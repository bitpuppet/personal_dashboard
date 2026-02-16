"""
Core DB models: component registry and task schedule (next_run persistence).
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import Column, String, Boolean, DateTime, Text, JSON, select

from dashboard.core.db import Base, session_scope


def _utc_now() -> datetime:
    """UTC now as naive datetime for DateTime(timezone=False) columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Component(Base):
    """Registry of available components and whether each is enabled."""
    __tablename__ = "components"

    name = Column(String(255), primary_key=True)  # component display name
    enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=False), default=_utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=False), default=_utc_now, onupdate=_utc_now, nullable=False)


class TaskSchedule(Base):
    """Per-component task schedule: next_run_at and last_run_at so scheduling survives restarts."""
    __tablename__ = "task_schedules"

    component_name = Column(String(255), primary_key=True)
    schedule_type = Column(String(64), nullable=False)  # DAILY, HOURLY, INTERVAL_SECONDS, MONTHLY
    schedule_config = Column(JSON, nullable=True)  # e.g. {"time": "07:00"}, {"interval_seconds": 86400}
    next_run_at = Column(DateTime(timezone=False), nullable=True)  # null = run immediately (e.g. new DB)
    last_run_at = Column(DateTime(timezone=False), nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=False), default=_utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=False), default=_utc_now, onupdate=_utc_now, nullable=False)


def get_all_task_schedules() -> List[Dict[str, Any]]:
    """Return all TaskSchedule rows as list of dicts (for API). Datetimes are naive UTC."""
    rows = get_all_task_schedule_records()
    return [
        {
            "component_name": r.component_name,
            "schedule_type": r.schedule_type,
            "schedule_config": r.schedule_config,
            "next_run_at": r.next_run_at,
            "last_run_at": r.last_run_at,
            "last_error": r.last_error,
        }
        for r in rows
    ]


def get_all_task_schedule_records() -> List[TaskSchedule]:
    """Return all TaskSchedule ORM rows (for API serialization via Pydantic from_attributes)."""
    with session_scope() as session:
        return list(session.execute(select(TaskSchedule)).scalars().all())


def sync_components_from_config(config_data: Dict[str, Any]) -> None:
    """Upsert component registry from config so DB has current list and enabled state."""
    components = config_data.get("components") or {}
    with session_scope() as session:
        for name, comp_config in components.items():
            enabled = comp_config.get("enable", True) if isinstance(comp_config, dict) else True
            now = _utc_now()
            row = session.execute(select(Component).where(Component.name == name)).scalars().first()
            if row:
                row.enabled = enabled
                row.updated_at = now
            else:
                session.add(Component(name=name, enabled=enabled, created_at=now, updated_at=now))
