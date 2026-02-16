"""
Per-plugin API for Prayer Times. Mounted at /api/prayer/.
Uses PrayerTimesRecord ORM with Pydantic from_attributes.
"""
from datetime import date, datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from .models import PrayerTimesRecord
from .service import get_latest_prayer_times_record

COMPONENT_NAME = "Prayer Times"


class PrayerTimesRecordResponse(BaseModel):
    """Pydantic view of PrayerTimesRecord for API; serializes from ORM."""

    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = None
    component_name: Optional[str] = None
    fetched_at: Optional[datetime] = None
    prayer_date: Optional[date] = None
    data: Optional[Dict[str, Any]] = None


def get_router(dashboard_app) -> Optional[APIRouter]:
    """Return router for this plugin; mounted with prefix /api/prayer."""
    router = APIRouter(tags=["Prayer Times"])

    @router.get("/data", response_model=PrayerTimesRecordResponse)
    def get_data() -> PrayerTimesRecordResponse:
        """Return latest prayer times record from DB (ORM serialized via Pydantic)."""
        record = get_latest_prayer_times_record(COMPONENT_NAME)
        if record is None:
            raise HTTPException(status_code=404, detail="No prayer times data available")
        return PrayerTimesRecordResponse.model_validate(record)

    return router
