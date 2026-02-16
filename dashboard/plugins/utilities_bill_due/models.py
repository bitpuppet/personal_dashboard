"""
SQLAlchemy models for utilities bill data.

- UtilityBillRecord: current due bills only (one run per component; replaced each fetch).
- UtilityBillHistory: all past bills (archived when replaced); no current_balance/current_bill_billed_date.
"""
from datetime import date, datetime

from sqlalchemy import Column, String, Date, Boolean, Text, DateTime, Integer

from dashboard.core.db import Base


class UtilityBillRecord(Base):
    """Current due bills only. One run per component; replaced on each fetch."""
    __tablename__ = "utility_bill_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    component_name = Column(String(255), nullable=False, index=True)
    fetched_at = Column(DateTime(timezone=False), nullable=False, index=True)

    utility_type = Column(String(64), nullable=True)
    source = Column(String(255), nullable=True)
    due_date = Column(Date, nullable=True)
    amount_due = Column(String(64), nullable=True)
    payment_due = Column(Boolean, default=False)
    payment_status = Column(String(64), nullable=True)  # "Due", "Autopay", etc.
    current_balance = Column(String(64), nullable=True)
    current_bill_billed_date = Column(Date, nullable=True)
    last_payment_amount = Column(String(64), nullable=True)
    last_payment_date = Column(Date, nullable=True)
    raw_status = Column(Text, nullable=True)
    usage = Column(String(128), nullable=True)


class UtilityBillHistory(Base):
    """Historical bills (archived when superseded by a new run). Columns: id, fetched_at, due_date, paid_date, amount, usage, status, utility_type, source."""
    __tablename__ = "utility_bill_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    fetched_at = Column(DateTime(timezone=False), nullable=False, index=True)
    due_date = Column(Date, nullable=True, index=True)
    paid_date = Column(Date, nullable=True)
    amount = Column(String(64), nullable=True)
    usage = Column(String(128), nullable=True)
    status = Column(String(128), nullable=True)
    utility_type = Column(String(64), nullable=True)
    source = Column(String(255), nullable=True)
