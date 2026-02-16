"""
Service layer: save and load weather data from DB.
"""
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import select, delete

from dashboard.core.db import session_scope
from dashboard.plugins.weather.models import WeatherRecord


def save_weather(component_name: str, data: Dict[str, Any]) -> None:
    """Replace this component's weather data with a new run (delete previous, insert one row)."""
    fetched_at = datetime.now(timezone.utc).replace(tzinfo=None)
    with session_scope() as session:
        session.execute(
            delete(WeatherRecord).where(WeatherRecord.component_name == component_name)
        )
        session.add(
            WeatherRecord(
                component_name=component_name,
                fetched_at=fetched_at,
                data=data,
            )
        )


def get_latest_weather(component_name: str) -> Optional[Dict[str, Any]]:
    """Return the latest weather data for this component (most recent fetch)."""
    row = get_latest_weather_record(component_name)
    if row and row.data is not None:
        return row.data
    return None


def get_latest_weather_record(component_name: str) -> Optional[WeatherRecord]:
    """Return the latest WeatherRecord row for this component (for API serialization)."""
    with session_scope() as session:
        return (
            session.execute(
                select(WeatherRecord)
                .where(WeatherRecord.component_name == component_name)
                .order_by(WeatherRecord.fetched_at.desc())
                .limit(1)
            )
            .scalars().first()
        )
