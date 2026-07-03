#!/bin/bash
set -e

# ============================================================
# VPN Manager — One-Click Install Script
# ============================================================
# 支持的系统: Ubuntu 20.04+, Debian 11+, CentOS 7+, AlmaLinux, Rocky Linux
# 架构: amd64, arm64, armv7
# ============================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

info()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn()  { echo -e "${YELLOW}[!]${NC} $1"; }
error() { echo -e "${RED}[✗]${NC} $1"; }
step()  { echo -e "\n${BLUE}━━━ $1 ━━━${NC}"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/opt/vpn-manager"
WORK_DIR="/etc/vpn-manager"
BIN_DIR="/usr/local/bin"

# --- Detect OS ---
detect_os() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS=$ID
        OS_VERSION=$VERSION_ID
    else
        OS=$(uname -s)
    fi
    echo "系统: $OS $OS_VERSION"
}

# --- Detect Architecture ---
detect_arch() {
    case "$(uname -m)" in
        x86_64)  ARCH="amd64" ;;
        aarch64) ARCH="arm64" ;;
        armv7l)  ARCH="armv7" ;;
        *)       error "不支持的架构: $(uname -m)"; exit 1 ;;
    esac
    echo "架构: $ARCH"
}

# --- Install System Dependencies ---
install_deps() {
    step "安装系统依赖"

    case "$OS" in
        ubuntu|debian)
            apt-get update -qq
            apt-get install -y -qq curl wget python3 python3-pip python3-venv unzip || true
            ;;
        centos|rhel|almalinux|rocky|fedora)
            if command -v dnf &>/dev/null; then
                dnf install -y curl wget python3 python3-pip unzip
            else
                yum install -y curl wget python3 python3-pip unzip
            fi
            ;;
        openwrt|lede)
            opkg update
            opkg install python3 python3-pip curl wget unzip
            ;;
        *)
            warn "未知系统: $OS，尝试使用 pip 安装 Python 依赖"
            ;;
    esac
    info "系统依赖安装完成"
}

# --- Install mihomo ---
install_mihomo() {
    step "安装 mihomo (Clash Meta)"

    if command -v mihomo &>/dev/null; then
        info "mihomo 已安装: $(mihomo --version | head -1)"
        return 0
    fi

    # Determine the latest version
    info "获取最新版本信息..."
    LATEST_URL=$(curl -s https://api.github.com/repos/MetaCubeX/mihomo/releases/latest \
        | grep "browser_download_url.*mihomo-linux-${ARCH}" \
        | grep -v "gz" \
        | head -1 \
        | cut -d '"' -f 4)

    if [ -z "$LATEST_URL" ]; then
        # Fallback: try to find any compatible release
        LATEST_URL=$(curl -s https://api.github.com/repos/MetaCubeX/mihomo/releases/latest \
            | grep "browser_download_url" \
            | grep "linux-${ARCH}" \
            | grep -v "gz" \
            | head -1 \
            | cut -d '"' -f 4)
    fi

    if [ -z "$LATEST_URL" ]; then
        warn "无法自动获取 mihomo 下载链接，请手动安装"
        warn "下载地址: https://github.com/MetaCubeX/mihomo/releases"
        return 1
    fi

    info "下载: $LATEST_URL"
    TMP_DIR=$(mktemp -d)
    cd "$TMP_DIR"

    if curl -L -o mihomo.tar.gz "$LATEST_URL" --connect-timeout 10 --max-time 120; then
        tar -xzf mihomo.tar.gz 2>/dev/null || unzip -o mihomo.tar.gz 2>/dev/null || true
        # Find the mihomo binary
        find . -name "mihomo*" -type f -executable | head -1 | while read f; do
            cp "$f" "$BIN_DIR/mihomo"
            chmod +x "$BIN_DIR/mihomo"
        done
        if [ -f "$BIN_DIR/mihomo" ]; then
            info "mihomo 安装成功: $BIN_DIR/mihomo"
        else
            # Try without executable bit
            find . -name "mihomo*" -type f | head -1 | while read f; do
                cp "$f" "$BIN_DIR/mihomo"
                chmod +x "$BIN_DIR/mihomo"
            done
        fi
    else
        warn "下载失败，请手动安装 mihomo"
    fi

    cd /
    rm -rf "$TMP_DIR"
}

# --- Install Python Dependencies ---
install_python_deps() {
    step "安装 Python 依赖"

    cd "$SCRIPT_DIR"

    # Create virtual environment if not exists
    if [ ! -d "$INSTALL_DIR/venv" ]; then
        python3 -m venv "$INSTALL_DIR/venv"
        info "创建 Python 虚拟环境"
    fi

    # Install requirements
    "$INSTALL_DIR/venv/bin/pip" install --upgrade pip -q
    "$INSTALL_DIR/venv/bin/pip" install -r requirements.txt -q
    info "Python 依赖安装完成"

    # Create symlink for vpn-manager command
    cat > "$BIN_DIR/vpn-manager" << 'EOF'
#!/bin/bash
cd /opt/vpn-manager
/opt/vpn-manager/venv/bin/python3 main.py "$@"
EOF
    chmod +x "$BIN_DIR/vpn-manager"
    info "创建命令: vpn-manager"
}

