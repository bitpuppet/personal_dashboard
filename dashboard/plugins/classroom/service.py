"""
Service layer: save and load classroom assignments from DB.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select, delete

from dashboard.core.db import session_scope
from dashboard.plugins.classroom.models import ClassroomAssignmentRecord


def _serialize_assignments(assignments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Make assignments JSON-serializable (datetime -> ISO string)."""
    out = []
    for a in assignments:
        row = dict(a)
        if "due_datetime" in row and row["due_datetime"] is not None:
            dt = row["due_datetime"]
            if hasattr(dt, "isoformat"):
                row["due_datetime"] = dt.isoformat()
        out.append(row)
    return out


def _deserialize_assignments(data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Parse due_datetime ISO string back to datetime."""
    out = []
    for a in data:
        row = dict(a)
        if "due_datetime" in row and isinstance(row["due_datetime"], str):
            try:
                row["due_datetime"] = datetime.fromisoformat(
                    row["due_datetime"].replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                pass
        out.append(row)
    return out


def save_assignments(component_name: str, assignments: List[Dict[str, Any]]) -> None:
    """Replace this component's assignments with a new run (delete previous, insert one row)."""
    fetched_at = datetime.now(timezone.utc).replace(tzinfo=None)
    data = _serialize_assignments(assignments)
    with session_scope() as session:
        session.execute(
            delete(ClassroomAssignmentRecord).where(
                ClassroomAssignmentRecord.component_name == component_name
            )
        )
        session.add(
            ClassroomAssignmentRecord(
                component_name=component_name,
                fetched_at=fetched_at,
                data=data,
            )
        )


def get_latest_assignments(component_name: str) -> List[Dict[str, Any]]:
    """Return the latest assignments for this component (most recent fetch)."""
    row = get_latest_assignment_record(component_name)
    if row and row.data:
        return _deserialize_assignments(row.data)
    return []


def get_latest_assignment_record(component_name: str) -> Optional[ClassroomAssignmentRecord]:
    """Return the latest ClassroomAssignmentRecord row for this component (for API serialization)."""
    with session_scope() as session:
        return (
            session.execute(
                select(ClassroomAssignmentRecord)
                .where(ClassroomAssignmentRecord.component_name == component_name)
                .order_by(ClassroomAssignmentRecord.fetched_at.desc())
                .limit(1)
            )
            .scalars().first()
        )
