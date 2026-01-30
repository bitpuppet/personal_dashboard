from .base import BillDueInfo, UtilityBillDueBackend
from .murphytx import MurphyTXBackend

__all__ = ["BillDueInfo", "UtilityBillDueBackend", "MurphyTXBackend"]

_BACKENDS = {
    "murphytx": MurphyTXBackend,
}


def get_backend(backend_type: str, config: dict, logger=None):
    """Factory: return backend instance for given type."""
    cls = _BACKENDS.get((backend_type or "").lower())
    if not cls:
        return None
    return cls(config, logger=logger)
