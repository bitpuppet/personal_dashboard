"""
SQLAlchemy models for weather cache: one row per component per fetch.
"""
from datetime import datetime

from sqlalchemy import Column, String, DateTime, Integer, JSON

from dashboard.core.db import Base


class WeatherRecord(Base):
    """One fetch of weather data. component_name: 'Hourly Weather' | 'Weekly Weather' | 'Weather'; data: JSON."""
    __tablename__ = "weather_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    component_name = Column(String(255), nullable=False, index=True)
    fetched_at = Column(DateTime(timezone=False), nullable=False, index=True)
    data = Column(JSON, nullable=False)
