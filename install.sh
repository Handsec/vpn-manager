#!/bin/bash
# ============================================================
# VPN Manager — 一键安装脚本
# 支持离线安装（vendor/ 目录存在时自动走离线）
# ============================================================
# 用法:
#   sudo bash install.sh                                          # 自动检测本地代理端口
#   PROXY=http://127.0.0.1:7890 sudo bash install.sh              # 临时指定代理
#   SUBSCRIPTION_URL=https://xxx sudo bash install.sh              # 安装 + 自动导入订阅
#   SUBSCRIPTION_URL=... AUTO_START=true sudo bash install.sh     # 安装 + 导入 + 启动引擎 + 设代理
# ============================================================
set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn()  { echo -e "${YELLOW}[!]${NC} $1"; }
error() { echo -e "${RED}[✗]${NC} $1"; }
step()  { echo -e "\n${BLUE}━━━ $1 ━━━${NC}"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 代理检测优先级: PROXY 环境变量 > proxy.conf > 本地端口扫描
PROXY="${PROXY:-}"
if [ -z "$PROXY" ] && [ -f "$SCRIPT_DIR/proxy.conf" ]; then
    source "$SCRIPT_DIR/proxy.conf"
    PROXY="${PROXY:-}"
fi
if [ -z "$PROXY" ]; then
    for port in 7890 7891 1080 8080; do
        if curl -s --connect-timeout 1 --max-time 2 --proxy "http://127.0.0.1:$port" \
            -o /dev/null http://www.google.com &>/dev/null; then
            PROXY="http://127.0.0.1:$port"
            info "检测到本地代理: $PROXY"
            break
        fi
    done
fi

[ -n "$PROXY" ] && export http_proxy="$PROXY" https_proxy="$PROXY" HTTP_PROXY="$PROXY" HTTPS_PROXY="$PROXY"

VENDOR_DIR="$SCRIPT_DIR/vendor"

# 离线模式检测
HAS_VENDOR=0
if [ -d "$VENDOR_DIR" ] && [ -f "$VENDOR_DIR/mihomo" ]; then
    HAS_VENDOR=1
    info "检测到 vendor 目录，将使用离线安装"
fi

# 检测系统
detect_os() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release; OS=$ID; OS_VERSION=$VERSION_ID
    else
        OS=$(uname -s)
    fi
    info "系统: $OS $OS_VERSION"
}

detect_arch() {
    case "$(uname -m)" in
        x86_64)  ARCH="amd64" ;;
        aarch64) ARCH="arm64" ;;
        armv7l)  ARCH="armv7" ;;
        *)       error "不支持的架构: $(uname -m)"; exit 1 ;;
    esac
    info "架构: $ARCH"
}

install_system_deps() {
    step "系统依赖"

    # 离线模式：跳过系统包管理器（需要网络），假定系统已预装 python3
    if [ "$HAS_VENDOR" = "1" ]; then
        info "离线模式: 跳过系统包管理器，假定已安装 python3"
        # 验证 python3 可用
        if ! command -v python3 &>/dev/null; then
            error "离线模式下未检测到 python3，请先在目标机器上安装 Python 3"
            exit 1
        fi
        return 0
    fi

    case "$OS" in
        ubuntu|debian)
            apt-get update -qq 2>/dev/null && apt-get install -y -qq curl wget python3 python3-pip python3-venv unzip 2>/dev/null || warn "部分系统依赖安装失败，请手动安装 python3/pip/venv"
            ;;
        centos|rhel|almalinux|rocky|fedora)
            cmd="dnf install -y curl wget python3 python3-pip unzip"
            command -v dnf &>/dev/null || cmd="yum install -y curl wget python3 python3-pip unzip"
            $cmd 2>/dev/null || warn "部分系统依赖安装失败，请手动安装"
            ;;
        *)
            warn "未知系统，跳过系统依赖"
            ;;
    esac
    info "系统依赖完成"
}

install_mihomo() {
    step "安装 mihomo (Clash Meta)"

    if command -v mihomo &>/dev/null; then
        info "mihomo 已安装: $(mihomo --version | head -1)"
        return 0
    fi

    # 离线安装
    if [ "$HAS_VENDOR" = "1" ] && [ -f "$VENDOR_DIR/mihomo" ]; then
        cp "$VENDOR_DIR/mihomo" /usr/local/bin/mihomo
        chmod +x /usr/local/bin/mihomo
        info "mihomo 安装成功 (离线)"
        return 0
    fi

    # 在线下载
    warn "vendor 中未找到 mihomo，尝试在线下载..."
    VERSION=$VERSION
    [ -z "$VERSION" ] && VERSION="1.19.27"
    if command -v mihomo &>/dev/null; then
        info "mihomo 已存在"
        return 0
    fi

    warn "请手动下载 mihomo 到 /usr/local/bin/"
    warn "下载地址: https://github.com/MetaCubeX/mihomo/releases"
}

