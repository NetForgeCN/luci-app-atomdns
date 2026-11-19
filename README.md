# luci-app-atomdns

AtomDNS 的一体化 OpenWrt 包——**装一个 ipk 即可用**：主程序二进制、默认配置、内置 WebUI 与 LuCI 控制面板全部打包在一起。

AtomDNS 是 [jasonxtt/atomdns](https://github.com/jasonxtt/atomdns)（Rust 重写的 MosDNS），单静态二进制，支持国内外 DNS 分流、FakeIP、路由学习、乐观缓存、DoH/DoT、SRS/geosite 规则与内置 WebUI。对应上游版本 **v0.6.6**。

> 本包已整合原独立 `atomdns` 主程序包，不再需要额外安装主程序，也不再依赖 `+atomdns`。

## 功能

- 主程序：官方 musl 静态二进制，按架构自动选择（x86_64 / arm64 / armv7），SHA256 校验
- 内置 WebUI：随官方配置包一起提供（`/usr/share/atomdns/ui/main/`）
- LuCI 控制面板：状态查看、端口配置、一键打开 WebUI、一键重启
- procd 托管：开机自启、异常重启、配置变更自动重载

## 端口与默认行为

| 项目 | 默认值 | 说明 |
|---|---|---|
| DNS 监听 | **2053** | 避开 dnsmasq 的 53；需接管局域网 DNS 时先停用 dnsmasq DNS 再改 53 |
| WebUI | **9099** | 明文 HTTP |
| 启用状态 | **关闭** | 安装后默认不启用，需手动打开，不影响现有网络 |
| 配置/数据目录 | `/etc/atomdns` | 首次启动从 `/usr/share/atomdns` 初始化，升级不丢规则/缓存 |

## 目录结构

```
luci-app-atomdns/
├── Makefile                                           # 下载校验 + 打包 + luci.mk
├── htdocs/.../view/atomdns/status.js                  # LuCI 视图
└── root/
    ├── etc/config/atomdns                             # UCI 配置（conffile）
    ├── etc/init.d/atomdns                             # procd 启动脚本
    ├── etc/uci-defaults/99-atomdns                    # UCI 默认值 + rpcd 权限兜底
    ├── usr/libexec/rpcd/atomdns                       # ubus 方法：status / restart
    ├── usr/share/luci/menu.d/luci-app-atomdns.json    # 服务 → AtomDNS 菜单
    └── usr/share/rpcd/acl.d/luci-app-atomdns.json     # 访问控制
```

> 二进制与官方配置包不在仓库内，编译时由 Makefile 从官方 Release 下载并校验 SHA256 后打包进 ipk。

## 安装

把本仓库加入 feed：

```sh
echo 'src-git luci-app-atomdns https://github.com/NetForgeCN/luci-app-atomdns.git' >> feeds.conf.default
./scripts/feeds update luci-app-atomdns
./scripts/feeds install -a -p luci-app-atomdns
```

`make menuconfig` 选中 `LuCI` → `Applications` → `luci-app-atomdns`，然后编译：

```sh
make package/luci-app-atomdns/compile V=s
```

产物在 `bin/packages/<arch>/`，用 `opkg install` 安装单个 ipk 即可。

## 使用

1. 进入 **LuCI → 服务 → AtomDNS**，勾选「启用」。
2. 确认 DNS 端口（默认 2053）与 WebUI 端口（默认 9099），保存应用。
3. 状态显示「运行中」后点 **打开 WebUI** 进入内置管理界面。
4. 首次启动自动初始化 `/etc/atomdns`，含默认规则、缓存目录与 WebUI 资源。

## 关于「打开 WebUI」按钮

AtomDNS 内置 WebUI 只提供明文 HTTP（`api.http`，默认 `0.0.0.0:9099`）。按钮固定用 `http://` 拼地址，即使 LuCI 本身走 HTTPS 也不会误拼成 `https://host:9099` 导致 SSL 失败。

## 二进制变体说明

x86_64 使用官方 `amd64-musl` 静态版（零依赖，适配 OpenWrt 的 musl 环境）。官方另有 `amd64-v3`（AVX2）变体，但它是 **glibc 动态链接**（解释器 `/lib64/ld-linux-x86-64.so.2`），与 OpenWrt 的 musl 不兼容，故不采用。如需自编译 musl + AVX2 版本可另行处理。

## 在线更新说明

AtomDNS 内置 WebUI 的在线更新：musl 二进制更新时会继续下载 musl 变体（`wants_musl()` 判断），不会被替换成 glibc 版；ARM 平台更新功能自动禁用。不过固件版本升级仍建议通过重新编译本包完成，以保证哈希一致。

## 许可

GPL-3.0，与上游 AtomDNS 一致。
