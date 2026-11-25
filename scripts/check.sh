#!/bin/sh
# Offline static checks for luci-app-atomdns (used by CI and developers).
# Requires only sh, node and python3; nothing is installed into the package.
set -eu

cd "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
P=luci-app-atomdns

fail=0

check_sh() {
	for f do
		if sh -n "$f"; then
			echo "ok   sh -n $f"
		else
			echo "FAIL sh -n $f" >&2
			fail=1
		fi
	done
}

check_js() {
	command -v node >/dev/null 2>&1 || { echo "FAIL node not found" >&2; fail=1; return 0; }
	for f do
		if node --check "$f"; then
			echo "ok   node --check $f"
		else
			echo "FAIL node --check $f" >&2
			fail=1
		fi
	done
}

check_json() {
	command -v python3 >/dev/null 2>&1 || { echo "FAIL python3 not found" >&2; fail=1; return 0; }
	for f do
		if python3 -c 'import json,sys; json.load(open(sys.argv[1], encoding="utf-8"))' "$f"; then
			echo "ok   python3 json $f"
		else
			echo "FAIL python3 json $f" >&2
			fail=1
		fi
	done
}

check_yaml() {
	command -v python3 >/dev/null 2>&1 || return 0
	python3 -c 'import yaml' >/dev/null 2>&1 || { echo "skip YAML parse (PyYAML unavailable)"; return 0; }
	for f do
		if python3 -c 'import sys,yaml; yaml.safe_load(open(sys.argv[1], encoding="utf-8"))' "$f"; then
			echo "ok   python3 yaml $f"
		else
			echo "FAIL python3 yaml $f" >&2
			fail=1
		fi
	done
}

check_python() {
	command -v python3 >/dev/null 2>&1 || { echo "FAIL python3 not found" >&2; fail=1; return 0; }
	for f do
		# 把 pyc 重定向到缓存目录，保持工作树干净。
		if PYTHONPYCACHEPREFIX="${TMPDIR:-/tmp}/luci-atomdns-pycache" python3 -m py_compile "$f"; then
			echo "ok   python3 -m py_compile $f"
		else
			echo "FAIL python3 -m py_compile $f" >&2
			fail=1
		fi
	done
}

check_sh \
	scripts/check.sh \
	"$P/root/etc/init.d/atomdns" \
	"$P/root/etc/uci-defaults/99-atomdns" \
	"$P/root/usr/libexec/rpcd/atomdns"

check_js "$P/htdocs/luci-static/resources/view/atomdns/status.js"

check_json \
	"$P/root/usr/share/luci/menu.d/luci-app-atomdns.json" \
	"$P/root/usr/share/rpcd/acl.d/luci-app-atomdns.json"

check_python scripts/bump.py

check_yaml .github/workflows/ci.yml .github/workflows/bump-atomdns.yml

[ "$fail" -eq 0 ] || { echo "static checks failed" >&2; exit 1; }
echo "all static checks passed"
