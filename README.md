# luci-app-atomdns

AtomDNS 的 LuCI 控制面板。AtomDNS 是 [jasonxtt/atomdns](https://github.com/jasonxtt/atomdns)（Rust 重写的 MosDNS），单静态二进制，支持国内外 DNS 分流、FakeIP、路由学习、乐观缓存、DoH/DoT 与内置 WebUI。

本包**只提供 LuCI 控制界面**，不包含 AtomDNS 主程序。主程序由独立仓库 [`openwrt-atomdns`](https://github.com/NetForgeCN/openwrt-atomdns) 中的 `atomdns` 包提供（`LUCI_DEPENDS:=+atomdns`）。两者需要同时加入编译树。

## 功能

- 查看运行状态（启用 / 运行 / 版本 / 当前监听 / 配置目录）
- 配置 DNS 端口（默认 **2053**，避开 dnsmasq 的 53）、WebUI 端口（默认 **9099**）、配置目录、日志路径
- **一键打开内置 WebUI**：按当前 WebUI 端口在新标签页打开管理界面
- 一键重启服务

## 目录结构

```
luci-app-atomdns/
├── Makefile                                          # luci.mk 定义，依赖 +atomdns
├── htdocs/luci-static/resources/view/atomdns/status.js  # LuCI 视图
└── root/
    ├── etc/uci-defaults/99-atomdns                   # UCI 默认配置（仅缺失时写入）
    ├── usr/share/luci/menu.d/luci-app-atomdns.json   # 服务 → AtomDNS 菜单
    ├── usr/share/rpcd/acl.d/luci-app-atomdns.json    # 访问控制
    └── usr/libexec/rpcd/atomdns                      # ubus 方法：status / restart
```

## 安装

两个仓库都要加入 feed（地址按需替换为你自己的 fork）：

```sh
echo 'src-git atomdns https://github.com/NetForgeCN/openwrt-atomdns.git' >> feeds.conf.default
echo 'src-git luci-app-atomdns https://github.com/NetForgeCN/luci-app-atomdns.git' >> feeds.conf.default

./scripts/feeds update atomdns luci-app-atomdns
./scripts/feeds install -a -p atomdns
./scripts/feeds install -a -p luci-app-atomdns
```

然后 `make menuconfig` 选中：

- `Network` → `DNS and Domain Name Resolution` → `atomdns`
- `LuCI` → `Applications` → `luci-app-atomdns`

或单独编译验证：

```sh
make package/luci-app-atomdns/compile V=s
```

## 关于「打开 WebUI」按钮

AtomDNS 的内置管理界面由主程序运行，监听 `http://0.0.0.0:9099`（**明文 HTTP，无 TLS**）。按钮固定用 `http://` 拼地址：即使 LuCI 本身通过 HTTPS 访问，也不会误拼成 `https://host:9099` 导致 SSL 失败。需保证浏览器能访问到路由器对应端口，且服务处于运行状态。

## 获取方式说明

本 LuCI 包是纯脚本 / 静态资源（`LUCI_PKGARCH:=all`），**不涉及任何二进制下载**。AtomDNS 主程序二进制与其 WebUI 静态资源，均由 `atomdns` 主包在**编译阶段**从官方 GitHub Release 下载、校验 SHA256 后打包进 ipk（详见主包 README）。设备端安装后无需联网拉取程序本体。

## 许可

GPL-3.0，与上游 AtomDNS 一致。