# --- Setup Working Directory ---
setup_workdir() {
    step "创建工作目录"

    mkdir -p "$WORK_DIR"
    mkdir -p "$INSTALL_DIR"

    # Copy project files
    cp -r "$SCRIPT_DIR"/* "$INSTALL_DIR/" 2>/dev/null || true
    cp -r "$SCRIPT_DIR"/.[!.]* "$INSTALL_DIR/" 2>/dev/null || true

    # Download GeoIP/GeoSite databases
    if [ ! -f "$WORK_DIR/geoip.dat" ]; then
        info "下载 GeoIP 数据库..."
        curl -L -o "$WORK_DIR/geoip.dat" \
            "https://github.com/MetaCubeX/meta-rules-dat/releases/download/latest/geoip.dat" \
            --connect-timeout 10 --max-time 60 2>/dev/null || \
        wget -O "$WORK_DIR/geoip.dat" \
            "https://github.com/MetaCubeX/meta-rules-dat/releases/download/latest/geoip.dat" \
            --timeout=10 2>/dev/null || \
        warn "GeoIP 下载失败，可稍后手动下载"
    fi

    if [ ! -f "$WORK_DIR/geosite.dat" ]; then
        info "下载 GeoSite 数据库..."
        curl -L -o "$WORK_DIR/geosite.dat" \
            "https://github.com/MetaCubeX/meta-rules-dat/releases/download/latest/geosite.dat" \
            --connect-timeout 10 --max-time 60 2>/dev/null || \
        wget -O "$WORK_DIR/geosite.dat" \
            "https://github.com/MetaCubeX/meta-rules-dat/releases/download/latest/geosite.dat" \
            --timeout=10 2>/dev/null || \
        warn "GeoSite 下载失败，可稍后手动下载"
    fi

    info "工作目录: $WORK_DIR"
}

# --- Create Systemd Service ---
setup_service() {
    step "配置系统服务"

    cat > /etc/systemd/system/vpn-manager.service << 'SERVICE'
[Unit]
Description=VPN Manager - Clash Meta Proxy Service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/vpn-manager
ExecStartPre=/usr/local/bin/mihomo -d /etc/vpn-manager --test
ExecStart=/opt/vpn-manager/venv/bin/python3 /opt/vpn-manager/main.py web --port 8080
Restart=on-failure
RestartSec=5
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
SERVICE

    systemctl daemon-reload
    info "服务文件已创建: vpn-manager.service"
    info "使用 systemctl start vpn-manager 启动服务"
    info "使用 systemctl enable vpn-manager 设置开机自启"
}

# --- Create Alias for Convenience ---
setup_alias() {
    # Add alias to .bashrc for root
    if ! grep -q "alias vpn=" /root/.bashrc 2>/dev/null; then
        echo 'alias vpn="vpn-manager"' >> /root/.bashrc
    fi
}

# --- Main ---
main() {
    echo ""
    echo -e "${CYAN}============================================${NC}"
    echo -e "${CYAN}   VPN Manager — One-Click Install${NC}"
    echo -e "${CYAN}   Clash Meta Subscription Manager${NC}"
    echo -e "${CYAN}============================================${NC}"
    echo ""

    detect_os
    detect_arch

    # Check root
    if [ "$(id -u)" -ne 0 ]; then
        error "请以 root 用户运行 (sudo bash install.sh)"
        exit 1
    fi

    install_deps
    install_mihomo
    install_python_deps
    setup_workdir
    setup_service
    setup_alias

    echo ""
    echo -e "${GREEN}============================================${NC}"
    echo -e "${GREEN}  安装完成！${NC}"
    echo -e "${GREEN}============================================${NC}"
    echo ""
    echo "  Web 管理面板:"
    echo "    vpn-manager web --port 8080"
    echo "    或 systemctl start vpn-manager"
    echo ""
    echo "  命令行管理:"
    echo "    vpn-manager status         查看状态"
    echo "    vpn-manager start          启动代理"
    echo "    vpn-manager stop           停止代理"
    echo "    vpn-manager mode rule      规则模式"
    echo "    vpn-manager mode global    全局模式"
    echo "    vpn-manager mode direct    直连模式"
    echo "    vpn-manager import url <URL>  导入订阅"
    echo "    vpn-manager list           查看节点"
    echo ""
    echo "  快捷命令: vpn (等同于 vpn-manager)"
    echo ""
}

main "$@"
