#!/usr/bin/env python3
"""
VPN Manager — Clash Meta (mihomo) subscription management tool for Linux servers.

Usage:
  python3 main.py web                  # Start web dashboard
  python3 main.py start                # Start mihomo engine
  python3 main.py stop                 # Stop mihomo engine
  python3 main.py restart              # Restart mihomo engine
  python3 main.py status               # Show engine status
  python3 main.py mode [global|rule|direct]  # Switch proxy mode
  python3 main.py select [name]        # Select proxy node (interactive if no name)
  python3 main.py import url <URL> [--name NAME]   # Import subscription from URL
  python3 main.py import text <CONTENT> [--name NAME]  # Import subscription from text
  python3 main.py list                 # List subscriptions and proxies
  python3 main.py delete <name>        # Delete a subscription
  python3 main.py install              # Install mihomo and dependencies
  python3 main.py update               # Update all subscriptions
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
from pathlib import Path

import click

from vpn_manager.config import ConfigManager
from vpn_manager.engine import EngineManager
from vpn_manager.models import ProxyMode
from vpn_manager.subscription import fetch_subscription, parse_subscription_text


# Ensure we're in the right directory
base_dir = Path(__file__).parent
os.chdir(base_dir)

cfg = ConfigManager()
eng = EngineManager(cfg)


@click.group()
def cli():
    """VPN Manager — Clash Meta 订阅管理工具"""
    pass


@cli.command()
@click.option("--host", default="0.0.0.0", help="监听地址")
@click.option("--port", default=8080, help="监听端口", type=int)
@click.option("--no-open", is_flag=True, help="不自动打开浏览器")
def web(host, port, no_open):
    """启动 Web 管理面板"""
    from vpn_manager.webapp import create_app

    app = create_app(cfg, eng)

    if not no_open:
        click.echo(f"Web 面板启动中: http://{host}:{port}")
    else:
        click.echo(f"Web 面板地址: http://{host}:{port}")

    import uvicorn
    uvicorn.run(app, host=host, port=port, log_level="info")


PROXY_SH = "/etc/profile.d/proxy.sh"
PROXY_ENV = "/etc/environment"

SYSTEM_PROXY_SH = """export ALL_PROXY=http://127.0.0.1:7890
export http_proxy=http://127.0.0.1:7890
export https_proxy=http://127.0.0.1:7890
export NO_PROXY=localhost,127.0.0.1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16
"""

SYSTEM_PROXY_ENV = """http_proxy=http://127.0.0.1:7890
https_proxy=http://127.0.0.1:7890
ALL_PROXY=http://127.0.0.1:7890
NO_PROXY=localhost,127.0.0.1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16
"""


def _write_proxy_config():
    """Write system-wide proxy configuration files."""
    try:
        with open(PROXY_SH, "w") as f:
            f.write(SYSTEM_PROXY_SH)
    except PermissionError:
        return False

    try:
        with open(PROXY_ENV, "r") as f:
            content = f.read()
        if "http_proxy=http://127.0.0.1:7890" not in content:
            with open(PROXY_ENV, "a") as f:
                f.write("\n" + SYSTEM_PROXY_ENV)
    except (PermissionError, FileNotFoundError):
        try:
            with open(PROXY_ENV, "w") as f:
                f.write(SYSTEM_PROXY_ENV)
        except PermissionError:
            return False

    # 确保 shell 函数可用（旧安装无需重装）
    sh_func = "/etc/profile.d/vpn-manager.sh"
    if not os.path.exists(sh_func):
        try:
            with open(sh_func, "w") as f:
                f.write('vpn() {\n'
                        '    /opt/vpn-manager/venv/bin/python3 /opt/vpn-manager/main.py "$@"\n'
                        '    local rc=$?\n'
                        '    case "$1" in\n'
                        '        start) [ -f /etc/profile.d/proxy.sh ] && . /etc/profile.d/proxy.sh ;;\n'
                        '        stop)  unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY NO_PROXY ;;\n'
                        '    esac\n'
                        '    return $rc\n'
                        '}\n')
        except PermissionError:
            pass

    return True


def _remove_proxy_config():
    """Remove system-wide proxy configuration files."""
    removed = False
    for path in [PROXY_SH]:
        try:
            if os.path.exists(path):
                os.remove(path)
                removed = True
        except PermissionError:
            pass

    try:
        if os.path.exists(PROXY_ENV):
            with open(PROXY_ENV, "r") as f:
                lines = f.readlines()
            keep = [l for l in lines if "http_proxy" not in l and "https_proxy" not in l and "ALL_PROXY" not in l and "NO_PROXY" not in l]
            with open(PROXY_ENV, "w") as f:
                f.writelines(keep)
            removed = True
    except PermissionError:
        pass

    return removed


@cli.command()
def start():
    """启动 mihomo 引擎"""
    result = eng.start()
    click.echo(result)

    if not "错误" in result and not "已在运行" in result:
        if _write_proxy_config():
            click.echo("系统代理已配置，重新登录后所有流量自动走 mihomo 规则")
            click.echo("运行 source /etc/profile.d/proxy.sh 立即当前 shell 生效")


@cli.command()
def stop():
    """停止 mihomo 引擎"""
    result = eng.stop()
    click.echo(result)

    if _remove_proxy_config():
        click.echo("系统代理配置已清理")


@cli.command()
def restart():
    """重启 mihomo 引擎"""
    result = eng.restart()
    click.echo(result)


@cli.command()
def status():
    """查看引擎状态"""
    s = eng.get_status()
    mode = cfg.get_mode()
    version = eng.get_version()

    click.echo(f"引擎状态: {'● 运行中' if s.value == 'running' else '○ 已停止'}")
    click.echo(f"代理模式: {mode.value}")
    click.echo(f"引擎版本: {version}")

    if s.value == "running":
        all_proxies = cfg.get_all_proxies()
        click.echo(f"节点总数: {len(all_proxies)}")
        click.echo(f"HTTP 端口: {cfg.config.server.mixed_port}")
        click.echo(f"API 端口: {cfg.config.server.api_port}")


@cli.command()
@click.argument("mode", type=click.Choice(["global", "rule", "direct"]))
def mode(mode):
    """切换代理模式 (global/rule/direct)"""
    pm = ProxyMode(mode)
    result = eng.switch_mode(pm)
    click.echo(result)


@cli.command()
@click.argument("proxy_name", required=False)
@click.option("--group", default="PROXY", help="代理组名称 (默认: PROXY)")
def select(proxy_name, group):
    """选择代理节点（不带参数时进入交互式选择）"""
    if not proxy_name:
        _interactive_select(group)
        return
    result = eng.select_proxy(group, proxy_name)
    click.echo(result)


def _interactive_select(default_group="PROXY"):
    """Interactive proxy selection with arrow keys."""
    from pick import pick

    # Check engine status
    status = eng.get_status()
    if status.value != "running":
        click.echo("引擎未运行，请先启动: vpn-manager start")
        return

    # Get proxy groups from mihomo API
    proxies_data = eng.get_proxies()
    groups = {}
    for name, info in proxies_data.items():
        if info.get("type") in ("Selector", "URLTest", "Fallback"):
            groups[name] = {
                "type": info.get("type"),
                "now": info.get("now", ""),
                "all": info.get("all", []),
            }

    if not groups:
        click.echo("未获取到代理组信息")
        return

    # If multiple groups, let user pick group first
    group_names = list(groups.keys())
    target_group = default_group if default_group in group_names else group_names[0]
    if len(group_names) > 1:
        opts = [f"{g}  (当前: {groups[g]['now']})" for g in group_names]
        selected, idx = pick(opts, "选择代理组 (↑↓ 键移动, Enter 确认):")
        target_group = group_names[idx]
    else:
        target_group = group_names[0]

    # Show current selection and let user pick a proxy
    g = groups[target_group]
    if not g["all"]:
        click.echo(f"代理组 [{target_group}] 中无可用节点")
        return

    now = g["now"]
    opts = []
    for p in g["all"]:
        prefix = "● " if p == now else "  "
        opts.append(f"{prefix}{p}")

    selected, idx = pick(opts, f"代理组 [{target_group}] — 选择节点 (↑↓ 键移动, Enter 确认):")
    proxy_name = selected.replace("● ", "").replace("  ", "").strip()

    result = eng.select_proxy(target_group, proxy_name)
    click.echo(f"\n{result}")


@cli.command()
@click.argument("action", type=click.Choice(["url", "text"]))
@click.argument("source")
@click.option("--name", default=None, help="订阅名称")
def import_cmd(action, source, name):
    """导入订阅 (url/text)"""
    if action == "url":
        click.echo("正在获取订阅内容...")
        text = asyncio.run(fetch_subscription(source))
        if not text:
            click.echo("错误: 无法获取订阅内容", err=True)
            sys.exit(1)
        sub_name = name or "订阅-" + str(len(cfg.get_subscriptions()) + 1)
        proxies = parse_subscription_text(text)
        if not proxies:
            click.echo("错误: 未解析到任何代理节点", err=True)
            sys.exit(1)
        cfg.add_subscription(sub_name, source, proxies)
        click.echo(f"✓ 导入成功: {sub_name}")
        click.echo(f"  解析到 {len(proxies)} 个节点")
    else:  # text
        proxies = parse_subscription_text(source)
        if not proxies:
            click.echo("错误: 未解析到任何代理节点", err=True)
            sys.exit(1)
        sub_name = name or "手动-" + str(len(cfg.get_subscriptions()) + 1)
        cfg.add_subscription(sub_name, None, proxies)
        click.echo(f"✓ 导入成功: {sub_name}")
        click.echo(f"  解析到 {len(proxies)} 个节点")


@cli.command("list")
def list_cmd():
    """列出所有订阅和节点"""
    subs = cfg.get_subscriptions()
    if not subs:
        click.echo("暂无订阅，请使用 import 命令导入")
        return

    click.echo(f"共 {len(subs)} 个订阅:")
    click.echo("-" * 40)
    for name, sub in subs.items():
        proxy_types = {}
        for p in sub.proxies:
            ptype = p.get("type", "unknown")
            proxy_types[ptype] = proxy_types.get(ptype, 0) + 1
        type_str = ", ".join(f"{k}: {v}" for k, v in proxy_types.items())
        click.echo(f"  {name}")
        click.echo(f"    节点数: {len(sub.proxies)} ({type_str})")
        click.echo(f"    来源: {'订阅链接' if sub.url else '手动导入'}")
        if sub.updated_at:
            click.echo(f"    更新: {sub.updated_at[:19]}")

    all_proxies = cfg.get_all_proxies()
    if all_proxies:
        click.echo("")
        click.echo(f"所有节点 (共 {len(all_proxies)} 个):")
        click.echo("-" * 40)
        for i, p in enumerate(all_proxies, 1):
            click.echo(f"  {i:3d}. [{p.get('type', '?'):6s}] {p.get('name', 'unknown')}")


@cli.command()
@click.argument("name")
def delete(name):
    """删除指定订阅"""
    if cfg.remove_subscription(name):
        click.echo(f"已删除订阅: {name}")
    else:
        click.echo(f"未找到订阅: {name}", err=True)
        sys.exit(1)


@cli.command()
def update():
    """更新所有订阅"""
    subs = cfg.get_subscriptions()
    if not subs:
        click.echo("暂无订阅")
        return

    for name, sub in subs.items():
        if sub.url:
            click.echo(f"正在更新: {name}...")
            text = asyncio.run(fetch_subscription(sub.url))
            if text:
                proxies = parse_subscription_text(text)
                if proxies:
                    cfg.update_proxies(name, proxies)
                    click.echo(f"  ✓ 更新成功，{len(proxies)} 个节点")
                else:
                    click.echo(f"  ✗ 解析失败")
            else:
                click.echo(f"  ✗ 无法获取订阅")
        else:
            click.echo(f"  - {name}: 手动导入，跳过")

    # Reload config if engine is running
    if eng.get_status().value == "running":
        click.echo("引擎运行中，重新加载配置...")
        click.echo(eng.reload_config())


@cli.command()
def install():
    """安装 mihomo 及依赖（支持离线模式）"""
    click.echo("开始安装 VPN Manager 依赖...")

    # Detect architecture
    import platform
    arch_map = {
        "x86_64": "amd64",
        "aarch64": "arm64",
        "armv7l": "armv7",
    }
    arch = arch_map.get(platform.machine(), platform.machine())
    click.echo(f"系统架构: {arch}")

    base_dir = Path(__file__).parent
    vendor_dir = base_dir / "vendor"

    # 检测 vendor 离线包
    has_vendor = vendor_dir.is_dir() and (vendor_dir / "mihomo").is_file()
    if has_vendor:
        click.echo("检测到 vendor 目录，将使用离线安装模式")

    # Install Python dependencies
    click.echo("\n1. 安装 Python 依赖...")
    req_file = base_dir / "requirements.txt"

    # 离线安装：从 vendor/wheels 安装
    wheels_dir = vendor_dir / "wheels"
    if has_vendor and wheels_dir.is_dir() and list(wheels_dir.glob("*.whl")):
        click.echo("  从 vendor/wheels 离线安装...")
        ret = os.system(
            f"{sys.executable} -m pip install --no-index --find-links "
            f'"{wheels_dir}" -r "{req_file}" -q'
        )
        if ret == 0:
            click.echo("  ✓ Python 依赖安装完成 (离线)")
        else:
            click.echo("  ✗ 离线安装失败，尝试在线安装...")
            ret = os.system(f"{sys.executable} -m pip install -r {req_file}")
    else:
        # 在线安装
        ret = os.system(f"{sys.executable} -m pip install -r {req_file}")

    # Check if mihomo exists
    bin_path = cfg.config.mihomo_bin_path
    if os.path.isfile(bin_path) and os.access(bin_path, os.X_OK):
        click.echo(f"mihomo 已存在: {bin_path}")
    elif has_vendor:
        click.echo("\n2. 安装 mihomo (离线)...")
        mihomo_src = vendor_dir / "mihomo"
        if mihomo_src.is_file():
            shutil.copy2(str(mihomo_src), bin_path)
            os.chmod(bin_path, 0o755)
            click.echo(f"  ✓ mihomo 已安装到 {bin_path}")
        else:
            click.echo("  ✗ vendor/mihomo 不存在，请运行 download-deps.sh 重新打包")
    else:
        click.echo("\n2. 下载 mihomo (Clash Meta)...")
        click.echo("   请手动下载安装，或运行安装脚本: install.sh")
        click.echo("   下载地址: https://github.com/MetaCubeX/mihomo/releases")

    # Create working directories
    click.echo("\n3. 创建工作目录...")
    work_dir = Path(cfg.config.working_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    # GeoIP database
    geo_dir = work_dir
    click.echo("\n4. 安装 GeoIP 数据库...")
    if os.path.isfile(f"{geo_dir}/geoip.dat") and os.path.getsize(f"{geo_dir}/geoip.dat") > 0:
        click.echo("  ✓ GeoIP 数据库已存在")
    elif has_vendor and (vendor_dir / "geoip.dat").is_file():
        shutil.copy2(str(vendor_dir / "geoip.dat"), str(geo_dir / "geoip.dat"))
        click.echo("  ✓ GeoIP 数据库已安装 (离线)")
    else:
        click.echo("  尝试在线下载...")
        for url in [
            "https://ghproxy.com/https://github.com/MetaCubeX/meta-rules-dat/releases/download/latest/geoip.dat",
            "https://cdn.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@release/geoip.dat",
            "https://github.com/MetaCubeX/meta-rules-dat/releases/download/latest/geoip.dat",
        ]:
            if os.path.isfile(f"{geo_dir}/geoip.dat") and os.path.getsize(f"{geo_dir}/geoip.dat") > 0:
                break
            click.echo(f"  尝试: {url[:50]}...")
            ret = os.system(f'curl -L --connect-timeout 5 --max-time 30 -o "{geo_dir}/geoip.dat" "{url}" 2>/dev/null')
            if ret == 0 and os.path.isfile(f"{geo_dir}/geoip.dat") and os.path.getsize(f"{geo_dir}/geoip.dat") > 0:
                click.echo("  ✓ 下载成功")
                break
        else:
            click.echo("  ✗ 下载失败，请手动下载 geoip.dat 到 /etc/vpn-manager/")

    # GeoSite database
    click.echo("\n5. 安装 GeoSite 数据库...")
    if os.path.isfile(f"{geo_dir}/geosite.dat") and os.path.getsize(f"{geo_dir}/geosite.dat") > 0:
        click.echo("  ✓ GeoSite 数据库已存在")
    elif has_vendor and (vendor_dir / "geosite.dat").is_file():
        shutil.copy2(str(vendor_dir / "geosite.dat"), str(geo_dir / "geosite.dat"))
        click.echo("  ✓ GeoSite 数据库已安装 (离线)")
    else:
        click.echo("  尝试在线下载...")
        for url in [
            "https://ghproxy.com/https://github.com/MetaCubeX/meta-rules-dat/releases/download/latest/geosite.dat",
            "https://cdn.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@release/geosite.dat",
            "https://github.com/MetaCubeX/meta-rules-dat/releases/download/latest/geosite.dat",
        ]:
            if os.path.isfile(f"{geo_dir}/geosite.dat") and os.path.getsize(f"{geo_dir}/geosite.dat") > 0:
                break
            click.echo(f"  尝试: {url[:50]}...")
            ret = os.system(f'curl -L --connect-timeout 5 --max-time 30 -o "{geo_dir}/geosite.dat" "{url}" 2>/dev/null')
            if ret == 0 and os.path.isfile(f"{geo_dir}/geosite.dat") and os.path.getsize(f"{geo_dir}/geosite.dat") > 0:
                click.echo("  ✓ 下载成功")
                break
        else:
            click.echo("  ✗ 下载失败，请手动下载 geosite.dat 到 /etc/vpn-manager/")

    click.echo("\n✓ 安装完成！")
    click.echo("   运行 python3 main.py web 启动 Web 面板")
    click.echo("   运行 python3 main.py start 启动代理引擎")


if __name__ == "__main__":
    cli()
