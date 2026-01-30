"""
Base type and interface for utilities bill-due backends.
All backends return List[BillDueInfo]; no dicts.
"""
from abc import ABC, abstractmethod
from collections import namedtuple
from datetime import date, datetime
from typing import List, Optional

# Named tuple for one bill/utility entry. Amount is fetched but not shown in UI.
BillDueInfo = namedtuple(
    "BillDueInfo",
    [
        "utility_type",  # "water" | "gas" | "electric"
        "source",       # e.g. "Murphy TX"
        "due_date",     # date or None
        "amount_due",   # str or None (fetched, not displayed)
        "payment_due",  # bool
        "current_balance",           # str/float or None
        "current_bill_billed_date", # date or None
        "last_payment_amount",      # str or None
        "last_payment_date",        # date or None
        "raw_status",   # str or None for debugging
    ],
    defaults=(None,) * 10,
)


class UtilityBillDueBackend(ABC):
    """Abstract backend: return list of BillDueInfo from one provider."""

    @abstractmethod
    def get_bill_due_info(self) -> List[BillDueInfo]:
        """Fetch and return bill due info. Use BillDueInfo(...), not dicts."""
        pass
