"""
Service layer: save and load bill data from DB.
- UtilityBillRecord: current due bills only (replaced each fetch).
- UtilityBillHistory: archive outgoing run when replacing; history has no current_balance/current_bill_billed_date.
"""
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import delete, select

from dashboard.core.db import session_scope
from dashboard.plugins.utilities_bill_due.backends.base import BillDueInfo
from dashboard.plugins.utilities_bill_due.models import UtilityBillHistory, UtilityBillRecord


def save_bills(component_name: str, items: List[BillDueInfo]) -> None:
    """Replace current run: archive existing rows to UtilityBillHistory, then insert new run into UtilityBillRecord."""
    fetched_at = datetime.now(timezone.utc).replace(tzinfo=None)
    with session_scope() as session:
        # Archive current run to history (before deleting)
        existing = (
            session.execute(
                select(UtilityBillRecord).where(UtilityBillRecord.component_name == component_name)
            )
            .scalars().all()
        )
        for r in existing:
            session.add(
                UtilityBillHistory(
                    fetched_at=r.fetched_at,
                    due_date=r.due_date,
                    paid_date=r.last_payment_date,
                    amount=r.amount_due,
                    usage=r.usage,
                    status=r.raw_status,
                    utility_type=r.utility_type,
                    source=r.source,
                )
            )
        # Replace current run
        session.execute(delete(UtilityBillRecord).where(UtilityBillRecord.component_name == component_name))
        for item in items:
            r = UtilityBillRecord(
                component_name=component_name,
                fetched_at=fetched_at,
                utility_type=getattr(item, "utility_type", None),
                source=getattr(item, "source", None),
                due_date=getattr(item, "due_date", None),
                amount_due=str(getattr(item, "amount_due", "") or ""),
                payment_due=getattr(item, "payment_due", False),
                payment_status=None,
                current_balance=str(getattr(item, "current_balance", "") or ""),
                current_bill_billed_date=getattr(item, "current_bill_billed_date", None),
                last_payment_amount=str(getattr(item, "last_payment_amount", "") or ""),
                last_payment_date=getattr(item, "last_payment_date", None),
                raw_status=getattr(item, "raw_status", None),
                usage=getattr(item, "usage", None),
            )
            session.add(r)


def get_latest_bills(component_name: str) -> List[BillDueInfo]:
    """Return the latest run of bill entries for this component from DB."""
    rows = get_latest_bill_records(component_name)
    return [_row_to_bill(r) for r in rows]


def get_latest_bill_records(component_name: str) -> List[UtilityBillRecord]:
    """Return the latest run of UtilityBillRecord rows for this component (for API serialization)."""
    with session_scope() as session:
        subq = (
            select(UtilityBillRecord.fetched_at)
            .where(UtilityBillRecord.component_name == component_name)
            .order_by(UtilityBillRecord.fetched_at.desc())
            .limit(1)
            .scalar_subquery()
        )
        stmt = (
            select(UtilityBillRecord)
            .where(
                UtilityBillRecord.component_name == component_name,
                UtilityBillRecord.fetched_at == subq,
            )
            .order_by(UtilityBillRecord.due_date.asc().nulls_last(), UtilityBillRecord.source)
        )
        return list(session.execute(stmt).scalars().all())


def get_bill_history_records(limit: Optional[int] = 500) -> List[UtilityBillHistory]:
    """Return historical bills from UtilityBillHistory (global), newest first."""
    with session_scope() as session:
        stmt = (
            select(UtilityBillHistory)
            .order_by(UtilityBillHistory.fetched_at.desc(), UtilityBillHistory.due_date.desc().nulls_last())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(session.execute(stmt).scalars().all())


def _row_to_bill(r: UtilityBillRecord) -> BillDueInfo:
    return BillDueInfo(
        utility_type=r.utility_type,
        source=r.source,
        due_date=r.due_date,
        amount_due=r.amount_due or None,
        payment_due=r.payment_due or False,
        current_balance=r.current_balance or None,
        current_bill_billed_date=r.current_bill_billed_date,
        last_payment_amount=r.last_payment_amount or None,
        last_payment_date=r.last_payment_date,
        raw_status=r.raw_status,
        usage=r.usage or None,
    )
