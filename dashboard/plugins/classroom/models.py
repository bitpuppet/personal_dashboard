"""
SQLAlchemy models for classroom assignments: one row per fetch per component.
"""
from datetime import datetime

from sqlalchemy import Column, String, DateTime, Integer, JSON

from dashboard.core.db import Base


class ClassroomAssignmentRecord(Base):
    """One fetch of assignments. data is JSON array of assignment dicts (due_datetime as ISO string)."""
    __tablename__ = "classroom_assignment_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    component_name = Column(String(255), nullable=False, index=True)
    fetched_at = Column(DateTime(timezone=False), nullable=False, index=True)
    data = Column(JSON, nullable=False)  # list of {student_name, course_name, title, due_datetime, status, ...}
