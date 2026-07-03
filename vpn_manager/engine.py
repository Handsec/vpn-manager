from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import time
from pathlib import Path
from typing import Optional

import httpx
import yaml

from vpn_manager.config import ConfigManager
from vpn_manager.models import EngineStatus, ProxyMode

DEFAULT_CONFIG_TEMPLATE = """mixed-port: {mixed_port}
api-port: {api_port}
allow-lan: {allow_lan}
log-level: {log_level}
mode: {mode}
ipv6: false
external-controller: 0.0.0.0:{api_port}
external-ui: /etc/vpn-manager/ui

proxies: []

proxy-groups:
  - name: PROXY
    type: select
    proxies:
      - AUTO
      - DIRECT
  - name: AUTO
    type: url-test
    proxies: []
    url: "http://www.gstatic.com/generate_204"
    interval: 300
    tolerance: 50

rules:
  - GEOSITE,category-ads,REJECT
  - GEOSITE,private,DIRECT
  - GEOSITE,microsoft@cn,DIRECT
  - GEOSITE,apple-cn,DIRECT
  - GEOSITE,google-cn,DIRECT
  - GEOSITE,category-games@cn,DIRECT
  - GEOSITE,cn,DIRECT
  - GEOIP,CN,DIRECT
  - MATCH,PROXY
"""


