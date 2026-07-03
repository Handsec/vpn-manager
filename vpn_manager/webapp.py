from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from vpn_manager.config import ConfigManager
from vpn_manager.engine import EngineManager
from vpn_manager.models import ProxyMode
from vpn_manager.subscription import fetch_subscription, parse_subscription_text


class SubscriptionImportRequest(BaseModel):
    url: str = ""
    name: str = ""
    text: str = ""
    sub_name: str = ""


class ModeSwitchRequest(BaseModel):
    mode: str


def create_app(config: ConfigManager, engine: EngineManager) -> FastAPI:
    app = FastAPI(title="VPN Manager", version="1.0.0")

    web_dir = Path(__file__).parent.parent / "web"
    templates = Jinja2Templates(directory=str(web_dir / "templates"))

    # Mount static files
    static_dir = web_dir / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    router = APIRouter()

    @router.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        status = engine.get_status().value
        mode = config.get_mode().value
        proxies_data = engine.get_proxies()
        version = engine.get_version()
        all_proxies = config.get_all_proxies()

        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "status": status,
                "mode": mode,
                "proxies": all_proxies,
                "version": version,
                "config": config.config,
            },
        )

    @router.get("/api/status")
    async def api_status():
        return {
            "status": engine.get_status().value,
            "mode": config.get_mode().value,
            "version": engine.get_version(),
        }

    @router.get("/api/proxies")
    async def api_proxies():
        return engine.get_proxies()

    @router.get("/api/subscriptions")
    async def api_subscriptions():
        subs = config.get_subscriptions()
        return {name: s.model_dump(mode="json") for name, s in subs.items()}

    @router.post("/api/subscriptions/import-url")
    async def api_import_url(req: SubscriptionImportRequest):
        if not req.url:
            raise HTTPException(400, "请提供订阅URL")
        text = await fetch_subscription(req.url)
        if not text:
            raise HTTPException(400, "无法获取订阅内容")
        proxies = parse_subscription_text(text)
        if not proxies:
            raise HTTPException(400, "未解析到任何代理节点")
        name = req.name or "订阅-" + str(len(config.get_subscriptions()) + 1)
        config.add_subscription(name, req.url, proxies)
        return {"success": True, "name": name, "count": len(proxies)}

    @router.post("/api/subscriptions/import-text")
    async def api_import_text(req: SubscriptionImportRequest):
        if not req.text:
            raise HTTPException(400, "请提供订阅内容")
        proxies = parse_subscription_text(req.text)
        if not proxies:
            raise HTTPException(400, "未解析到任何代理节点")
        name = req.name or "手动-" + str(len(config.get_subscriptions()) + 1)
        config.add_subscription(name, None, proxies)
        return {"success": True, "name": name, "count": len(proxies)}

    @router.post("/api/subscriptions/delete/{name}")
    async def api_delete_subscription(name: str):
        config.remove_subscription(name)
        return {"success": True}

    @router.post("/api/mode")
    async def api_switch_mode(req: ModeSwitchRequest):
        try:
            mode = ProxyMode(req.mode)
        except ValueError:
            raise HTTPException(400, f"无效模式: {req.mode}，可选: global, rule, direct")
        msg = engine.switch_mode(mode)
        return {"success": True, "mode": mode.value, "message": msg}

    @router.post("/api/engine/start")
    async def api_start():
        msg = engine.start()
        return {"success": "已启动" in msg, "message": msg}

    @router.post("/api/engine/stop")
    async def api_stop():
        msg = engine.stop()
        return {"success": True, "message": msg}

    @router.post("/api/engine/restart")
    async def api_restart():
        msg = engine.restart()
        return {"success": True, "message": msg}

    @router.get("/api/config")
    async def api_get_config():
        return config.config.model_dump(mode="json")

    @router.post("/api/config/update")
    async def api_update_config(data: dict):
        server_fields = ["mixed_port", "api_port", "allow_lan", "log_level"]
        for k, v in data.items():
            if k in server_fields:
                config.update_server_config(**{k: v})
        return {"success": True}

    @router.get("/api/logs")
    async def api_get_logs(level: str = "warning"):
        return {"logs": engine.get_logs(level)}

    app.include_router(router)
    return app
