"""
Service layer: save and load Friday prayer times from DB.
"""
from datetime import datetime, timezone
from typing import Any, List, Optional

from sqlalchemy import select, delete

from dashboard.core.db import session_scope
from dashboard.plugins.friday_prayer.models import FridayPrayerRecord


def save_friday_times(component_name: str, times_list: List[dict]) -> None:
    """Replace this component's Friday times with a new run (delete previous, insert one row)."""
    fetched_at = datetime.now(timezone.utc).replace(tzinfo=None)
    with session_scope() as session:
        session.execute(
            delete(FridayPrayerRecord).where(
                FridayPrayerRecord.component_name == component_name
            )
        )
        session.add(
            FridayPrayerRecord(
                component_name=component_name,
                fetched_at=fetched_at,
                data=times_list,
            )
        )


def get_latest_friday_times(component_name: str) -> List[dict]:
    """Return the latest Friday times for this component (most recent fetch)."""
    row = get_latest_friday_prayer_record(component_name)
    if row and row.data:
        return row.data
    return []


def get_latest_friday_prayer_record(component_name: str) -> Optional[FridayPrayerRecord]:
    """Return the latest FridayPrayerRecord row for this component (for API serialization)."""
    with session_scope() as session:
        return (
            session.execute(
                select(FridayPrayerRecord)
                .where(FridayPrayerRecord.component_name == component_name)
                .order_by(FridayPrayerRecord.fetched_at.desc())
                .limit(1)
            )
            .scalars().first()
        )
