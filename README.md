# luci-app-atomdns

AtomDNS 的一体化 OpenWrt 包——**装一个 ipk 即可用**：主程序二进制、默认配置、内置 WebUI 与 LuCI 控制面板全部打包在一起。

AtomDNS 是 [jasonxtt/atomdns](https://github.com/jasonxtt/atomdns)（Rust 重写的 MosDNS），单静态二进制，支持国内外 DNS 分流、FakeIP、路由学习、乐观缓存、DoH/DoT、SRS/geosite 规则与内置 WebUI。对应上游版本 **v0.6.6**。

> 本包已整合原独立 `atomdns` 主程序包，不再需要额外安装主程序，也不再依赖 `+atomdns`。

## 功能

- 主程序：官方 musl 静态二进制，按架构自动选择（x86_64 / arm64 / armv7），SHA256 校验
- 内置 WebUI：随官方配置包一起提供（`/usr/share/atomdns/ui/main/`）
- LuCI 控制面板：状态查看、端口配置、一键打开 WebUI、一键重启
- procd 托管：开机自启、异常重启、配置变更自动重载

程序本体的全部能力（分流规则、FakeIP、路由学习、乐观缓存、DoH/DoT、订阅与规则更新等）在内置 WebUI 里操作；LuCI 只负责开关、端口与入口。

## 端口与默认行为

| 项目 | 默认值 | 说明 |
|---|---|---|
| DNS 监听 | **2053** | 避开 dnsmasq 的 53；需接管局域网 DNS 时先停用 dnsmasq DNS 再改 53 |
| WebUI | **9099** | 明文 HTTP |
| 启用状态 | **关闭** | 安装后默认不启用，需手动打开，不影响现有网络 |
| 配置/数据目录 | `/etc/atomdns` | 首次启动从 `/usr/share/atomdns` 初始化，升级不丢规则/缓存 |

## 目录结构

仓库根目录**不是**包目录：包本体放在 `luci-app-atomdns/` 子目录里，这是 OpenWrt feed 的硬性要求（原因见下文「为什么包必须放在子目录」）。

```
<repo>/
├── README.md
└── luci-app-atomdns/                                  # 包目录（feed 扫描的单位）
    ├── Makefile                                       # 下载校验 + 打包 + luci.mk
    ├── htdocs/.../view/atomdns/status.js              # LuCI 视图
    └── root/
        ├── etc/config/atomdns                         # UCI 配置（conffile）
        ├── etc/init.d/atomdns                         # procd 启动脚本
        ├── etc/uci-defaults/99-atomdns                # UCI 默认值 + rpcd 权限兜底
        ├── usr/libexec/rpcd/atomdns                   # ubus 方法：status / restart
        ├── usr/share/luci/menu.d/luci-app-atomdns.json    # 服务 → AtomDNS 菜单
        └── usr/share/rpcd/acl.d/luci-app-atomdns.json     # 访问控制
```

> 二进制与官方配置包不在仓库内，编译时由 Makefile 从官方 Release 下载并校验 SHA256 后打包进 ipk。

## 构建前提

- 构建主机需装 `unzip`（OpenWrt 官方 prereq 列表已包含；`tools/` 里只提供 `zip`，不提供 `unzip`），用于解压官方 `config_rust.zip`。
- 需要编译树中已安装 `feeds/luci`（本包 `include $(TOPDIR)/feeds/luci/luci.mk`）。
- 仅支持 **x86_64 / aarch64 / armv7** 目标；其他架构（mips、armv5/armv6 等）在编译阶段直接报错，不会静默打进错误的二进制。

## 安装

把本仓库加入 feed，**feed 短名用 `atomdns`**（不能带 `-`）：

```sh
# 先删掉之前那条报错的写法（如果有）
sed -i '/^src-git luci-app-atomdns /d' feeds.conf.default

echo 'src-git atomdns https://github.com/NetForgeCN/luci-app-atomdns.git' >> feeds.conf.default

./scripts/feeds update atomdns      # 只负责拉源码 + 生成索引，不做安装
./scripts/feeds install luci-app-atomdns   # 这一步才会把包链进 package/feeds/
```

> ⚠️ **`feeds update` 不等于 `feeds install`**：`update` 只把仓库拉到 `feeds/atomdns/` 并生成 `feeds/atomdns.index`；`make menuconfig` 扫的是 `package/` 目录树，必须再 `install` 才会生成 `package/feeds/atomdns/luci-app-atomdns` 这个软链。只 update 不 install，menuconfig 里必然看不到，而且**不会有任何报错**。

> ⚠️ **feed 短名不能含 `-`**：`scripts/feeds` 用 `(\w+)` 解析 feeds.conf 的 name 段（类型段才是 `([\w\-]+)`），所以 `src-git luci-app-atomdns ...` 会直接报 `Syntax error in feeds.conf.default`。包名 `luci-app-atomdns` 本身带横线没问题——feed 名和包名是两回事。

`make menuconfig` 选中 `LuCI` → `Applications` → `luci-app-atomdns`，然后编译：

```sh
# 单包编译（路径是 package/feeds/<feed 名>/<包目录名>，这里两者恰好都叫 atomdns 系）
make package/feeds/atomdns/luci-app-atomdns/compile V=s

# 或者整体编译
make -j$(nproc)
```

产物在 `bin/packages/<arch>/`（luci 子目录下），用 `opkg install` 安装单个 ipk 即可。装完进 **LuCI → 服务 → AtomDNS** 启用。

## 为什么 menuconfig 里找不到（两个静默坑）

`scripts/feeds` + `include/scan.mk` 有两个不报错、只静默跳过的地方，历史上都踩过：

**1) Makefile 里必须出现 `call BuildPackage` 字样**

`include/scan.mk` 收集包用的是：

