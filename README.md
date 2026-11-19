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
- 两个外部文件（`atomdns-linux-<arch>.tar.gz`、`config_rust.zip`）通过 `Download/` 定义挂在 `$(STAMP_PREPARED)` 上，`make .../compile` 会自动下载并校验 SHA256；想提前拉可以用 `make package/feeds/atomdns/luci-app-atomdns/download`。
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

## 编译时报 `tar: Cannot open: No such file or directory`

```
tar (child): /home/wrt/openwrt/dl/atomdns-linux-amd64-musl.tar.gz: Cannot open: No such file or directory
```

不是下载失败，而是**压根没有生成下载规则**。`Download/xxx` 只是数据定义，真正生成规则的是 `$(eval $(call Download,xxx))`；而 `Download` 宏来自 `download.mk`（由 `package.mk` 引入，`package.mk` 又在 `luci.mk` 里才被 include），宏未定义时 `$(call Download,x)` 展开为空串，`$(eval )` 就是空操作——静默无效，prepare 阶段自然没有文件。

所以本包的两行 eval 放在**文件末尾 `include $(TOPDIR)/feeds/luci/luci.mk` 之后**：只有那时 `Download` 宏和 `$(STAMP_PREPARED)` 才存在，才能展开出

```make
$(STAMP_PREPARED): $(DL_DIR)/atomdns-linux-<arch>.tar.gz $(DL_DIR)/config_rust.zip
```

（`Download/xxx` 的 **define 可以在前面**，**eval 必须在后面**——`Package/description`、`conffiles`、`Build/Prepare` 这些则是 define 也必须在前面，两类别搞混。）

验证方式：`make package/feeds/atomdns/luci-app-atomdns/download V=s` 应看到下载两个文件；或直接 `ls dl/atomdns-* dl/config_rust.zip`。

## 下载 404：`URL` 只能写到目录

```
curl: (22) The requested URL returned error: 404
Download failed.
No more mirrors to try - giving up.
```

`Download/xxx` 里的 `URL` 是**镜像目录**，不是文件地址。`scripts/download.pl` 内部是：

```perl
download_cmd("$mirror/$download_filename", ...)
```

即它会自己用 `FILE` 拼上文件名。所以把文件名也写进 `URL` 时，真实请求会变成重复拼接：

```
…/download/v0.6.6/atomdns-linux-amd64-musl.tar.gz/atomdns-linux-amd64-musl.tar.gz   → 404
```

GitHub 对这种路径就回 404，`download.pl` 再试 OpenWrt 官方源镜像（我们的文件不在那儿，也是 404），最后 `No more mirrors to try`。这也是官方包为什么一律 `PKG_SOURCE_URL:=<目录>` + `PKG_SOURCE:=<文件名>` 分开写。

本包的正确写法：

```make
ATOMDNS_RELEASE_URL:=https://github.com/jasonxtt/atomdns/releases/download/v$(PKG_VERSION)

define Download/atomdns-bin
  FILE:=atomdns-linux-amd64-musl.tar.gz   # 文件名放这里
  URL:=$(ATOMDNS_RELEASE_URL)             # 只写到目录
  HASH:=5ec815c1…
endef
```

**兜底**：网络确实不通时，手动把文件放进 `dl/`，下载规则检测到文件已存在会跳过。哈希必须与 Makefile 中固定的一致（v0.6.6）：

| 文件 | SHA256 |
|---|---|
| `atomdns-linux-amd64-musl.tar.gz` | `5ec815c111a934712061a438e0f6b35e520bcdba4ea6b1ab44b479989843d395` |
| `config_rust.zip` | `88a6332d83ebbe81d01ffcbd622b4afc3901689913a4dca327665ab1e0b0f84b` |

