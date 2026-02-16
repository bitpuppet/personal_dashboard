"""
Manual backend: define utility rows in config when scraping is not available.
Each entry provides name (utility label), source (provider), due_date, optional amount.
due_date can be YYYY-MM-DD or "on every N" / "every N" (day of month 1-31); then the
next due date is computed from today.
No network, no cache.
"""
import logging
import re
from calendar import monthrange
from datetime import date, datetime
from typing import List, Optional

from .base import BillDueInfo, UtilityBillDueBackend

try:
    from dateutil import parser as dateutil_parser
    HAS_DATEUTIL = True
except ImportError:
    HAS_DATEUTIL = False

# "on every 14", "every 14", "every 14th" -> day of month 1-31
_DAY_OF_MONTH_RE = re.compile(
    r"(?:on\s+)?every\s+(\d{1,2})(?:st|nd|rd|th)?\s*$",
    re.IGNORECASE,
)


def _next_due_date_for_day_of_month(day: int) -> Optional[date]:
    """Return the next due date for a given day of month (1-31). Uses current or next month."""
    if not 1 <= day <= 31:
        return None
    today = date.today()
    year, month = today.year, today.month
    _, last = monthrange(year, month)
    day_this_month = min(day, last)
    candidate = date(year, month, day_this_month)
    if candidate >= today:
        return candidate
    # Next month
    if month == 12:
        year, month = year + 1, 1
    else:
        month += 1
    _, last = monthrange(year, month)
    day_next = min(day, last)
    return date(year, month, day_next)


def _parse_due_date(s: Optional[str]) -> Optional[date]:
    """Parse due_date: YYYY-MM-DD, or 'on every N' / 'every N' (day of month); then compute next due."""
    if not s:
        return None
    s = str(s).strip()
    # Day-of-month: "on every 14", "every 14", "every 14th"
    m = _DAY_OF_MONTH_RE.search(s)
    if m:
        day = int(m.group(1))
        if 1 <= day <= 31:
            return _next_due_date_for_day_of_month(day)
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        pass
    if HAS_DATEUTIL:
        try:
            dt = dateutil_parser.parse(s)
            return dt.date() if hasattr(dt, "date") else dt
        except Exception:
            pass
    return None


class ManualBackend(UtilityBillDueBackend):
    """Config-driven backend: return one BillDueInfo per entry in config['entries']."""

    def __init__(self, config: dict, logger=None):
        self.config = config or {}
        self.logger = logger or logging.getLogger(__name__)

    def get_bill_due_info(self) -> List[BillDueInfo]:
        entries = self.config.get("entries")
        if not isinstance(entries, list):
            if entries is not None:
                self.logger.warning(f"Manual backend: 'entries' must be a list, got {type(entries).__name__}")
            return []

        results: List[BillDueInfo] = []
        today = date.today()

        for i, entry in enumerate(entries):
            if not isinstance(entry, dict):
                self.logger.warning(f"Manual backend: entry[{i}] is not a dict, skipping")
                continue

            name = entry.get("name")
            source = entry.get("source")
            if not name and not source:
                self.logger.warning(f"Manual backend: entry[{i}] missing name and source, skipping")
                continue

            name = (name or "").strip() or None
            source = (source or "").strip() or None
            if not name:
                name = source or "Manual"
            if not source:
                source = name or "Manual"

            due_date = _parse_due_date(entry.get("due_date"))
            if due_date is None and entry.get("due_date") is not None:
                self.logger.debug(f"Manual backend: entry[{i}] invalid due_date {entry.get('due_date')!r}")

            amount_raw = entry.get("amount")
            amount_due: Optional[str] = None
            if amount_raw is not None:
                if isinstance(amount_raw, (int, float)):
                    amount_due = f"{amount_raw:.2f}" if isinstance(amount_raw, float) else str(amount_raw)
                else:
                    amount_due = str(amount_raw).strip() or None

            payment_due = due_date is not None and due_date <= today

            status_override = entry.get("status")
            raw_status = (str(status_override).strip() or None) if status_override is not None else None

            results.append(
                BillDueInfo(
                    utility_type=name,
                    source=source,
                    due_date=due_date,
                    amount_due=amount_due,
                    payment_due=payment_due,
                    current_balance=None,
                    current_bill_billed_date=None,
                    last_payment_amount=None,
                    last_payment_date=None,
                    raw_status=raw_status,
                    usage=None,
                )
            )

        return results