class EngineManager:
    """Manages the mihomo (Clash Meta) engine process."""

    def __init__(self, config: ConfigManager):
        self.cfg = config
        self.process: Optional[subprocess.Popen] = None

    def _generate_config(self, mode: ProxyMode) -> dict:
        """Generate the mihomo config dict for the given mode."""
        server = self.cfg.config.server
        all_proxies = self.cfg.get_all_proxies()
        proxy_names = [p["name"] for p in all_proxies]

        config = {
            "mixed-port": server.mixed_port,
            "api-port": server.api_port,
            "allow-lan": server.allow_lan,
            "log-level": server.log_level,
            "mode": "rule",
            "ipv6": False,
            "external-controller": f"0.0.0.0:{server.api_port}",
            "proxies": all_proxies,
        }

        if mode == ProxyMode.DIRECT:
            config["mode"] = "direct"
            config["rules"] = [{"MATCH": "DIRECT"}]
            config["proxy-groups"] = []
            return config

        if mode == ProxyMode.GLOBAL:
            config["mode"] = "global"
            config["proxy-groups"] = [
                {
                    "name": "PROXY",
                    "type": "select",
                    "proxies": proxy_names if proxy_names else ["DIRECT"],
                },
            ]
            config["rules"] = [{"MATCH": "PROXY"}]
            return config

        # Rule mode
        config["mode"] = "rule"
        config["proxy-groups"] = [
            {
                "name": "PROXY",
                "type": "select",
                "proxies": ["AUTO", "DIRECT", *proxy_names[:5]],
            },
            {
                "name": "AUTO",
                "type": "url-test",
                "proxies": proxy_names if proxy_names else ["DIRECT"],
                "url": "http://www.gstatic.com/generate_204",
                "interval": 300,
                "tolerance": 50,
            },
        ]

        config["rules"] = [
            {"GEOSITE": "category-ads", "policy": "REJECT"},
            {"GEOSITE": "private", "policy": "DIRECT"},
            {"GEOSITE": "microsoft@cn", "policy": "DIRECT"},
            {"GEOSITE": "apple-cn", "policy": "DIRECT"},
            {"GEOSITE": "google-cn", "policy": "DIRECT"},
            {"GEOSITE": "category-games@cn", "policy": "DIRECT"},
            {"GEOSITE": "cn", "policy": "DIRECT"},
            {"GEOIP": "CN", "policy": "DIRECT"},
            {"MATCH": "PROXY"},
        ]

        return config

    def write_config(self, mode: Optional[ProxyMode] = None) -> str:
        """Write mihomo config to disk."""
        mode = mode or self.cfg.get_mode()
        config = self._generate_config(mode)
        work_dir = Path(self.cfg.config.working_dir)
        work_dir.mkdir(parents=True, exist_ok=True)
        config_path = work_dir / "config.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
        return str(config_path)

    def find_mihomo(self) -> Optional[str]:
        """Locate the mihomo binary."""
        paths = [
            self.cfg.config.mihomo_bin_path,
            "/usr/local/bin/mihomo",
            "/usr/bin/mihomo",
            "/opt/mihomo/mihomo",
        ]
        for p in paths:
            if os.path.isfile(p) and os.access(p, os.X_OK):
                return p
        which = shutil.which("mihomo")
        if which:
            return which
        return None

    def get_status(self) -> EngineStatus:
        """Check if mihomo is running."""
        if self.process and self.process.poll() is None:
            return EngineStatus.RUNNING
        # Check by PID file
        pid_file = Path(self.cfg.config.working_dir) / "mihomo.pid"
        if pid_file.exists():
            try:
                pid = int(pid_file.read_text().strip())
                os.kill(pid, 0)
                return EngineStatus.RUNNING
            except (ValueError, OSError, ProcessLookupError):
                pid_file.unlink(missing_ok=True)
        return EngineStatus.STOPPED

    def start(self, mode: Optional[ProxyMode] = None) -> str:
        """Start the mihomo engine."""
        status = self.get_status()
        if status == EngineStatus.RUNNING:
            return "mihomo 已在运行中"

        bin_path = self.find_mihomo()
        if not bin_path:
            return (
                "错误: 未找到 mihomo 二进制文件\n"
                "请先安装: 运行 install.sh 脚本 或 手动下载 mihomo 到 /usr/local/bin/"
            )

        config_path = self.write_config(mode)
        work_dir = Path(self.cfg.config.working_dir)
        work_dir.mkdir(parents=True, exist_ok=True)

        try:
            self.process = subprocess.Popen(
                [bin_path, "-d", str(work_dir), "-f", config_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            # Write PID
            pid_file = work_dir / "mihomo.pid"
            pid_file.write_text(str(self.process.pid))

            # Wait briefly to check for immediate failure
            time.sleep(1)
            if self.process.poll() is not None:
                stderr = self.process.stderr.read().decode(errors="replace") if self.process.stderr else ""
                return f"启动失败: {stderr[:500]}"

            return (
                f"mihomo 已启动 (PID: {self.process.pid})\n"
                f"  混合端口: {self.cfg.config.server.mixed_port}\n"
                f"  API端口: {self.cfg.config.server.api_port}\n"
                f"  模式: {mode or self.cfg.get_mode()}"
            )
        except Exception as e:
            return f"启动失败: {e}"

    def stop(self) -> str:
        """Stop the mihomo engine."""
        work_dir = Path(self.cfg.config.working_dir)
        pid_file = work_dir / "mihomo.pid"

        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None
            pid_file.unlink(missing_ok=True)
            return "mihomo 已停止"

        if pid_file.exists():
            try:
                pid = int(pid_file.read_text().strip())
                os.kill(pid, signal.SIGTERM)
                pid_file.unlink(missing_ok=True)
                return f"mihomo (PID: {pid}) 已停止"
            except (ProcessLookupError, ValueError):
                pid_file.unlink(missing_ok=True)
                return "mihomo 未在运行"
        return "mihomo 未在运行"

    def restart(self, mode: Optional[ProxyMode] = None) -> str:
        """Restart the mihomo engine."""
        self.stop()
        time.sleep(1)
        return self.start(mode)

    def switch_mode(self, mode: ProxyMode) -> str:
        """Switch proxy mode (global/rule/direct)."""
        from vpn_manager.models import ProxyMode

        self.cfg.set_mode(mode)
        status = self.get_status()
        if status == EngineStatus.RUNNING:
            self.write_config(mode)
            return self.reload_config()
        else:
            return f"模式已切换为 {mode.value} (引擎未运行，下次启动时生效)"

    def reload_config(self) -> str:
        """Reload mihomo config via API."""
        server = self.cfg.config.server
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{server.api_port}", timeout=5) as client:
                # PUT /configs to reload
                config_path = Path(self.cfg.config.working_dir) / "config.yaml"
                with open(config_path) as f:
                    config_data = yaml.safe_load(f)
                resp = client.put("/configs", json={"path": str(config_path)})
                if resp.status_code in (200, 201, 204):
                    return "配置已重新加载"
                # Fallback: PUT /configs with data
                resp = client.put("/configs", json=config_data)
                if resp.status_code in (200, 201, 204):
                    return "配置已重新加载"
                return f"配置重载返回: {resp.status_code}"
        except httpx.ConnectError:
            return "无法连接到 mihomo API (引擎可能未运行)"
        except Exception as e:
            return f"配置重载失败: {e}"

    def get_proxies(self) -> dict:
        """Get current proxy information from mihomo API."""
        server = self.cfg.config.server
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{server.api_port}", timeout=5) as client:
                resp = client.get("/proxies")
                if resp.status_code == 200:
                    return resp.json().get("proxies", {})
        except Exception:
            pass
        return {}

    def get_traffic(self) -> dict:
        """Get traffic information."""
        server = self.cfg.config.server
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{server.api_port}", timeout=3) as client:
                up = client.get("/traffic")
                # Use events for real-time, but just return basic stats
                return {"up": 0, "down": 0}
        except Exception:
            return {"up": 0, "down": 0}

    def get_logs(self, level: str = "warning") -> list[str]:
        """Get recent logs."""
        server = self.cfg.config.server
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{server.api_port}", timeout=3) as client:
                resp = client.get("/logs", params={"level": level})
                if resp.status_code == 200:
                    return resp.text.strip().split("\n")
        except Exception:
            pass
        return []

    def get_version(self) -> str:
        """Get mihomo version."""
        bin_path = self.find_mihomo()
        if not bin_path:
            return "未知 (未安装)"
        try:
            result = subprocess.run([bin_path, "--version"], capture_output=True, text=True, timeout=5)
            return result.stdout.strip() or result.stderr.strip() or "未知"
        except Exception:
            return "未知"
