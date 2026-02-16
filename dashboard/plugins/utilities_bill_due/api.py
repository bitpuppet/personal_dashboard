"""
Per-plugin API for Utilities Bill Due. Mounted at /api/utilities_bill_due/.
- /data: current due bills (UtilityBillRecord).
- /data/history: historical bills (UtilityBillHistory; no current_balance/current_bill_billed_date).
"""
from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from .models import UtilityBillHistory, UtilityBillRecord
from .service import get_bill_history_records, get_latest_bill_records

COMPONENT_NAME = "Utilities Bill Due"


class UtilityBillRecordResponse(BaseModel):
    """Pydantic view of UtilityBillRecord (current due bills)."""

    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = None
    component_name: Optional[str] = None
    fetched_at: Optional[datetime] = None
    utility_type: Optional[str] = None
    source: Optional[str] = None
    due_date: Optional[date] = None
    amount_due: Optional[str] = None
    payment_due: bool = False
    payment_status: Optional[str] = None
    current_balance: Optional[str] = None
    current_bill_billed_date: Optional[date] = None
    last_payment_amount: Optional[str] = None
    last_payment_date: Optional[date] = None
    raw_status: Optional[str] = None
    usage: Optional[str] = None


class UtilityBillHistoryResponse(BaseModel):
    """Pydantic view of UtilityBillHistory: id, fetched_at, due_date, paid_date, amount, usage, status, utility_type, source."""

    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = None
    fetched_at: Optional[datetime] = None
    due_date: Optional[date] = None
    paid_date: Optional[date] = None
    amount: Optional[str] = None
    usage: Optional[str] = None
    status: Optional[str] = None
    utility_type: Optional[str] = None
    source: Optional[str] = None


class BillsResponse(BaseModel):
    """Response for GET /data (current)."""

    bills: List[UtilityBillRecordResponse]


class BillsHistoryResponse(BaseModel):
    """Response for GET /data/history."""

    bills: List[UtilityBillHistoryResponse]


def get_router(dashboard_app) -> Optional[APIRouter]:
    """Return router for this plugin; mounted with prefix /api/utilities_bill_due."""
    router = APIRouter(tags=["Utilities Bill Due"])

    @router.get("/data", response_model=BillsResponse)
    def get_bills() -> BillsResponse:
        """Return current due bills from UtilityBillRecord."""
        try:
            records = get_latest_bill_records(COMPONENT_NAME)
        except Exception:
            return BillsResponse(bills=[])
        return BillsResponse(bills=[UtilityBillRecordResponse.model_validate(r) for r in records])

    @router.get("/data/history", response_model=BillsHistoryResponse)
    def get_bills_history(limit: Optional[int] = 500) -> BillsHistoryResponse:
        """Return historical bills from UtilityBillHistory (all utilities). Use ?limit= to cap (default 500)."""
        try:
            records = get_bill_history_records(limit=limit)
        except Exception:
            return BillsHistoryResponse(bills=[])
        return BillsHistoryResponse(bills=[UtilityBillHistoryResponse.model_validate(r) for r in records])

    return router
