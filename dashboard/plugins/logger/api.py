"""
Per-plugin API for Logger. Mounted at /api/components/logger/.
"""
from typing import Any, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel


class LoggerResponse(BaseModel):
    """Response for GET /data."""

    recent_logs: List[Any] = []


def get_router(dashboard_app: Any) -> Optional[APIRouter]:
    """Return router for this plugin; mounted with prefix /api/components/logger."""
    router = APIRouter(tags=["Logger"])

    @router.get("/data", response_model=LoggerResponse)
    def get_data() -> LoggerResponse:
        """Return minimal placeholder; optional: tail log file and return last N lines."""
        return LoggerResponse(recent_logs=[])

    return router
