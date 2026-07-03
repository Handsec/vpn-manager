# vpn-manager

基于 Clash Meta (mihomo) 的 Linux 服务器代理订阅管理工具。

## 一键部署

```bash
git clone https://github.com/Handsec/vpn-manager.git
cd vpn-manager
sudo bash install.sh
```

## 快速使用

```bash
# 导入订阅
vpn-manager import url https://your-subscribe-url --name 我的订阅

# 启动代理
vpn-manager start

# 切换模式
vpn-manager mode rule    # 规则模式（国内直连，国外代理）
vpn-manager mode global  # 全局模式
vpn-manager mode direct  # 直连模式

# 启动 Web 管理面板
vpn-manager web --port 8080

# 查看状态
vpn-manager status
```

## 功能

- CLI 命令行 + Web 面板双模式
- 支持订阅 URL 导入 / 手动导入
- 支持 SS / SSR / VMess / Trojan / VLESS / Clash YAML
- 规则模式 / 全局模式 / 直连模式 一键切换
- 配置热重载
- systemd 服务管理
