from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ProxyMode(str, Enum):
    GLOBAL = "global"
    RULE = "rule"
    DIRECT = "direct"


class EngineStatus(str, Enum):
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"


class Subscription(BaseModel):
    name: str
    url: Optional[str] = None
    proxies: list[dict] = Field(default_factory=list)
    updated_at: Optional[str] = None
    type: str = "clash"  # clash, base64


class ServerConfig(BaseModel):
    mixed_port: int = 7890
    api_port: int = 9090
    allow_lan: bool = False
    log_level: str = "warning"
    mode: ProxyMode = ProxyMode.RULE


class AppConfig(BaseModel):
    server: ServerConfig = Field(default_factory=ServerConfig)
    subscriptions: dict[str, Subscription] = Field(default_factory=dict)
    current_mode: ProxyMode = ProxyMode.RULE
    mihomo_bin_path: str = "/usr/local/bin/mihomo"
    working_dir: str = "/etc/vpn-manager"
    auto_update: bool = False
    update_interval: int = 3600  # seconds
