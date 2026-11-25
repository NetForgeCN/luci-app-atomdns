#!/usr/bin/env python3
"""自动检测上游 AtomDNS release，并更新本包的版本与 SHA256。

这是版本更新的唯一入口（workflow 与本地开发者共用）：

    python3 scripts/bump.py            # 默认 dry-run，不写任何文件
    python3 scripts/bump.py --apply    # 校验全部通过后原子写入 Makefile / README

设计原则：fail closed。任何网络错误、API 格式变化、资产缺失、下载地址与
Makefile 不一致、hash 与上游清单冲突，都会中止并在 stderr 记录原因；在全部
校验完成之前不会修改仓库文件。构建时的 SHA256 / 归档路径安全校验保持原样。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MAKEFILE = REPO_ROOT / "luci-app-atomdns" / "Makefile"

USER_AGENT = "luci-app-atomdns-bump/1.0 (+https://github.com/NetForgeCN/luci-app-atomdns)"
REQUEST_TIMEOUT = 30
MAX_ASSET_BYTES = 100 * 1024 * 1024
MAX_JSON_BYTES = 4 * 1024 * 1024
VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:[-+][0-9A-Za-z.-]+)?$")
README_VERSION_RE = re.compile(r"(本包对应上游版本 \*\*v)[0-9A-Za-z.+-]+(\*\*)")
MANIFEST_NAME = "atomdns-update-manifest.json"


class BumpError(Exception):
    """任何导致 fail closed 的校验失败。"""


def log(message: str) -> None:
    print(f"[bump] {message}", flush=True)


def fail(message: str) -> None:
    raise BumpError(message)


@dataclass
class MakefileInfo:
    path: Path
    readme_path: Path
    text: str
    lines: List[str]
    version: str
    version_index: int
    release_index: int
    pkg_release_index: int
    owner: str
    repo: str
    conf_file: str
    conf_hash_index: int
    bin_hash_indexes: List[Tuple[int, str]]
    asset_names: List[str]


def find_assignment(lines: List[str], key: str, label: str) -> Tuple[str, int]:
    """找到唯一的 Makefile 赋值行，返回 (值, 行号)。"""
    regex = re.compile(re.escape(key) + r":=(\S+)")
    found: List[Tuple[str, int]] = []
    for index, raw in enumerate(lines):
        match = regex.fullmatch(raw.rstrip("\r\n"))
        if match:
            found.append((match.group(1), index))
    if len(found) != 1:
        fail(f"Makefile 中 {label} 应恰好出现一次，实际 {len(found)} 次")
    return found[0]


def parse_makefile(path: Path) -> MakefileInfo:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        fail(f"无法读取 Makefile: {exc}")
    lines = text.splitlines(keepends=True)

    version, version_index = find_assignment(lines, "PKG_VERSION", "PKG_VERSION")
    _, release_index = find_assignment(lines, "ATOMDNS_RELEASE_URL", "ATOMDNS_RELEASE_URL")
    _, pkg_release_index = find_assignment(lines, "PKG_RELEASE", "PKG_RELEASE")
    _, conf_hash_index = find_assignment(lines, "ATOMDNS_CONF_HASH", "ATOMDNS_CONF_HASH")
    config_name, _ = find_assignment(lines, "ATOMDNS_CONF_FILE", "ATOMDNS_CONF_FILE")
    bin_template, _ = find_assignment(lines, "ATOMDNS_BIN_FILE", "ATOMDNS_BIN_FILE")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", config_name):
        fail(f"ATOMDNS_CONF_FILE 含不安全字符: {config_name!r}")
    if bin_template != "atomdns-linux-$(ATOMDNS_BIN_VARIANT).tar.gz":
        fail(f"ATOMDNS_BIN_FILE 模板不符合预期，拒绝猜测资产名: {bin_template!r}")

    release_url, _ = find_assignment(lines, "ATOMDNS_RELEASE_URL", "ATOMDNS_RELEASE_URL")
    url_match = re.fullmatch(
        r"https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/releases/download/v\$\(PKG_VERSION\)",
        release_url,
    )
    if not url_match:
        fail(
            f"不支持的 ATOMDNS_RELEASE_URL: {release_url!r}；"
            "本脚本只接受 GitHub releases 且版本由 $(PKG_VERSION) 参数化的地址"
        )
    owner, repo = url_match.group(1), url_match.group(2)

    # 按出现顺序把每个 BIN_HASH 归属于它前面最近的 BIN_VARIANT，
    # 这样架构分支里的哈希可以逐个替换，占位分支也不会漏改。
    bin_hash_indexes: List[Tuple[int, str]] = []
    current_variant: Optional[str] = None
    hash_by_variant: Dict[str, str] = {}
    for index, raw in enumerate(lines):
        line = raw.rstrip("\r\n")
        variant_match = re.fullmatch(r"\s*ATOMDNS_BIN_VARIANT:=(\S+)", line)
        if variant_match:
            current_variant = variant_match.group(1)
            if not re.fullmatch(r"[A-Za-z0-9_-]+", current_variant):
                fail(f"ATOMDNS_BIN_VARIANT 含不安全字符: {current_variant!r}")
            continue
        hash_match = re.fullmatch(r"\s*ATOMDNS_BIN_HASH:=([0-9a-fA-F]{64})", line)
        if hash_match:
            if current_variant is None:
                fail(f"Makefile 第 {index + 1} 行的 BIN_HASH 前面没有 BIN_VARIANT")
            if current_variant in hash_by_variant and hash_by_variant[current_variant] != hash_match.group(1):
                fail(f"Makefile 中 {current_variant} 的多个 BIN_HASH 不一致，拒绝自动修复")
            hash_by_variant[current_variant] = hash_match.group(1)
            bin_hash_indexes.append((index, current_variant))
            current_variant = None

    if len(bin_hash_indexes) < 3:
        fail(f"Makefile 中只找到 {len(bin_hash_indexes)} 处 BIN_HASH，预期至少 3 处")
    asset_names = sorted("atomdns-linux-" + variant + ".tar.gz" for variant in hash_by_variant)

    return MakefileInfo(
        path=path,
        readme_path=path.parent.parent / "README.md",
        text=text,
        lines=lines,
        version=version,
        version_index=version_index,
        release_index=release_index,
        pkg_release_index=pkg_release_index,
        owner=owner,
        repo=repo,
        conf_file=config_name,
        conf_hash_index=conf_hash_index,
        bin_hash_indexes=bin_hash_indexes,
        asset_names=asset_names,
    )


def parse_version(value: str, label: str) -> Tuple[Tuple[int, int, int], str]:
    match = VERSION_RE.fullmatch(value.strip())
    if not match:
        fail(f"{label} 版本格式无法识别: {value!r}")
    return (int(match.group(1)), int(match.group(2)), int(match.group(3))), match.group(0)


def http_get(url: str, label: str, token: Optional[str] = None, max_bytes: int = MAX_ASSET_BYTES) -> bytes:
    headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    # 只把凭据发给 GitHub API；资产下载走公开 browser_download_url，
    # 避免 urllib 跟随跳转时把 token 带到第三方 CDN。
    if token and (urllib.parse.urlsplit(url).hostname or "") == "api.github.com":
        headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            declared = response.headers.get("Content-Length", "")
            if declared.isdigit() and int(declared) > max_bytes:
                fail(f"{label} 声明大小 {declared} 字节，超过上限 {max_bytes}")
            chunks: List[bytes] = []
            total = 0
            while True:
                chunk = response.read(256 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    fail(f"{label} 实际下载超过上限 {max_bytes} 字节")
                chunks.append(chunk)
            if total == 0:
                fail(f"{label} 下载内容为空")
            return b"".join(chunks)
    except urllib.error.HTTPError as exc:
        fail(f"{label} HTTP 错误: {exc.code} {exc.reason}")
    except (urllib.error.URLError, OSError) as exc:
        fail(f"{label} 网络错误: {exc}")
    raise AssertionError("unreachable")


def fetch_json(url: str, label: str, token: Optional[str] = None) -> dict:
    raw = http_get(url, label, token=token, max_bytes=MAX_JSON_BYTES)
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail(f"{label} 不是合法 JSON: {exc}")
    if not isinstance(data, dict):
        fail(f"{label} 顶层不是 JSON 对象")
    return data


def collect_assets(release: dict, expected_prefix: str) -> Dict[str, dict]:
    raw_assets = release.get("assets")
    if not isinstance(raw_assets, list) or not raw_assets:
        fail("上游 release 没有资产列表")
    assets: Dict[str, dict] = {}
    for asset in raw_assets:
        if not isinstance(asset, dict):
            fail("上游 release 资产条目格式异常")
        name, url = asset.get("name"), asset.get("browser_download_url")
        if not isinstance(name, str) or not isinstance(url, str):
            fail("上游 release 资产缺少 name 或 browser_download_url")
        if name in assets:
            fail(f"上游 release 资产重名: {name}")
        if not url.startswith(expected_prefix):
            fail(f"资产 {name} 的下载地址与 Makefile 的 release URL 不一致: {url}")
        if asset.get("state") not in (None, "uploaded"):
            fail(f"资产 {name} 尚未上传完成 (state={asset.get('state')!r})")
        assets[name] = asset
    return assets


def hash_asset(asset: dict, name: str) -> str:
    raw = http_get(asset["browser_download_url"], f"资产 {name}")
    declared_size = asset.get("size")
    if isinstance(declared_size, int) and declared_size != len(raw):
        fail(f"资产 {name} 大小不符: API 声明 {declared_size}，实际 {len(raw)}")
    digest = hashlib.sha256(raw).hexdigest()
    log(f"sha256 {name} = {digest}")
    return digest


def verify_manifest(assets: Dict[str, dict], tag: str, hashes: Dict[str, str], binary_names: List[str]) -> None:
    """用上游自带的清单交叉校验二进制哈希；清单缺失则只依赖直接计算的 SHA256。"""
    if MANIFEST_NAME not in assets:
        log("注意: 上游 release 未提供更新清单，跳过交叉校验（仍使用直接下载的 SHA256）")
        return
    manifest = fetch_json(assets[MANIFEST_NAME]["browser_download_url"], "上游更新清单")
    if manifest.get("version") not in (tag, tag.lstrip("v")):
        fail(f"更新清单版本与 release tag 不一致: {manifest.get('version')!r} != {tag!r}")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        fail("更新清单缺少 artifacts 对象")
    for name in binary_names:
        entry = artifacts.get(name)
        if not isinstance(entry, dict) or not isinstance(entry.get("sha256"), str):
            fail(f"更新清单缺少 {name} 的 sha256，拒绝更新")
        expected = entry["sha256"].lower()
        if expected != hashes[name]:
            fail(f"{name} 的实际 SHA256 与上游清单不一致，拒绝更新")


def make_value(line: str, key: str, value: str) -> str:
    body = line.rstrip("\r\n")
    eol = line[len(body):]
    regex = re.compile(r"^(\s*" + re.escape(key) + r"\s*:=\s*)([^\s#]+)(.*)$")
    match = regex.fullmatch(body)
    if not match:
        fail(f"无法替换 Makefile 行: {body!r}")
    return match.group(1) + value + match.group(3) + eol


def build_new_makefile(info: MakefileInfo, plain_version: str, hashes: Dict[str, str]) -> str:
    lines = list(info.lines)
    lines[info.version_index] = make_value(lines[info.version_index], "PKG_VERSION", plain_version)
    lines[info.release_index] = make_value(
        lines[info.release_index], "ATOMDNS_RELEASE_URL",
        f"https://github.com/{info.owner}/{info.repo}/releases/download/v$(PKG_VERSION)",
    )
    lines[info.pkg_release_index] = make_value(lines[info.pkg_release_index], "PKG_RELEASE", "1")
    lines[info.conf_hash_index] = make_value(lines[info.conf_hash_index], "ATOMDNS_CONF_HASH", hashes[info.conf_file])
    for index, variant in info.bin_hash_indexes:
        lines[index] = make_value(lines[index], "ATOMDNS_BIN_HASH", hashes["atomdns-linux-" + variant + ".tar.gz"])
    return "".join(lines)


def build_new_readme(path: Path, tag: str) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        fail(f"无法读取 README: {exc}")
    new_text, count = README_VERSION_RE.subn(lambda m: m.group(1) + tag[1:] + m.group(2), text)
    if count != 1:
        fail("README 中未找到唯一的上游版本标记，拒绝留下过期说明")
    return new_text


def atomic_write(path: Path, content: str) -> None:
    """全部校验完成后才写盘；保留原文件权限。"""
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
        os.chmod(tmp_name, stat.S_IMODE(path.stat().st_mode))
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def emit_outputs(updated: bool, version: str) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    with open(output_path, "a", encoding="utf-8") as handle:
        handle.write(f"updated={'true' if updated else 'false'}\n")
        handle.write(f"version={version}\n")


def run(apply: bool, makefile_path: Path) -> Tuple[bool, str]:
    info = parse_makefile(makefile_path)
    log(f"当前版本 v{info.version}，上游仓库 {info.owner}/{info.repo}")

    release = fetch_json(
        f"https://api.github.com/repos/{info.owner}/{info.repo}/releases/latest",
        "GitHub release API",
        token=os.environ.get("GITHUB_TOKEN"),
    )
    if release.get("draft") or release.get("prerelease"):
        fail("上游最新 release 是 draft/prerelease，拒绝自动升级")
    tag = release.get("tag_name")
    if not isinstance(tag, str) or not tag.startswith("v"):
        fail(f"上游 tag 格式不符合 Makefile 的 v$(PKG_VERSION) 约定: {tag!r}")
    upstream_version, plain_version = parse_version(tag[1:], "上游 tag")
    current_version, _ = parse_version(info.version, "Makefile PKG_VERSION")

    if upstream_version <= current_version:
        log(f"no update（Makefile v{info.version} 已是最新，上游 {tag}）")
        return False, f"v{info.version}"

    expected_prefix = f"https://github.com/{info.owner}/{info.repo}/releases/download/{tag}/"
    assets = collect_assets(release, expected_prefix)
    needed = info.asset_names + [info.conf_file]
    missing = [name for name in needed if name not in assets]
    if missing:
        fail("上游 release 资产不全: " + ", ".join(missing))

    hashes = {name: hash_asset(assets[name], name) for name in needed}
    verify_manifest(assets, tag, hashes, info.asset_names)

    new_makefile = build_new_makefile(info, plain_version, hashes)
    new_readme = build_new_readme(info.readme_path, tag)
    if new_makefile == info.text:
        fail("生成内容与当前 Makefile 相同，拒绝无意义提交")

    if apply:
        atomic_write(info.path, new_makefile)
        atomic_write(info.readme_path, new_readme)
        log(f"已更新 Makefile 与 README 至 {tag}")
    else:
        log(f"dry-run: 将更新 Makefile 与 README 至 {tag}，未写入任何文件")
    return apply, tag


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="校验通过后写入 Makefile / README；默认 dry-run")
    parser.add_argument("--makefile", type=Path, default=DEFAULT_MAKEFILE, help="要检查/更新的 Makefile 路径")
    args = parser.parse_args(argv)

    try:
        updated, version = run(args.apply, args.makefile)
    except BumpError as exc:
        print(f"[bump] ERROR: {exc}；fail closed，仓库文件未改动", file=sys.stderr, flush=True)
        return 1
    emit_outputs(updated, version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
