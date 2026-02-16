"""
SQLAlchemy models for prayer times: one row per fetch per component.
"""
from datetime import date, datetime

from sqlalchemy import Column, String, Date, DateTime, Integer, JSON

from dashboard.core.db import Base


class PrayerTimesRecord(Base):
    """One prayer times fetch. data is JSON: {prayer_name: "HH:MM" or ISO datetime string}."""
    __tablename__ = "prayer_times_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    component_name = Column(String(255), nullable=False, index=True)
    fetched_at = Column(DateTime(timezone=False), nullable=False, index=True)
    prayer_date = Column(Date, nullable=False, index=True)
    data = Column(JSON, nullable=False)  # {prayer_name: "HH:MM" or ISO string}