```sh
cd ~/openwrt/dl
curl -fL -O https://github.com/jasonxtt/atomdns/releases/download/v0.6.6/atomdns-linux-amd64-musl.tar.gz
curl -fL -O https://github.com/jasonxtt/atomdns/releases/download/v0.6.6/config_rust.zip
sha256sum atomdns-linux-amd64-musl.tar.gz config_rust.zip   # 必须与上表一致
```

## LuCI 页面报 `ReferenceError: rpc is not defined`

视图脚本顶部的依赖声明必须是 `'require xxx';`，**不是** `'use xxx';`。LuCI 的加载器（`luci.js`）在加载 view 时用正则
`/^require[ \t]+(\S+)...$/` 扫描字符串字面量，匹配到的模块才作为函数参数注入；`'use rpc'` 只有 `use strict` 被特殊识别，其余被当普通字符串丢弃，于是 `rpc` / `form` / `view` / `uci` 全是未定义。

正确写法（缺一不可，用到哪个就要 require 哪个）：

```js
'use strict';
'require view';
'require rpc';
'require uci';
'require form';
```

`E()` 与 `_()` 是全局函数，不需要 require。

另一个同源问题：状态区若写成 `m.section(form.TypedSection, '_status', ...)`，`_status` 会被当成 UCI section **类型**去查 `atomdns` 配置，而配置里只有 `config atomdns 'main'`（类型是 `atomdns`），查询返回空数组，整块状态区不渲染。状态区必须映射到真实 section：

```js
s = m.section(form.NamedSection, 'main', 'atomdns', _('运行状态'));
```

## 关于「运行状态」区块

早期版本在「服务设置」上方有个「运行状态」区块（服务状态/版本/监听/配置目录），已移除。原因：它走 rpcd 的 `atomdns status` 取数，`pidof`/`uci` 拼出的状态与实际进程并不可靠，且信息在服务设置里已经体现。现在 LuCI 只做配置与操作（启用、端口、配置目录、日志、打开 WebUI、重启），真实运行状态以内置 WebUI 为准。

`rpcd/atomdns` 里的 `status` 方法仍保留（给 ubus 手动调试用），但前端不再调用。

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

## "保留配置"升级固件时配置丢失

OpenWrt 的 sysupgrade 靠两份清单决定备份什么：包声明的 **conffiles**（只追踪安装时就存在的文件），以及 `/etc/sysupgrade.conf` + `/lib/upgrade/keep.d/*`（用 `find` 展开，会递归收目录下所有运行时生成的文件）。

AtomDNS 的数据目录 `/etc/atomdns/`（含 `config_custom.yaml`、订阅规则 `srs/` `adguard/`、缓存、学习数据）是**首次启动时才生成**的，不在 conffiles 追踪范围内。以前只在 conffiles 里声明了 `/etc/config/atomdns`（UCI 开关/端口），所以"保留配置"升级后 UCI 设置还在，但整个数据目录被丢弃——规则、订阅、缓存全没了，等于恢复出厂。

修复：新增 `root/lib/upgrade/keep.d/luci-app-atomdns`，内容就一行 `/etc/atomdns`。这与官方 `luci-theme-footstrap` 保留运行时上传文件的做法一致。两份清单现在互补：

| 清单 | 覆盖内容 | 机制 |
|---|---|---|
| conffiles `/etc/config/atomdns` | UCI 配置（启用开关、端口、目录路径） | opkg 追踪 checksum |
| keep.d `/etc/atomdns` | 数据目录（config_custom.yaml、订阅规则、缓存、学习数据） | sysupgrade `find` 递归展开 |

自检：在路由器上跑 `sysupgrade -l | grep atomdns`，应同时列出 `/etc/config/atomdns` 和 `/etc/atomdns/` 下的文件；若只有前者说明 keep.d 没装进去。

> 若把 `config_dir` 改成了 `/etc/atomdns` 以外的路径，需自行把新路径加进 `/lib/upgrade/keep.d/luci-app-atomdns`，否则新目录不会被保留。

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
