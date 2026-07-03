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


@cli.command()
def start():
    """启动 mihomo 引擎"""
    result = eng.start()
    click.echo(result)


@cli.command()
def stop():
    """停止 mihomo 引擎"""
    result = eng.stop()
    click.echo(result)


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
    """安装 mihomo 及依赖"""
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

    # Install Python dependencies
    click.echo("\n1. 安装 Python 依赖...")
    req_file = Path(__file__).parent / "requirements.txt"
    os.system(f"{sys.executable} -m pip install -r {req_file}")

    # Check if mihomo exists
    bin_path = cfg.config.mihomo_bin_path
    if os.path.isfile(bin_path) and os.access(bin_path, os.X_OK):
        click.echo(f"mihomo 已存在: {bin_path}")
    else:
        click.echo(f"\n2. 下载 mihomo (Clash Meta)...")
        click.echo("   请手动下载安装，或运行安装脚本: install.sh")
        click.echo("   下载地址: https://github.com/MetaCubeX/mihomo/releases")

    # Create working directories
    click.echo("\n3. 创建工作目录...")
    work_dir = Path(cfg.config.working_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    # Download GeoIP and GeoSite databases (with mirrors)
    geo_dir = work_dir
    click.echo("\n4. 下载 GeoIP 数据库...")
    for url in [
        f"https://ghproxy.com/https://github.com/MetaCubeX/meta-rules-dat/releases/download/latest/geoip.dat",
        f"https://cdn.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@release/geoip.dat",
        f"https://github.com/MetaCubeX/meta-rules-dat/releases/download/latest/geoip.dat",
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

    click.echo("\n5. 下载 GeoSite 数据库...")
    for url in [
        f"https://ghproxy.com/https://github.com/MetaCubeX/meta-rules-dat/releases/download/latest/geosite.dat",
        f"https://cdn.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@release/geosite.dat",
        f"https://github.com/MetaCubeX/meta-rules-dat/releases/download/latest/geosite.dat",
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
