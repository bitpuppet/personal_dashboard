"""
Per-plugin API for Task Manager. Mounted at /api/components/task_manager/.
Uses TaskSchedule ORM with Pydantic from_attributes for db_schedules.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from dashboard.core.models import get_all_task_schedule_records


class TaskScheduleResponse(BaseModel):
    """Pydantic view of TaskSchedule for API; serializes from ORM."""

    model_config = ConfigDict(from_attributes=True)

    component_name: Optional[str] = None
    schedule_type: Optional[str] = None
    schedule_config: Optional[Dict[str, Any]] = None
    next_run_at: Optional[datetime] = None
    last_run_at: Optional[datetime] = None
    last_error: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ActiveTimerResponse(BaseModel):
    """One active timer (in-memory; not from DB)."""

    name: str = ""
    next_run_at: Optional[datetime] = None


class TaskManagerResponse(BaseModel):
    """Response for GET /data."""

    db_schedules: List[TaskScheduleResponse]
    active_timers: List[ActiveTimerResponse]


def get_router(dashboard_app) -> Optional[APIRouter]:
    """Return router for this plugin; mounted with prefix /api/components/task_manager."""
    router = APIRouter(tags=["Task Manager"])

    @router.get("/data", response_model=TaskManagerResponse)
    def get_data() -> TaskManagerResponse:
        """Return DB schedule records (ORM serialized via Pydantic) and active timers."""
        records = get_all_task_schedule_records()
        schedules = [TaskScheduleResponse.model_validate(r) for r in records]

        active_timers = dashboard_app.task_manager.get_active_timers()
        active_list = [
            ActiveTimerResponse(name=t["name"], next_run_at=t.get("next_run_at"))
            for t in active_timers
        ]
        return TaskManagerResponse(db_schedules=schedules, active_timers=active_list)

    return router
