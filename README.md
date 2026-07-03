# VPN Manager

基于 Clash Meta (mihomo) 的 Linux 服务器代理订阅管理工具。

通过自动切换代理节点，让云服务器能访问不可达的网络站点。

## 快速使用

```bash
./vpn-manager.sh status          # 查看引擎状态
./vpn-manager.sh start           # 启动代理
./vpn-manager.sh stop            # 停止代理
```

### 切换代理模式

```bash
./vpn-manager.sh mode rule       # 规则模式（国内直连，国外代理）
./vpn-manager.sh mode global     # 全局模式（所有流量走代理）
./vpn-manager.sh mode direct     # 直连模式
```

### 选择节点

```bash
./vpn-manager.sh select          # 交互式选择（上下键翻页，Enter 确认）
./vpn-manager.sh select "节点名"  # 直接指定节点
```

### 导入订阅

```bash
./vpn-manager.sh import url https://your-subscribe-url --name 我的订阅
./vpn-manager.sh list            # 查看所有节点
./vpn-manager.sh update          # 更新所有订阅
./vpn-manager.sh delete "订阅名"  # 删除订阅
```

### 测试代理是否生效

```bash
curl --proxy http://127.0.0.1:7890 ip.sb
# 或设置环境变量后直接 curl
export http_proxy=http://127.0.0.1:7890
export https_proxy=http://127.0.0.1:7890
curl ip.sb
```

### Web 管理面板

```bash
./vpn-manager.sh web --host 127.0.0.1 --port 8080
```

通过 SSH 隧道安全访问：

```bash
ssh -L 8080:127.0.0.1:8080 root@your-server
# 浏览器打开 http://127.0.0.1:8080
```

## 一键部署

```bash
git clone https://github.com/Handsec/vpn-manager.git
cd vpn-manager
sudo bash install.sh
```

## 功能

- CLI 命令行 + Web 面板双模式
- 交互式节点选择（上下键操作）
- 支持订阅 URL 导入 / 手动导入
- 支持 SS / SSR / VMess / Trojan / VLESS / Clash YAML
- 规则模式 / 全局模式 / 直连模式 一键切换
- 配置热重载
- systemd 服务管理

## 端口

| 端口 | 用途 |
|------|------|
| 7890 | 混合代理端口 (HTTP/SOCKS5) |
| 9090 | Clash API 端口 |
| 8080 | Web 管理面板（仅本地监听） |
