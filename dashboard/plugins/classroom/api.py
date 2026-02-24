"""
Per-plugin API for Classroom Homework. Mounted at /api/classroom/.
Uses ClassroomAssignmentRecord ORM with Pydantic from_attributes.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from .models import ClassroomAssignmentRecord
from .service import get_latest_assignment_record

COMPONENT_NAME = "Classroom Homework"


class ClassroomAssignmentRecordResponse(BaseModel):
    """Pydantic view of ClassroomAssignmentRecord for API; serializes from ORM."""

    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = None
    component_name: Optional[str] = None
    fetched_at: Optional[datetime] = None
    data: Optional[List[Dict[str, Any]]] = None


def get_router(dashboard_app) -> Optional[APIRouter]:
    """Return router for this plugin; mounted with prefix /api/classroom."""
    router = APIRouter(tags=["Classroom Homework"])

    @router.get("/data", response_model=ClassroomAssignmentRecordResponse)
    def get_data() -> ClassroomAssignmentRecordResponse:
        """Return latest assignment record from DB (ORM serialized via Pydantic)."""
        record = get_latest_assignment_record(COMPONENT_NAME)
        if record is None:
            return ClassroomAssignmentRecordResponse(component_name=COMPONENT_NAME, data=[])
        return ClassroomAssignmentRecordResponse.model_validate(record)

    return router
