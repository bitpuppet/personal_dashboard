"""
SQLAlchemy models for Friday prayer times: one row per fetch per component.
"""
from datetime import datetime

from sqlalchemy import Column, String, DateTime, Integer, JSON

from dashboard.core.db import Base


class FridayPrayerRecord(Base):
    """One fetch of Friday times. data is JSON list of {mosque_name, times}."""
    __tablename__ = "friday_prayer_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    component_name = Column(String(255), nullable=False, index=True)
    fetched_at = Column(DateTime(timezone=False), nullable=False, index=True)
    data = Column(JSON, nullable=False)  # [{mosque_name, times: {khutbah, ...}}, ...]
