#!/bin/bash
# ============================================================
# VPN Manager — 本地下载所有依赖，打包供服务器离线安装
# 在本地能访问 GitHub 的机器上运行
# ============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENDOR_DIR="$SCRIPT_DIR/vendor"
WORK_DIR="$SCRIPT_DIR/vendor/work"
PROXY="${PROXY:-}"

mkdir -p "$VENDOR_DIR"
mkdir -p "$WORK_DIR"

info()  { echo -e "\033[0;32m[✓]\033[0m $1"; }
warn()  { echo -e "\033[1;33m[!]\033[0m $1"; }
step()  { echo -e "\n\033[0;34m━━━ $1 ━━━\033[0m"; }

CURL_BASE="curl -L"

# 检测本地架构
ARCH="amd64"
case "$(uname -m)" in
    aarch64) ARCH="arm64" ;;
    armv7l)  ARCH="armv7" ;;
esac

if [ "$(uname -s)" = "Linux" ]; then
    SUFFIX="linux-${ARCH}"
    PYTHON="python3"
elif [ "$(uname -s)" = "Darwin" ]; then
    SUFFIX="darwin-${ARCH}"
    PYTHON="python3"
else
    # Windows 用 Linux 的包
    SUFFIX="linux-${ARCH}"
    PYTHON="python"
fi

if [ -n "$PROXY" ]; then
    CURL_BASE="$CURL_BASE --proxy $PROXY"
    info "使用代理: $PROXY"
fi

# 1. 获取最新 mihomo 版本
step "获取 mihomo 最新版本"
VERSION=$($CURL_BASE -s --connect-timeout 10 --max-time 15 \
    "https://api.github.com/repos/MetaCubeX/mihomo/releases/latest" 2>/dev/null \
    | grep '"tag_name"' | head -1 | cut -d '"' -f 4 | sed 's/^v//')

if [ -z "$VERSION" ]; then
    warn "无法获取版本号，默认 v1.19.27"
    VERSION="1.19.27"
fi
info "mihomo 版本: v$VERSION"

# 2. 下载 mihomo
MIHOMO_FILE="mihomo-linux-${ARCH}-v${VERSION}.gz"
MIHOMO_URL="https://github.com/MetaCubeX/mihomo/releases/download/v${VERSION}/${MIHOMO_FILE}"

if [ ! -f "$VENDOR_DIR/mihomo.gz" ]; then
    step "下载 mihomo"
    info "下载: $MIHOMO_URL"
    $CURL_BASE --connect-timeout 10 --max-time 120 -o "$VENDOR_DIR/mihomo.gz" "$MIHOMO_URL"
    # 解压后重命名为 mihomo
    gunzip -c "$VENDOR_DIR/mihomo.gz" > "$VENDOR_DIR/mihomo" 2>/dev/null
    chmod +x "$VENDOR_DIR/mihomo"
    info "mihomo 下载完成"
else
    info "mihomo 已存在，跳过"
fi

# 3. 下载 GeoIP 数据库
step "下载 GeoIP/GeoSite 数据库"
if [ ! -f "$VENDOR_DIR/geoip.dat" ]; then
    info "下载 GeoIP..."
    $CURL_BASE --connect-timeout 10 --max-time 60 \
        -o "$VENDOR_DIR/geoip.dat" \
        "https://github.com/MetaCubeX/meta-rules-dat/releases/download/latest/geoip.dat"
    info "GeoIP 下载完成"
else
    info "GeoIP 已存在，跳过"
fi

if [ ! -f "$VENDOR_DIR/geosite.dat" ]; then
    info "下载 GeoSite..."
    $CURL_BASE --connect-timeout 10 --max-time 60 \
        -o "$VENDOR_DIR/geosite.dat" \
        "https://github.com/MetaCubeX/meta-rules-dat/releases/download/latest/geosite.dat"
    info "GeoSite 下载完成"
else
    info "GeoSite 已存在，跳过"
fi

# 4. 下载 Python 依赖的 wheel 包
step "下载 Python 依赖 (wheels)"
if [ ! -d "$VENDOR_DIR/wheels" ] || [ -z "$(ls -A "$VENDOR_DIR/wheels" 2>/dev/null)" ]; then
    mkdir -p "$VENDOR_DIR/wheels"
    info "下载 pip 依赖到 vendor/wheels/ ..."
    pip download -r "$SCRIPT_DIR/requirements.txt" -d "$VENDOR_DIR/wheels" 2>/dev/null || \
    $PYTHON -m pip download -r "$SCRIPT_DIR/requirements.txt" -d "$VENDOR_DIR/wheels" || \
    warn "pip download 失败，需要服务器联网安装"
    info "Python wheels 下载完成"
else
    info "Python wheels 已存在，跳过"
fi

# 5. 打压缩包
step "打包"
PACKAGE_NAME="vpn-manager-deps-${SUFFIX}-v${VERSION}.tar.gz"
cd "$SCRIPT_DIR"
tar -czf "$PACKAGE_NAME" \
    vendor/mihomo vendor/mihomo.gz \
    vendor/geoip.dat vendor/geosite.dat \
    vendor/wheels/ 2>/dev/null || true

info "依赖包已生成: $PACKAGE_NAME"
info "大小: $(du -h "$PACKAGE_NAME" | cut -f1)"

echo ""
echo "============================================"
echo "  下一步：上传到服务器"
echo "============================================"
echo "  scp $PACKAGE_NAME root@你的服务器:/root/"
echo "  scp -r * root@你的服务器:/opt/vpn-manager/"
echo ""
echo "  服务器上运行 install.sh 即可离线安装"
echo "============================================"
