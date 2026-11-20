# luci-app-atomdns

AtomDNS 的一体化 OpenWrt 包：主程序二进制、默认配置、内置 WebUI 与 LuCI 控制面板打包在同一个 ipk 里，装完即可用。

AtomDNS 是 [jasonxtt/atomdns](https://github.com/jasonxtt/atomdns)（Rust 重写的 MosDNS），单静态二进制，支持国内外 DNS 分流、FakeIP、路由学习、乐观缓存、DoH/DoT、SRS/geosite 规则与内置 WebUI。本包对应上游版本 **v0.6.6**。

## 功能

- 主程序：官方 musl 静态二进制，按目标架构自动选择（x86_64 / arm64 / armv7），编译期下载并做 SHA256 校验后随固件打包
- 内置 WebUI：随官方配置包提供，位于 `/usr/share/atomdns/ui/main/`
- LuCI 控制面板：启用开关、DNS / WebUI 端口、配置目录、打开 WebUI、重启服务
- procd 托管：开机自启、异常重启、配置变更自动重载
- 升级保留：UCI 配置走 conffiles，运行时数据目录走 `keep.d`，sysupgrade 保留配置时不丢规则与缓存

程序本体的能力（分流规则、FakeIP、路由学习、乐观缓存、DoH/DoT、订阅与规则更新等）在内置 WebUI 里配置；LuCI 只负责开关、端口与入口。

## 端口与默认行为

| 项目 | 默认值 | 说明 |
|---|---|---|
| DNS 监听 | **2053** | 避开 dnsmasq 的 53；需接管局域网 DNS 时先停用 dnsmasq DNS 再改 53 |
| WebUI | **9099** | 明文 HTTP |
| 启用状态 | **关闭** | 安装后默认不启用，不影响现有网络 |
| 配置/数据目录 | `/etc/atomdns` | 首次启动从 `/usr/share/atomdns` 初始化，升级不丢规则与缓存 |

## 目录结构

包本体位于仓库的 `luci-app-atomdns/` 子目录，这是 OpenWrt feed 扫描所要求的两级结构（feed 根 → 包目录 → Makefile）。

```
<repo>/
├── LICENSE
├── README.md
└── luci-app-atomdns/                                  # 包目录（feed 扫描的单位）
    ├── Makefile                                       # 下载校验 + 打包 + luci.mk
    ├── htdocs/.../view/atomdns/status.js              # LuCI 视图
    └── root/
        ├── etc/config/atomdns                         # UCI 配置（conffile）
        ├── etc/init.d/atomdns                         # procd 启动脚本
        ├── etc/uci-defaults/99-atomdns                # UCI 默认值与 rpcd 权限兜底
        ├── lib/upgrade/keep.d/luci-app-atomdns        # sysupgrade 保留数据目录
        ├── usr/libexec/rpcd/atomdns                   # ubus 方法：status / restart
        ├── usr/share/luci/menu.d/luci-app-atomdns.json    # 服务 → AtomDNS 菜单
        └── usr/share/rpcd/acl.d/luci-app-atomdns.json     # 访问控制
```

## 构建前提

- 构建主机需装 `unzip`，用于解压官方 `config_rust.zip`；编译树中需已安装 `feeds/luci`（本包包含 `$(TOPDIR)/feeds/luci/luci.mk`）。
- 两个外部资产 `atomdns-linux-<arch>.tar.gz` 与 `config_rust.zip` 由 `Download/` 规则挂在 `$(STAMP_PREPARED)` 上，编译期自动下载并校验 SHA256，开机不联网拉取。需要提前拉取可执行 `make package/feeds/atomdns/luci-app-atomdns/download`。
- 支持 **x86_64 / aarch64 / armv7** 目标；其他架构（mips、armv5 / armv6 等）在编译阶段报错终止，不会静默打入不兼容的二进制。

## 接入与编译

feed 短名用 `atomdns`（不含 `-`：`scripts/feeds` 用 `\w+` 解析 feeds.conf 的名称段）：

```sh
echo 'src-git atomdns https://github.com/NetForgeCN/luci-app-atomdns.git' >> feeds.conf.default

./scripts/feeds update atomdns                 # 拉取源码并生成索引
./scripts/feeds install luci-app-atomdns      # 把包链接进 package/feeds/
```

`feeds update` 只生成索引，`feeds install` 才会创建 `package/feeds/atomdns/luci-app-atomdns` 软链，menuconfig 扫描的是 `package/` 目录树。

在 `make menuconfig` 里选中 **LuCI → Applications → luci-app-atomdns**，然后编译：

```sh
make package/feeds/atomdns/luci-app-atomdns/compile V=s

# 或整体编译
make -j$(nproc)
```

产物在 `bin/packages/<arch>/` 的 luci 子目录下，用 `opkg install` 安装单个 ipk 即可。

## 使用

1. 进入 **LuCI → 服务 → AtomDNS**，勾选「启用」。
2. 确认 DNS 端口（默认 2053）与 WebUI 端口（默认 9099），保存应用。
3. 服务运行后点 **打开 WebUI** 进入内置管理界面。
4. 首次启动自动初始化 `/etc/atomdns`，含默认规则、缓存目录与 WebUI 资源。

内置 WebUI 只提供明文 HTTP，LuCI 的「打开 WebUI」按钮固定以 `http://` 拼地址，不随 LuCI 自身的 HTTPS 切换。

## 端口与 DNS 接管

- 默认旁挂在 **2053**，不影响系统 dnsmasq，此时它只是一个独立 DNS 服务器，需手动把客户端或上游指向它。
- 若要接管局域网 DNS（占用 53），先停用 dnsmasq 的 DNS 监听（保留 DHCP），再把 `dns_port` 改为 `53`：

  ```sh
  uci set dnsmasq.@dnsmasq[0].port='0'
  uci set dnsmasq.@dnsmasq[0].dns_forward_max=0
  uci commit dnsmasq
  uci set atomdns.main.dns_port='53'
  uci commit atomdns
  /etc/init.d/dnsmasq restart
  /etc/init.d/atomdns restart
  ```

- AtomDNS 的「指定客户端直连」分流要求直面客户端，必须占用 53；旁挂在 2053 时该功能不可用。
- WebUI 端口改动后需重启服务，再用 LuCI 按钮打开新端口。

## UCI 配置项

| 选项 | 默认值 | 说明 |
|---|---|---|
| `enabled` | `0` | 是否启用，procd 开机自启 |
| `dns_port` | `2053` | DNS 监听端口（UDP/TCP） |
| `webui_port` | `9099` | 管理 API / WebUI 端口 |
| `config_dir` | `/etc/atomdns` | 配置与数据目录 |
| `log_file` | `/tmp/atomdns.log` | 日志文件路径 |

## 升级保留

数据目录 `/etc/atomdns/`（含 `config_custom.yaml`、订阅规则 `srs/` `adguard/`、缓存与学习数据）在首次启动时生成，不在 opkg conffiles 追踪范围内，因此由两份清单互补覆盖：

| 清单 | 覆盖内容 | 机制 |
|---|---|---|
| conffiles `/etc/config/atomdns` | UCI 配置（启用开关、端口、目录路径） | opkg 追踪 checksum |
| keep.d `/etc/atomdns` | 数据目录（规则、订阅、缓存、学习数据） | sysupgrade `find` 递归展开 |

在路由器上执行 `sysupgrade -l | grep atomdns` 可确认两份清单都生效。若把 `config_dir` 改到 `/etc/atomdns` 以外的路径，需把新路径一并写进 `root/lib/upgrade/keep.d/luci-app-atomdns`。

## 二进制变体

x86_64 使用官方 `amd64-musl` 静态版（零依赖，适配 OpenWrt 的 musl 环境）。官方另有 `amd64-v3`（AVX2）变体，但它是 glibc 动态链接（解释器 `/lib64/ld-linux-x86-64.so.2`），与 OpenWrt 的 musl 不兼容，故不采用。musl 二进制通过内置 WebUI 在线更新时仍会选用 musl 变体；arm 平台上在线更新功能自动关闭，固件内的版本升级建议通过重新编译本包完成，以保证校验值一致。

## 注意事项

- **端口**：9099 是 WebUI 默认端口，一般不与 OpenWrt 组件冲突；被占用时可在 UCI 中修改。
- **日志**：默认写到 `/tmp/atomdns.log`（内存文件系统）避免占用 flash；需长期留存可改到 `/etc/atomdns/atomdns.log`。
- **首次初始化**：配置目录非空且缺少 `config_custom.yaml` 时不会自动写文件，避免覆盖已有数据。
- **脚本执行位**：打包钩子会统一设置 init.d、uci-defaults 与 rpcd 插件的可执行位，`uci-defaults` 另有一道开机兜底，保证 rpcd 只加载带 owner 可执行位插件的要求得到满足。

## 许可证

本打包仓库以 **GPL-3.0-only** 授权，全文见 [LICENSE](LICENSE)。

- 上游程序：[jasonxtt/atomdns](https://github.com/jasonxtt/atomdns)（GPL-3.0）
- 上游文档：https://jasonxtt.github.io/atomdns/
