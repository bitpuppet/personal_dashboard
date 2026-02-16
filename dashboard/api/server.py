"""
FastAPI server for dashboard API. Run with run_api_server(app) in a background thread.
Central endpoints: GET /api/components, GET /api/tasks. Per-plugin routes are mounted
from dashboard.plugins.<package>.api (get_router(dashboard_app)) under /api/components/<package>/.
Docs when enabled: http://<host>:<port>/docs
"""
import importlib
import logging
import pkgutil
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import FastAPI

logger = logging.getLogger(__name__)

# Keys to exclude from component config in API (secrets)
_CONFIG_SECRET_KEYS = frozenset(
    {"api_key", "password", "token", "secret", "credentials", "client_secret"}
)


def _safe_component_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Return config with secret keys omitted."""
    if not config:
        return {}
    return {k: v for k, v in config.items() if k.lower() not in _CONFIG_SECRET_KEYS}


def _serialize_datetime(dt: Optional[datetime]) -> Optional[str]:
    """Serialize datetime to ISO string (UTC)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def create_app(dashboard_app: Any) -> FastAPI:
    """Create FastAPI app with routes that use the given DashboardApp instance."""
    app = FastAPI(title="Dashboard API", description="Components, tasks, and component data")

    @app.get("/api/components")
    def list_components() -> List[Dict[str, Any]]:
        """List registered components with enabled state and safe config."""
        components_data = []
        comp_config = dashboard_app.config.data.get("components") or {}
        for name in dashboard_app.plugin_manager.components:
            enabled = True
            config = comp_config.get(name) or {}
            if isinstance(config, dict):
                enabled = config.get("enable", True)
            safe_config = _safe_component_config(config) if isinstance(config, dict) else {}
            components_data.append({
                "name": name,
                "enabled": enabled,
                "config": safe_config,
            })
        return components_data

    @app.get("/api/tasks")
    def list_tasks() -> Dict[str, Any]:
        """List scheduled tasks: DB schedules and active in-memory timers."""
        from dashboard.core.models import get_all_task_schedules

        db_schedules = get_all_task_schedules()
        for row in db_schedules:
            row["next_run_at"] = _serialize_datetime(row.get("next_run_at"))
            row["last_run_at"] = _serialize_datetime(row.get("last_run_at"))

        active_timers = dashboard_app.task_manager.get_active_timers()
        active_list = [
            {"name": t["name"], "next_run_at": _serialize_datetime(t["next_run_at"])}
            for t in active_timers
        ]

        return {"db_schedules": db_schedules, "active_timers": active_list}

    @app.get("/api/schedules")
    def list_schedules() -> Dict[str, Any]:
        """Alias for /api/tasks."""
        return list_tasks()

    # Mount per-plugin API routers from dashboard.plugins.<name>.api (get_router(dashboard_app))
    try:
        plugins_pkg = importlib.import_module("dashboard.plugins")
        for _mod, name, is_pkg in pkgutil.iter_modules(plugins_pkg.__path__):
            if not is_pkg:
                continue
            try:
                api_module = importlib.import_module(f"dashboard.plugins.{name}.api")
            except ImportError:
                continue
            if not hasattr(api_module, "get_router") or not callable(api_module.get_router):
                continue
            try:
                router = api_module.get_router(dashboard_app)
                if router is not None:
                    app.include_router(router, prefix=f"/api/components/{name}")
            except Exception as e:
                logger.warning(f"Failed to mount API router for plugin {name}: {e}", exc_info=True)
    except Exception as e:
        logger.warning(f"Plugin API discovery failed: {e}", exc_info=True)

    return app


def run_api_server(dashboard_app: Any) -> None:
    """
    Start the API server in a daemon thread if api.enabled is true.
    Reads api.host (default 127.0.0.1) and api.port (default 8765) from config.
    """
    api_config = dashboard_app.config.data.get("api") or {}
    enabled = api_config.get("enabled", False)
    config_file = getattr(dashboard_app.config, "config_file", None)
    logger.info(
        f"API config: enabled={enabled}, config_file={config_file}, api section={list(api_config.keys())}"
    )
    if not enabled:
        logger.info(
            "API server not started: set api.enabled to true in your config file to enable."
        )
        return
    host = api_config.get("host", "127.0.0.1")
    port = int(api_config.get("port", 8765))
    fastapi_app = create_app(dashboard_app)

    def run_uvicorn():
        try:
            import uvicorn
            logger.info(f"API server listening at http://{host}:{port} (docs at /docs)")
            uvicorn.run(fastapi_app, host=host, port=port)
        except Exception as e:
            logger.exception(f"API server thread failed: {e}")

    thread = threading.Thread(target=run_uvicorn, daemon=True)
    thread.start()
    logger.info("API server thread started.")
