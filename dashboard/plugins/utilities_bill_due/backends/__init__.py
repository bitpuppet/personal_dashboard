from .base import BillDueInfo, UtilityBillDueBackend
from .coserv import CoServBackend
from .farmerselectric import FarmersElectricBackend
from .manual import ManualBackend
from .murphytx import MurphyTXBackend

__all__ = ["BillDueInfo", "UtilityBillDueBackend", "CoServBackend", "FarmersElectricBackend", "ManualBackend", "MurphyTXBackend"]

_BACKENDS = {
    "coserv": CoServBackend,
    "farmerselectric": FarmersElectricBackend,
    "manual": ManualBackend,
    "murphytx": MurphyTXBackend,
}


def get_backend(backend_type: str, config: dict, logger=None):
    """Factory: return backend instance for given type."""
    cls = _BACKENDS.get((backend_type or "").lower())
    if not cls:
        return None
    return cls(config, logger=logger)
