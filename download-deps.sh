#!/bin/bash
# ============================================================
# VPN Manager — 下载依赖并打包完整项目
# 在能上网的机器上运行，产出自包含压缩包
# ============================================================
# 用法:
#   bash download-deps.sh              # 下载依赖并打包
#   PROXY=http://127.0.0.1:7890 bash download-deps.sh  # 走代理下载
# ============================================================
set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn()  { echo -e "${YELLOW}[!]${NC} $1"; }
step()  { echo -e "\n${BLUE}━━━ $1 ━━━${NC}"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENDOR_DIR="$SCRIPT_DIR/vendor"
WORK_DIR="$SCRIPT_DIR/vendor/work"
PROXY="${PROXY:-}"

mkdir -p "$VENDOR_DIR" "$WORK_DIR"

CURL_BASE="curl -L"
[ -n "$PROXY" ] && CURL_BASE="$CURL_BASE --proxy $PROXY" && info "使用代理下载"

# 检测架构
ARCH="amd64"
case "$(uname -m)" in
    aarch64|arm64) ARCH="arm64" ;;
    armv7l)        ARCH="armv7" ;;
esac

if [ "$(uname -s)" = "Linux" ]; then SUFFIX="linux-${ARCH}"
elif [ "$(uname -s)" = "Darwin" ]; then SUFFIX="darwin-${ARCH}"
else SUFFIX="linux-${ARCH}"; fi

# ---- 1. 获取 mihomo 版本 ----
step "获取 mihomo 版本"
VERSION=$($CURL_BASE -s --connect-timeout 10 --max-time 15 \
    "https://api.github.com/repos/MetaCubeX/mihomo/releases/latest" 2>/dev/null \
    | grep '"tag_name"' | head -1 | cut -d '"' -f 4 | sed 's/^v//')
[ -z "$VERSION" ] && VERSION="1.19.27" && warn "未获取到最新版本，默认 v$VERSION"
info "mihomo v$VERSION"

# ---- 2. 下载 mihomo ----
MIHOMO_FILE="mihomo-linux-${ARCH}-v${VERSION}.gz"
MIHOMO_URL="https://github.com/MetaCubeX/mihomo/releases/download/v${VERSION}/${MIHOMO_FILE}"
[ -f "$VENDOR_DIR/mihomo" ] && info "mihomo 已存在，跳过" || {
    step "下载 mihomo"
    # 多镜像重试
    for url in "$MIHOMO_URL" "https://ghproxy.com/$MIHOMO_URL" \
        "https://github.com/MetaCubeX/mihomo/releases/download/v${VERSION}/${MIHOMO_FILE}"; do
        info "尝试: ${url:0:60}..."
        $CURL_BASE --connect-timeout 10 --max-time 120 -o "$VENDOR_DIR/tmp.gz" "$url" 2>/dev/null && break
    done
    if [ -f "$VENDOR_DIR/tmp.gz" ] && [ -s "$VENDOR_DIR/tmp.gz" ]; then
        gunzip -c "$VENDOR_DIR/tmp.gz" > "$VENDOR_DIR/mihomo" 2>/dev/null
        chmod +x "$VENDOR_DIR/mihomo"
        mv "$VENDOR_DIR/tmp.gz" "$VENDOR_DIR/mihomo.gz"
        info "mihomo 下载完成 ($(du -h "$VENDOR_DIR/mihomo" | cut -f1))"
    else
        warn "mihomo 下载失败，可手动下载放入 vendor/"
        rm -f "$VENDOR_DIR/tmp.gz"
    fi
}

# ---- 3. 下载 GeoIP/GeoSite ----
download_geo() {
    local name="$1" url="$2" out="$VENDOR_DIR/$1"
    [ -f "$out" ] && [ -s "$out" ] && return 0
    for u in "$url" "https://ghproxy.com/$url" \
        "$(echo "$url" | sed 's|https://github.com/\(.*\)/releases/download/latest/\(.*\)|https://cdn.jsdelivr.net/gh/\1@release/\2|')"; do
        info "  尝试: ${u:0:50}..."
        $CURL_BASE --connect-timeout 10 --max-time 60 -o "$out" "$u" 2>/dev/null && [ -s "$out" ] && return 0
    done
    return 1
}

step "下载 GeoIP/GeoSite"
download_geo "geoip.dat" "https://github.com/MetaCubeX/meta-rules-dat/releases/download/latest/geoip.dat" \
    && info "GeoIP 下载完成" || warn "GeoIP 下载失败"
download_geo "geosite.dat" "https://github.com/MetaCubeX/meta-rules-dat/releases/download/latest/geosite.dat" \
    && info "GeoSite 下载完成" || warn "GeoSite 下载失败"

# ---- 4. 下载 Python wheels ----
step "下载 Python 依赖"
if [ -d "$VENDOR_DIR/wheels" ] && ls "$VENDOR_DIR/wheels/"*.whl &>/dev/null 2>&1; then
    info "Python wheels 已存在，跳过"
else
    mkdir -p "$VENDOR_DIR/wheels"
    pip download -r "$SCRIPT_DIR/requirements.txt" -d "$VENDOR_DIR/wheels" 2>/dev/null \
        || $CURL_BASE -s "https://api.github.com/repos/..." 2>/dev/null \
        || warn "pip download 失败，服务器上 install.sh 会自动尝试在线安装"
    ls "$VENDOR_DIR/wheels/"*.whl &>/dev/null && info "Python wheels 下载完成 ($(ls "$VENDOR_DIR/wheels/"*.whl 2>/dev/null | wc -l) 个)" \
        || warn "无 wheel 文件，服务器将尝试在线安装"
fi

# ---- 5. 打包完整项目 ----
step "打包完整项目"
PACKAGE="vpn-manager-${SUFFIX}-v${VERSION}.tar.gz"
cd "$SCRIPT_DIR"
tar -czf "$PACKAGE" \
    --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
    --exclude='venv' --exclude='.venv' --exclude='config.yaml' \
    --exclude='.env' --exclude='*.tar.gz' \
    . 2>/dev/null

info "✓ 自包含压缩包已生成: $PACKAGE"
info "  大小: $(du -h "$PACKAGE" | cut -f1)"
echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  下载完成，拿去服务器安装吧！${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo "  上传到服务器:"
echo "    scp $PACKAGE root@你的服务器:~/"
echo ""
echo "  在服务器上:"
echo "    tar -xzf $PACKAGE"
echo "    cd vpn-manager"
echo "    sudo bash install.sh"
echo ""
