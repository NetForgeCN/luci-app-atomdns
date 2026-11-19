include $(TOPDIR)/rules.mk

LUCI_TITLE:=AtomDNS WebUI Control
LUCI_DEPENDS:=+atomdns
LUCI_PKGARCH:=all

include $(TOPDIR)/feeds/luci/luci.mk

define Package/$(PKG_NAME)/description
 AtomDNS 控制面板：查看运行状态与版本、配置 DNS/WebUI 端口，并提供一键打开内置 WebUI 的按钮。
endef

$(call BuildPackage,$(PKG_NAME))