install_python_deps() {
    step "安装 Python 依赖"
    cd "$SCRIPT_DIR"

    # 创建虚拟环境
    INSTALL_DIR="/opt/vpn-manager"
    mkdir -p "$INSTALL_DIR"

    if [ ! -d "$INSTALL_DIR/venv" ]; then
        python3 -m venv "$INSTALL_DIR/venv"
        info "创建 Python 虚拟环境"
    fi

    # 离线安装
    if [ "$HAS_VENDOR" = "1" ] && [ -d "$VENDOR_DIR/wheels" ] && ls "$VENDOR_DIR/wheels/"*.whl &>/dev/null 2>&1; then
        info "从 vendor/wheels 离线安装 Python 依赖..."
        "$INSTALL_DIR/venv/bin/pip" install --no-index --find-links "$VENDOR_DIR/wheels" -r "$SCRIPT_DIR/requirements.txt" -q \
            && info "Python 依赖安装完成 (离线)" && _setup_entrypoint && return 0
    fi

    # 在线安装
    "$INSTALL_DIR/venv/bin/pip" install -r "$SCRIPT_DIR/requirements.txt" -q 2>/dev/null || \
    "$INSTALL_DIR/venv/bin/pip" install -r "$SCRIPT_DIR/requirements.txt" -q \
        -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com 2>/dev/null || \
    "$INSTALL_DIR/venv/bin/pip" install fastapi uvicorn jinja2 httpx pyyaml pydantic click pick -q 2>/dev/null || \
    warn "pip 安装失败，请手动执行: pip install -r requirements.txt"

    info "Python 依赖安装完成"
    _setup_entrypoint
}

