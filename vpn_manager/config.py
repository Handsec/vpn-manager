from __future__ import annotations

import os
import shutil
from pathlib import Path

import yaml

from vpn_manager.models import AppConfig, ProxyMode

DEFAULT_CONFIG_PATH = "/etc/vpn-manager/config.yaml"
LOCAL_CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


class ConfigManager:
    """Manages application configuration."""

    def __init__(self, config_path: str | None = None):
        self.config_path = config_path or str(LOCAL_CONFIG_PATH)
        self.config: AppConfig = self._load()

    def _load(self) -> AppConfig:
        path = Path(self.config_path)
        if path.exists():
            with open(path) as f:
                data = yaml.safe_load(f) or {}
            return AppConfig(**data)
        cfg = AppConfig()
        self._save(cfg)
        return cfg

    def _save(self, cfg: AppConfig | None = None) -> None:
        cfg = cfg or self.config
        path = Path(self.config_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            yaml.dump(
                cfg.model_dump(mode="json"),
                f,
                default_flow_style=False,
                allow_unicode=True,
            )

    def get_mode(self) -> ProxyMode:
        return self.config.current_mode

    def set_mode(self, mode: ProxyMode) -> None:
        self.config.current_mode = mode
        self._save()

    def get_subscriptions(self) -> dict:
        return self.config.subscriptions

    def add_subscription(self, name: str, url: str | None, proxies: list[dict] | None = None) -> None:
        from vpn_manager.models import Subscription
        import datetime
        self.config.subscriptions[name] = Subscription(
            name=name,
            url=url,
            proxies=proxies or [],
            updated_at=datetime.datetime.now().isoformat(),
        )
        self._save()

    def remove_subscription(self, name: str) -> bool:
        if name in self.config.subscriptions:
            del self.config.subscriptions[name]
            self._save()
            return True
        return False

    def update_proxies(self, sub_name: str, proxies: list[dict]) -> None:
        import datetime
        if sub_name in self.config.subscriptions:
            self.config.subscriptions[sub_name].proxies = proxies
            self.config.subscriptions[sub_name].updated_at = datetime.datetime.now().isoformat()
            self._save()

    def get_all_proxies(self) -> list[dict]:
        proxies = []
        seen_names = set()
        for sub in self.config.subscriptions.values():
            for p in sub.proxies:
                name = p.get("name", "")
                if name not in seen_names:
                    seen_names.add(name)
                    proxies.append(p)
        return proxies

    def update_server_config(self, **kwargs) -> None:
        for k, v in kwargs.items():
            if hasattr(self.config.server, k):
                setattr(self.config.server, k, v)
        self._save()
