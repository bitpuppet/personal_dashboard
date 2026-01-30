from .base import BillDueInfo, UtilityBillDueBackend
from .coserv import CoServBackend
from .farmerselectric import FarmersElectricBackend
from .murphytx import MurphyTXBackend

__all__ = ["BillDueInfo", "UtilityBillDueBackend", "CoServBackend", "FarmersElectricBackend", "MurphyTXBackend"]

_BACKENDS = {
    "coserv": CoServBackend,
    "farmerselectric": FarmersElectricBackend,
    "murphytx": MurphyTXBackend,
}


def get_backend(backend_type: str, config: dict, logger=None):
    """Factory: return backend instance for given type."""
    cls = _BACKENDS.get((backend_type or "").lower())
    if not cls:
        return None
    return cls(config, logger=logger)