_setup_entrypoint() {
    # 复制项目文件到安装目录
    cp -r "$SCRIPT_DIR"/* "$INSTALL_DIR/" 2>/dev/null || true
    cp -r "$SCRIPT_DIR"/.[!.]* "$INSTALL_DIR/" 2>/dev/null || true
    chmod +x "$INSTALL_DIR/vpn-manager.sh" 2>/dev/null || true

    # 创建 /usr/local/bin/vpn-manager 命令（供 systemd 等非交互环境使用）
    cat > /usr/local/bin/vpn-manager << 'EOF'
#!/bin/bash
cd /opt/vpn-manager
/opt/vpn-manager/venv/bin/python3 main.py "$@"
EOF
    chmod +x /usr/local/bin/vpn-manager
    info "创建命令: vpn-manager"

    # 创建 vpn shell 函数（支持在当前 shell 注入代理环境变量）
    cat > /etc/profile.d/vpn-manager.sh << 'FUNC_EOF'
# vpn-manager shell function — 支持自动设置代理环境变量
vpn() {
    /opt/vpn-manager/venv/bin/python3 /opt/vpn-manager/main.py "$@"
    local rc=$?
    case "$1" in
        start|restart)
            [ -f /etc/profile.d/proxy.sh ] && source /etc/profile.d/proxy.sh
            ;;
        stop)
            unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY NO_PROXY
            ;;
    esac
    return $rc
}
FUNC_EOF
    chmod +x /etc/profile.d/vpn-manager.sh

    # 确保当前 shell 和 .bashrc 加载此函数
    source /etc/profile.d/vpn-manager.sh 2>/dev/null || true
    if ! grep -q "vpn-manager.sh" /root/.bashrc 2>/dev/null; then
        echo 'source /etc/profile.d/vpn-manager.sh' >> /root/.bashrc
    fi
    info "创建 vpn 命令 (shell 函数，支持自动代理环境)"
}

setup_workdir() {
    step "配置工作目录"
    local work_dir="/etc/vpn-manager"
    mkdir -p "$work_dir"

    # 复制 GeoIP 数据库
    if [ -f "$VENDOR_DIR/geoip.dat" ] && [ ! -f "$work_dir/geoip.dat" ]; then
        cp "$VENDOR_DIR/geoip.dat" "$work_dir/geoip.dat" && info "GeoIP 数据库已安装"
    fi
    if [ -f "$VENDOR_DIR/geosite.dat" ] && [ ! -f "$work_dir/geosite.dat" ]; then
        cp "$VENDOR_DIR/geosite.dat" "$work_dir/geosite.dat" && info "GeoSite 数据库已安装"
    fi
    if [ ! -f "$work_dir/geoip.dat" ]; then
        warn "GeoIP 数据库缺失，可稍后手动下载放到 $work_dir/"
    fi

    # Web UI
    cp -r "$SCRIPT_DIR/web" "$INSTALL_DIR/" 2>/dev/null || true

    info "工作目录: $work_dir"
}

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
ExecStart=/opt/vpn-manager/venv/bin/python3 /opt/vpn-manager/main.py web --host 127.0.0.1 --port 8080
Restart=on-failure
RestartSec=5
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
SERVICE
    systemctl daemon-reload
    info "服务已创建: systemctl start vpn-manager"
}

auto_setup_proxy() {
    [ -z "$SUBSCRIPTION_URL" ] && return 0

    step "自动配置代理"
    info "检测到 SUBSCRIPTION_URL，开始自动化配置..."

    # 1. 导入订阅
    echo ""
    /opt/vpn-manager/venv/bin/python3 /opt/vpn-manager/main.py import url "$SUBSCRIPTION_URL" --name "自动导入"
    IMPORT_EXIT=$?

    if [ "$IMPORT_EXIT" -ne 0 ]; then
        warn "订阅导入失败，跳过后续自动化步骤"
        warn "可手动执行: vpn-manager import url <订阅链接>"
        return 0
    fi

    # 2. 如果 AUTO_START=true，启动引擎并配置系统代理
    if [ "${AUTO_START:-false}" = "true" ]; then
        echo ""
        info "启动 mihomo 引擎..."
        /opt/vpn-manager/venv/bin/python3 /opt/vpn-manager/main.py start

        echo ""
        info "设置系统代理环境变量..."
        cat > /etc/profile.d/proxy.sh << 'PROXY_EOF'
export ALL_PROXY=http://127.0.0.1:7890
export http_proxy=http://127.0.0.1:7890
export https_proxy=http://127.0.0.1:7890
export NO_PROXY=localhost,127.0.0.1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16
PROXY_EOF
        chmod +x /etc/profile.d/proxy.sh
        # 同时追加到 ~/.bashrc
        grep -q "proxy.sh" /root/.bashrc 2>/dev/null || echo 'source /etc/profile.d/proxy.sh' >> /root/.bashrc
        source /etc/profile.d/proxy.sh

        info "自动化配置完成！"
        echo ""
        echo -e "${GREEN}  现在可以测试:${NC}"
        echo "    curl -s -o /dev/null -w '%{http_code}' https://www.google.com"
        echo ""
        echo "  或重新登录后直接访问:"
        echo "    curl https://www.google.com"
    else
        info "订阅已导入。"
        echo ""
        echo "  下一步:"
        echo "    1. vpn-manager start              # 启动引擎"
        echo "    2. vpn-manager select              # 选择节点（交互式）"
        echo "    3. 参考 README 设置系统代理环境变量"
        echo ""
        echo "  如果用 AUTO_START=true 可一键全部完成:"
        echo "    SUBSCRIPTION_URL=https://xxx AUTO_START=true sudo bash install.sh"
    fi
}

show_summary() {
    echo ""
    echo -e "${GREEN}============================================${NC}"
    echo -e "${GREEN}  安装完成！${NC}"
    echo -e "${GREEN}============================================${NC}"
    echo ""
    echo "  常用命令:"
    echo "    vpn-manager status              # 查看状态"
    echo "    vpn-manager start               # 启动代理"
    echo "    vpn-manager select              # 交互式选节点"
    echo "    vpn-manager import url <URL>    # 导入订阅"
    echo "    vpn-manager web --port 8080     # Web 面板"
    echo ""
    echo "  快捷命令: vpn (等同于 vpn-manager)"
    echo ""
}

# ============ Main ============
main() {
    echo ""
    echo -e "${CYAN}============================================${NC}"
    echo -e "${CYAN}   VPN Manager 安装程序${NC}"
    echo -e "${CYAN}============================================${NC}"
    echo ""

    detect_os
    detect_arch

    if [ "$(id -u)" -ne 0 ]; then
        error "请以 root 用户运行: sudo bash install.sh"
        exit 1
    fi

    # 自动下载依赖（vendor 不存在时）
    if [ "$HAS_VENDOR" = "0" ]; then
        step "自动下载依赖"
        info "未检测到 vendor 目录，将自动下载所需依赖..."
        if [ -f "$SCRIPT_DIR/download-deps.sh" ]; then
            bash "$SCRIPT_DIR/download-deps.sh" || warn "自动下载未完全成功，将尝试在线安装"
            # 重新检测 vendor
            if [ -d "$VENDOR_DIR" ] && [ -f "$VENDOR_DIR/mihomo" ]; then
                HAS_VENDOR=1
                info "依赖下载完成，继续安装"
            fi
        fi
    fi

    install_system_deps
    install_mihomo
    install_python_deps
    setup_workdir
    setup_service
    auto_setup_proxy
    show_summary
}

main "$@"