```sh
find -L <SCAN_DIR> -mindepth 1 -maxdepth 5 -name Makefile \
  | xargs grep -aHE 'call (Build/DefaultTargets|BuildPackage|BuildContainer|BuildCompose|KernelPackage)'
```

grep **只看 Makefile 文件本身，不看它 include 进来的 luci.mk**。本包的 BuildPackage 在 `luci.mk` 末尾 eval，正文原本没有这个关键字，于是被当成「不是包的普通 Makefile」整条丢弃。修复方式是末尾保留这一行注释（官方 luci 包也有，纯扫描标记）：

```make
# call BuildPackage - OpenWrt buildroot signature
```

**2) 包必须在 feed 根目录的下一级子目录里**

上面那条管线的路径处理是 `sed 's#^<SCAN_DIR>/##' -e 's#/Makefile:.*##'`，它依赖「feed 根 → 包目录 → Makefile」这种至少两级的结构。如果包直接摊在仓库根（`feeds/atomdns/Makefile`），`-mindepth 1` 仍会找到它，但 sed 剥掉前缀后剩下的是 `Makefile:12:...`，最后拼成 `feeds/atomdns/Makefile:12:.../Makefile` 这种不存在的路径，索引里就成了垃圾条目。所以包必须放在 `luci-app-atomdns/` 子目录下。

**3) 索引过期**

改完 feeds.conf 或仓库结构后，建议连带重建索引：

```sh
rm -f feeds/atomdns.index feeds/atomdns.tmp/.packageinfo
./scripts/feeds update atomdns
./scripts/feeds install -f luci-app-atomdns
```

若之前在 `package/feeds/atomdns/` 下留下过错乱的软链，先 `./scripts/feeds uninstall atomdns` 再 install。

**自检**：`grep -c 'Package: luci-app-atomdns' feeds/atomdns.index` 返回 ≥1 就说明索引正常，menuconfig 一定能看到。

## 使用

1. 进入 **LuCI → 服务 → AtomDNS**，勾选「启用」。
2. 确认 DNS 端口（默认 2053）与 WebUI 端口（默认 9099），保存应用。
3. 状态显示「运行中」后点 **打开 WebUI** 进入内置管理界面。
4. 首次启动自动初始化 `/etc/atomdns`，含默认规则、缓存目录与 WebUI 资源。

## 端口与 DNS 接管

- 默认旁挂在 **2053**，不影响系统 dnsmasq。此时它只是一个独立 DNS 服务器，需手动把客户端或上游指向它。
- 若要让它接管局域网 DNS（占用 53），需先停用 dnsmasq 的 DNS 监听（保留 DHCP），再把 `dns_port` 改为 `53`：

  ```sh
  uci set dnsmasq.@dnsmasq[0].port='0'      # 关闭 dnsmasq 的 DNS 端口
  uci set dnsmasq.@dnsmasq[0].dns_forward_max=0
  uci commit dnsmasq
  uci set atomdns.main.dns_port='53'
  uci commit atomdns
  /etc/init.d/dnsmasq restart
  /etc/init.d/atomdns restart
  ```

- AtomDNS 的「指定客户端直连」分流功能要求它直面客户端，**必须占用 53**；旁挂在 2053 时该功能不可用。
- WebUI 端口改动后需重启服务，再用 LuCI 按钮打开新端口。

## UCI 配置项

| 选项 | 默认值 | 说明 |
|---|---|---|
| `enabled` | `0` | 是否启用，procd 开机自启 |
| `dns_port` | `2053` | DNS 监听端口（UDP/TCP） |
| `webui_port` | `9099` | 管理 API / WebUI 端口 |
| `config_dir` | `/etc/atomdns` | 配置与数据目录 |
| `log_file` | `/tmp/atomdns.log` | 日志文件路径 |

## 关于「打开 WebUI」按钮

AtomDNS 内置 WebUI 只提供明文 HTTP（`api.http`，默认 `0.0.0.0:9099`）。按钮固定用 `http://` 拼地址，即使 LuCI 本身走 HTTPS 也不会误拼成 `https://host:9099` 导致 SSL 失败。

## 二进制变体说明

x86_64 使用官方 `amd64-musl` 静态版（零依赖，适配 OpenWrt 的 musl 环境）。官方另有 `amd64-v3`（AVX2）变体，但它是 **glibc 动态链接**（解释器 `/lib64/ld-linux-x86-64.so.2`），与 OpenWrt 的 musl 不兼容，故不采用。如需自编译 musl + AVX2 版本可另行处理。

## 注意事项

- **在线更新**：AtomDNS 内置 WebUI 一键更新。musl 二进制更新时会继续下载 musl 变体（`wants_musl()` 判断），不会被替换成 glibc 版；arm 平台上更新功能自动关闭。不过固件自带的版本升级仍建议通过重新编译本包完成，以保证校验值一致。
- **9099 端口**：这是 WebUI 默认端口，一般不与 OpenWrt 组件冲突；若被占用请在 UCI 中修改。
- **日志**：默认写到 `/tmp/atomdns.log`（内存文件系统），避免占用 flash；如需长期留存可改到 `/etc/atomdns/atomdns.log`。
- **首次初始化**：配置目录非空且缺少 `config_custom.yaml` 时不会自动写文件，防止覆盖已有数据。
- **脚本执行位**：GitHub API 推送会把文件权限压成 `644`，而 rpcd 只加载带 owner 可执行位的插件。打包钩子里已显式 `chmod 0755`，`uci-defaults` 里另有一道开机兜底。

## 来源与许可

- 上游程序：[jasonxtt/atomdns](https://github.com/jasonxtt/atomdns)（GPL-3.0）
- 上游文档：https://jasonxtt.github.io/atomdns/
- 本打包仓库遵循 GPL-3.0。
