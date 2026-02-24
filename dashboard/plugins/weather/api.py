"""
Per-plugin API for Weather. Mounted at /api/components/weather/.
Uses WeatherRecord ORM with Pydantic from_attributes.
"""
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from .models import WeatherRecord
from .service import get_latest_weather_record


class WeatherRecordResponse(BaseModel):
    """Pydantic view of WeatherRecord for API; serializes from ORM."""

    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = None
    component_name: Optional[str] = None
    fetched_at: Optional[datetime] = None
    data: Optional[Dict[str, Any]] = None


def get_router(dashboard_app) -> Optional[APIRouter]:
    """Return router for this plugin; mounted with prefix /api/components/weather."""
    router = APIRouter(tags=["Weather"])

    @router.get("/data", response_model=WeatherRecordResponse)
    def get_data() -> WeatherRecordResponse:
        """Return data from the first available weather type in DB (ORM serialized via Pydantic)."""
        for name in ("Weekly Weather", "Hourly Weather", "Weather"):
            try:
                record = get_latest_weather_record(name)
                if record is not None:
                    return WeatherRecordResponse.model_validate(record)
            except Exception:
                pass
        raise HTTPException(status_code=404, detail="No weather data available")

    @router.get("/hourly", response_model=WeatherRecordResponse)
    def get_hourly() -> WeatherRecordResponse:
        """Return hourly weather record from DB (ORM serialized via Pydantic)."""
        record = get_latest_weather_record("Hourly Weather")
        if record is None:
            raise HTTPException(status_code=404, detail="No hourly weather data available")
        return WeatherRecordResponse.model_validate(record)

    @router.get("/weekly", response_model=WeatherRecordResponse)
    def get_weekly() -> WeatherRecordResponse:
        """Return weekly weather record from DB (ORM serialized via Pydantic)."""
        record = get_latest_weather_record("Weekly Weather")
        if record is None:
            raise HTTPException(status_code=404, detail="No weekly weather data available")
        return WeatherRecordResponse.model_validate(record)

    @router.get("/current", response_model=WeatherRecordResponse)
    def get_current() -> WeatherRecordResponse:
        """Return current (7-day) weather record from DB (ORM serialized via Pydantic)."""
        record = get_latest_weather_record("Weather")
        if record is None:
            raise HTTPException(status_code=404, detail="No current weather data available")
        return WeatherRecordResponse.model_validate(record)

    return router
