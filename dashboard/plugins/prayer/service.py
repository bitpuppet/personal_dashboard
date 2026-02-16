"""
Service layer: save and load prayer times from DB.
"""
from datetime import date, datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import select, delete

from dashboard.core.db import session_scope
from dashboard.plugins.prayer.models import PrayerTimesRecord


def save_prayer_times(
    component_name: str,
    prayer_date: date,
    times_dict: Dict[str, Any],
) -> None:
    """Replace this component's prayer times for the given date. times_dict: prayer_name -> datetime or ISO str."""
    fetched_at = datetime.now(timezone.utc).replace(tzinfo=None)
    # Serialize to JSON-serializable: datetime -> ISO string
    data = {}
    for k, v in times_dict.items():
        if isinstance(v, datetime):
            data[k] = v.isoformat()
        else:
            data[k] = v
    with session_scope() as session:
        session.execute(
            delete(PrayerTimesRecord).where(
                PrayerTimesRecord.component_name == component_name,
                PrayerTimesRecord.prayer_date == prayer_date,
            )
        )
        session.add(
            PrayerTimesRecord(
                component_name=component_name,
                fetched_at=fetched_at,
                prayer_date=prayer_date,
                data=data,
            )
        )


def get_latest_prayer_times(component_name: str) -> Optional[Dict[str, Any]]:
    """Return the latest prayer times for this component (most recent fetch). Data values are ISO datetime strings."""
    row = get_latest_prayer_times_record(component_name)
    return row.data if row else None


def get_latest_prayer_times_record(component_name: str) -> Optional[PrayerTimesRecord]:
    """Return the latest PrayerTimesRecord row for this component (for API serialization)."""
    with session_scope() as session:
        return (
            session.execute(
                select(PrayerTimesRecord)
                .where(PrayerTimesRecord.component_name == component_name)
                .order_by(PrayerTimesRecord.fetched_at.desc())
                .limit(1)
            )
            .scalars().first()
        )
