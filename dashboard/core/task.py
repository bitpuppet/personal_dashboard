"""
Base task type and abstract BaseTask with next_run persistence in DB.
"""
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from queue import Queue
from typing import Any, Callable, Dict, Optional

from sqlalchemy import select

from dashboard.core.db import session_scope
from dashboard.core.models import TaskSchedule

logger = logging.getLogger(__name__)


class TaskType:
    """Schedule kind for tasks."""
    DAILY = "daily"
    HOURLY = "hourly"
    INTERVAL_SECONDS = "interval_seconds"
    MONTHLY = "monthly"


def compute_next_run(
    schedule_type: str,
    schedule_config: Optional[Dict[str, Any]],
    last_run: Optional[datetime],
) -> datetime:
    """Compute next run datetime from schedule_type, schedule_config, and last_run."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if last_run is None:
        last_run = now

    if schedule_type == TaskType.DAILY and schedule_config:
        time_str = schedule_config.get("time", "00:00")
        parts = str(time_str).strip().split(":")
        hour = int(parts[0]) if parts else 0
        minute = int(parts[1]) if len(parts) > 1 else 0
        next_run = last_run.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if next_run <= last_run:
            next_run += timedelta(days=1)
        return next_run

    if schedule_type == TaskType.HOURLY:
        return last_run + timedelta(hours=1)

    if schedule_type == TaskType.INTERVAL_SECONDS and schedule_config:
        sec = int(schedule_config.get("interval_seconds", 86400))
        return last_run + timedelta(seconds=sec)

    if schedule_type == TaskType.MONTHLY and schedule_config:
        day = int(schedule_config.get("day", 1))
        time_str = schedule_config.get("time", "00:00")
        parts = str(time_str).strip().split(":")
        hour = int(parts[0]) if parts else 0
        minute = int(parts[1]) if len(parts) > 1 else 0
        next_run = last_run.replace(day=day, hour=hour, minute=minute, second=0, microsecond=0)
        if next_run <= last_run:
            if next_run.month == 12:
                next_run = next_run.replace(year=next_run.year + 1, month=1)
            else:
                next_run = next_run.replace(month=next_run.month + 1)
        return next_run

    return last_run + timedelta(days=1)


def get_next_run_from_db(component_name: str) -> Optional[datetime]:
    """Read next_run_at for component from DB. Returns None if no row or next_run_at is null (task will run immediately)."""
    try:
        with session_scope() as session:
            row = session.execute(
                select(TaskSchedule).where(TaskSchedule.component_name == component_name)
            ).scalars().first()
            if row and row.next_run_at is not None:
                return row.next_run_at
    except Exception as e:
        logger.debug(f"get_next_run_from_db {component_name}: {e}")
    return None


def upsert_task_schedule(
    component_name: str,
    schedule_type: str,
    schedule_config: Optional[Dict[str, Any]],
    next_run_at: Optional[datetime] = None,
    last_run_at: Optional[datetime] = None,
    last_error: Optional[str] = None,
) -> None:
    """Create or update TaskSchedule row. If next_run_at not given: for new row leave it null (run immediately); for existing row leave next_run_at unchanged."""
    with session_scope() as session:
        row = session.execute(
            select(TaskSchedule).where(TaskSchedule.component_name == component_name)
        ).scalars().first()
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if row:
            row.schedule_type = schedule_type
            row.schedule_config = schedule_config
            if next_run_at is not None:
                row.next_run_at = next_run_at
            if last_run_at is not None:
                row.last_run_at = last_run_at
            if last_error is not None:
                row.last_error = last_error
            row.updated_at = now
        else:
            # New row: leave next_run_at null so task runs immediately (e.g. fresh DB), then update_after_run sets it
            session.add(TaskSchedule(
                component_name=component_name,
                schedule_type=schedule_type,
                schedule_config=schedule_config,
                next_run_at=next_run_at,
                last_run_at=last_run_at,
                last_error=last_error,
                created_at=now,
                updated_at=now,
            ))


def update_after_run(component_name: str) -> None:
    """Update last_run_at and next_run_at in DB after a successful task run."""
    with session_scope() as session:
        row = session.execute(
            select(TaskSchedule).where(TaskSchedule.component_name == component_name)
        ).scalars().first()
        if not row:
            return
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        row.last_run_at = now
        row.last_error = None
        row.next_run_at = compute_next_run(row.schedule_type, row.schedule_config, now)
        row.updated_at = now


class BaseTask(ABC):
    """
    Abstract base for component background tasks. Subclasses implement run();
    base helps with get_next_run and persisting next_run in DB.
    """

    def __init__(self, component_name: str, schedule_type: str, schedule_config: Optional[Dict[str, Any]] = None):
        self.component_name = component_name
        self.schedule_type = schedule_type
        self.schedule_config = schedule_config or {}
        self.logger = logging.getLogger(self.__class__.__name__)

    def get_next_run(self, last_run: Optional[datetime] = None) -> datetime:
        """Compute next run time from schedule_type and schedule_config."""
        return compute_next_run(self.schedule_type, self.schedule_config, last_run)

    def ensure_scheduled(self, next_run_at: Optional[datetime] = None) -> None:
        """Ensure TaskSchedule row exists so next run survives restarts. Does not overwrite next_run_at on existing row (refetch only when next_run_at hits)."""
        upsert_task_schedule(
            self.component_name,
            self.schedule_type,
            self.schedule_config,
            next_run_at=next_run_at,
        )

    @abstractmethod
    def run(
        self,
        config: Dict[str, Any],
        result_queue: Queue,
        **kwargs: Any,
    ) -> None:
        """
        Execute the task. Subclass should: do work, then call update_after_run(self.component_name), then result_queue.put((component_name, None)).
        """
        pass
