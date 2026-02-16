"""
Per-plugin API for Friday Prayer. Mounted at /api/components/friday_prayer/.
Uses FridayPrayerRecord ORM with Pydantic from_attributes.
"""
from datetime import datetime
from typing import Any, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from .models import FridayPrayerRecord
from .service import get_latest_friday_prayer_record

COMPONENT_NAME = "Friday Prayer"


class FridayPrayerRecordResponse(BaseModel):
    """Pydantic view of FridayPrayerRecord for API; serializes from ORM."""

    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = None
    component_name: Optional[str] = None
    fetched_at: Optional[datetime] = None
    data: Optional[List[Any]] = None


def get_router(dashboard_app) -> Optional[APIRouter]:
    """Return router for this plugin; mounted with prefix /api/components/friday_prayer."""
    router = APIRouter(tags=["Friday Prayer"])

    @router.get("/data", response_model=FridayPrayerRecordResponse)
    def get_data() -> FridayPrayerRecordResponse:
        """Return latest Friday prayer record from DB (ORM serialized via Pydantic)."""
        record = get_latest_friday_prayer_record(COMPONENT_NAME)
        if record is None:
            return FridayPrayerRecordResponse(component_name=COMPONENT_NAME, data=[])
        return FridayPrayerRecordResponse.model_validate(record)

    return router
