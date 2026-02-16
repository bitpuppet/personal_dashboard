"""
Per-plugin API for Hello World. Mounted at /api/components/hello_world/.
"""
from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel


class HelloWorldResponse(BaseModel):
    """Response for GET /data."""

    message: str = "Hello World"


def get_router(dashboard_app: Any) -> Optional[APIRouter]:
    """Return router for this plugin; mounted with prefix /api/components/hello_world."""
    router = APIRouter(tags=["Hello World"])

    @router.get("/data", response_model=HelloWorldResponse)
    def get_data() -> HelloWorldResponse:
        """Return a simple message."""
        return HelloWorldResponse(message="Hello World")

    return router
