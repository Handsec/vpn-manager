# VPN Manager

基于 Clash Meta (mihomo) 的 Linux 服务器代理订阅管理工具。通过自动切换代理节点，让云服务器能访问不可达的网络站点。

## 架构

```
┌─ Windows ───────────────────────────────┐
│  机场客户端 (Clash/v2ray) 监听 :7890      │
│  ssh -R 7890:localhost:7890 root@服务器   │  ← 手动端口映射（一次性引导）
└──────────┬───────────────────────────────┘
           │ 反向隧道
           ▼
┌─ 云服务器 ───────────────────────────────┐
│  localhost:7890 → Windows 机场代理        │  ← 下载依赖时使用
│                                          │
│  mihomo :7890（用自己的订阅节点）           │  ← 永久运行
│  /etc/profile.d/proxy.sh 自动设代理       │  ← 所有流量走 mihomo
└──────────────────────────────────────────┘
```

## 一键部署

### 前置条件

- **Windows**: 机场客户端运行中，HTTP 代理端口已知（Clash 默认 `7890`）
- **Linux 服务器**: 能 SSH 连接，已安装 Python 3

### 第一步：打通代理隧道

Windows 上打开 PowerShell 或 CMD，将本地代理端口映射到服务器：

```powershell
ssh -R 7890:localhost:7890 root@你的服务器IP
```

> `-R 7890:localhost:7890` 意思是将 Windows 本机的 `127.0.0.1:7890` 映射到服务器的 `127.0.0.1:7890`。这样服务器就能通过本机端口走 Windows 的机场上网。
>
> 如果机场端口不是 7890，替换成实际端口（如 1080、8080）。

### 第二步：一键安装

SSH 连上服务器后执行：

```bash
git clone https://github.com/Handsec/vpn-manager.git
cd vpn-manager
sudo bash install.sh
```

脚本自动完成：

| 步骤 | 说明 |
|------|------|
| 检测 `localhost:7890` | 找到 Windows 代理隧道 |
| 下载 mihomo + geoip + Python wheels | 走 Windows 代理下载所有依赖 |
| 安装 mihomo 到 `/usr/local/bin/` | 离线安装 |
| 安装 Python 依赖 | 从 vendor/wheels 离线安装 |
| 配置 systemd 服务 | 开机自启 |

> 安装完成后就可以关闭 Windows 的 SSH 隧道了，服务器已不再依赖它。

### 第三步：导入订阅并启动

```bash
# 导入订阅（会自动解析 SS/SSR/VMess/Trojan/VLESS/Clash YAML）
vpn import url https://你的订阅链接

# 启动代理
vpn start

# 验证代理是否生效
curl https://ip.sb
```

返回的 IP 应该是机场节点的 IP，不是服务器真实 IP。

### 第四步：全自动代理

`vpn start` 会自动配置系统代理：

- 写入 `/etc/profile.d/proxy.sh` — 新 SSH 登录自动设好代理
- 写入 `/etc/environment` — 系统全局代理变量

**以后每次 SSH 登录，curl 等命令默认就走代理了**，无需手动设置。

```bash
# 重新登录后直接测试
curl https://www.google.com
```

## 常用命令

### 引擎管理

```bash
vpn start           # 启动 mihomo + 配置系统代理
vpn stop            # 停止 mihomo + 清理系统代理
vpn restart         # 重启
vpn status          # 查看状态、节点数、端口
```

### 代理模式

```bash
vpn mode rule       # 规则模式（国内直连，国外代理）[默认]
vpn mode global     # 全局模式（所有流量走代理）
vpn mode direct     # 直连模式
```

### 订阅管理

```bash
vpn import url https://你的订阅链接           # 从 URL 导入
vpn import text "$(cat config.yaml)"           # 从文本导入
vpn list                                       # 查看所有节点
vpn update                                     # 更新全部订阅
vpn delete 订阅名                               # 删除订阅
```

### 节点选择

```bash
vpn select          # 交互式选择（方向键移动，Enter 确认）
vpn select 节点名    # 直接指定
```

### Web 面板

```bash
vpn web --host 127.0.0.1 --port 8080

# 通过 SSH 隧道安全访问
ssh -L 8080:127.0.0.1:8080 root@你的服务器
# 浏览器打开 http://127.0.0.1:8080
```

## 离线部署

适用于服务器无法直连 GitHub 且没有 Windows 代理可用的场景。

**有网的机器上**：

```bash
bash download-deps.sh
# 生成 vpn-manager-linux-amd64-v1.19.27.tar.gz
```

**传到目标服务器**：

```bash
scp vpn-manager-*.tar.gz root@服务器:~/
tar -xzf vpn-manager-*.tar.gz
cd vpn-manager
sudo bash install.sh
```

## 功能

- CLI 命令行 + Web 面板双模式
- 交互式节点选择（上下键操作）
- 支持 SS / SSR / VMess / Trojan / VLESS / Clash YAML
- 规则模式 / 全局模式 / 直连模式 一键切换
- 配置热重载
- systemd 服务管理，开机自启
- 系统代理自动配置（profile.d + /etc/environment）
- 离线部署支持

## 端口

| 端口 | 用途 |
|------|------|
| 7890 | 混合代理端口 (HTTP/SOCKS5) |
| 9090 | Clash API 端口 |
| 8080 | Web 管理面板（仅本地监听） |

## 免责声明 / 合规说明

1. **合法用途**。本工具仅用于以下合法场景：
   - 服务器通过代理访问开源软件仓库、镜像站、API 服务等正常开发资源
   - 企业内部网络通过代理进行安全审计、流量管控
   - 个人合法合规的网络访问需求

2. **禁止违法用途**。严禁使用本工具从事任何违反中华人民共和国法律法规的活动，包括但不限于：
   - 非法侵入、攻击、破坏国家关键信息基础设施
   - 传播违法信息、从事违法犯罪活动
   - 用于任何形式的网络攻击、渗透测试（未获授权的情况下）

3. **使用者责任**。本工具仅为技术实现，使用者应当自行遵守所在地法律及云服务商的使用条款。因不当使用产生的法律责任由使用者自行承担。

4. **代理节点来源**。本工具不提供任何代理节点、订阅链接或机场服务。节点来源由用户自行获取，用户应当确保所使用节点的合法性。
