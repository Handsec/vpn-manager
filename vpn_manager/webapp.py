from __future__ import annotations

import json
from pathlib import Path

import yaml
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from vpn_manager.config import ConfigManager
from vpn_manager.engine import EngineManager
from vpn_manager.models import ProxyMode
from vpn_manager.subscription import fetch_subscription, parse_subscription_text

app = FastAPI(title="VPN Manager", version="1.0.0")

# Will be set by create_app()
cfg_mgr: ConfigManager = None
eng_mgr: EngineManager = None
templates: Jinja2Templates = None


class SubscriptionImportRequest(BaseModel):
    url: str = ""
    name: str = ""
    text: str = ""
    sub_name: str = ""


class ModeSwitchRequest(BaseModel):
    mode: str


class ProxySelectRequest(BaseModel):
    group_name: str
    proxy_name: str


def create_app(config: ConfigManager, engine: EngineManager) -> FastAPI:
    global cfg_mgr, eng_mgr, templates
    cfg_mgr = config
    eng_mgr = engine

    web_dir = Path(__file__).parent.parent / "web"
    templates = Jinja2Templates(directory=str(web_dir / "templates"))

    # Mount static files
    static_dir = web_dir / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    if str(static_dir) not in [m.path for m in app.routes if hasattr(m, "path")]:
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    return app


# ---- API Routes ----

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    status = eng_mgr.get_status().value
    mode = cfg_mgr.get_mode().value
    proxies_data = eng_mgr.get_proxies()
    version = eng_mgr.get_version()

    proxy_groups = {}
    for name, info in proxies_data.items():
        if info.get("type") in ("Selector", "URLTest", "Fallback"):
            proxy_groups[name] = {
                "type": info.get("type"),
                "now": info.get("now", ""),
                "all": info.get("all", []),
            }

    # Get all configured proxies
    all_proxies = cfg_mgr.get_all_proxies()

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "status": status,
            "mode": mode,
            "proxy_groups": proxy_groups,
            "proxies": all_proxies,
            "version": version,
            "config": cfg_mgr.config,
        },
    )


@app.get("/api/status")
async def api_status():
    return {
        "status": eng_mgr.get_status().value,
        "mode": cfg_mgr.get_mode().value,
        "version": eng_mgr.get_version(),
    }


@app.get("/api/proxies")
async def api_proxies():
    return eng_mgr.get_proxies()


@app.get("/api/subscriptions")
async def api_subscriptions():
    subs = cfg_mgr.get_subscriptions()
    return {name: s.model_dump(mode="json") for name, s in subs.items()}


@app.post("/api/subscriptions/import-url")
async def api_import_url(req: SubscriptionImportRequest):
    if not req.url:
        raise HTTPException(400, "请提供订阅URL")
    text = await fetch_subscription(req.url)
    if not text:
        raise HTTPException(400, "无法获取订阅内容")
    proxies = parse_subscription_text(text)
    if not proxies:
        raise HTTPException(400, "未解析到任何代理节点")
    name = req.name or "订阅-" + str(len(cfg_mgr.get_subscriptions()) + 1)
    cfg_mgr.add_subscription(name, req.url, proxies)
    return {"success": True, "name": name, "count": len(proxies)}


@app.post("/api/subscriptions/import-text")
async def api_import_text(req: SubscriptionImportRequest):
    if not req.text:
        raise HTTPException(400, "请提供订阅内容")
    proxies = parse_subscription_text(req.text)
    if not proxies:
        raise HTTPException(400, "未解析到任何代理节点")
    name = req.name or "手动-" + str(len(cfg_mgr.get_subscriptions()) + 1)
    cfg_mgr.add_subscription(name, None, proxies)
    return {"success": True, "name": name, "count": len(proxies)}


@app.post("/api/subscriptions/delete/{name}")
async def api_delete_subscription(name: str):
    cfg_mgr.remove_subscription(name)
    return {"success": True}


@app.post("/api/mode")
async def api_switch_mode(req: ModeSwitchRequest):
    try:
        mode = ProxyMode(req.mode)
    except ValueError:
        raise HTTPException(400, f"无效模式: {req.mode}，可选: global, rule, direct")
    msg = eng_mgr.switch_mode(mode)
    return {"success": True, "mode": mode.value, "message": msg}


@app.post("/api/engine/start")
async def api_start():
    msg = eng_mgr.start()
    return {"success": "已启动" in msg, "message": msg}


@app.post("/api/engine/stop")
async def api_stop():
    msg = eng_mgr.stop()
    return {"success": True, "message": msg}


@app.post("/api/engine/restart")
async def api_restart():
    msg = eng_mgr.restart()
    return {"success": True, "message": msg}


@app.get("/api/config")
async def api_get_config():
    return cfg_mgr.config.model_dump(mode="json")


@app.post("/api/config/update")
async def api_update_config(data: dict):
    server_fields = ["mixed_port", "api_port", "allow_lan", "log_level"]
    for k, v in data.items():
        if k in server_fields:
            cfg_mgr.update_server_config(**{k: v})
    return {"success": True}


@app.get("/api/logs")
async def api_get_logs(level: str = "warning"):
    return {"logs": eng_mgr.get_logs(level)}
