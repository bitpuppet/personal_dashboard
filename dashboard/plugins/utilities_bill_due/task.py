"""
Background task: fetch bills from backends, save via service, persist next_run in DB.
"""
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from dashboard.core.task import (
    BaseTask,
    TaskType,
    update_after_run,
    upsert_task_schedule,
)
from dashboard.plugins.utilities_bill_due.backends import get_backend, BillDueInfo
from dashboard.plugins.utilities_bill_due.service import save_bills


class UtilitiesBillDueTask(BaseTask):
    """Fetch bill due info from all backends, save to DB, update next_run."""

    def __init__(self, component_name: str, config: Dict[str, Any]):
        schedule_type, schedule_config = self._schedule_from_config(config)
        super().__init__(component_name, schedule_type, schedule_config)
        self.config = config

    def _schedule_from_config(self, config: Dict[str, Any]) -> tuple:
        schedule_time = config.get("schedule_time")
        update_interval = config.get("update_interval", 86400)
        if schedule_time:
            try:
                parts = str(schedule_time).strip().split(":")
                hour = int(parts[0]) if parts else 0
                minute = int(parts[1]) if len(parts) > 1 else 0
                return TaskType.DAILY, {"time": f"{hour:02d}:{minute:02d}"}
            except (ValueError, IndexError):
                return TaskType.DAILY, {"time": "07:00"}
        sec = update_interval if update_interval < 100000 else update_interval // 1000
        return TaskType.INTERVAL_SECONDS, {"interval_seconds": sec}

    def run(
        self,
        config: Dict[str, Any],
        result_queue: Any,
        config_data: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        cache_dir = None
        if config_data:
            cache_dir = config_data.get("cache", {}).get("directory")
        backends = self._build_backends(config, cache_dir)
        if not backends:
            self.logger.warning("Utilities Bill Due: no backends configured")
            try:
                result_queue.put((self.component_name, None))
            except Exception:
                pass
            return

        all_items: List[BillDueInfo] = []
        for backend in backends:
            try:
                items = backend.get_bill_due_info()
                all_items.extend(items)
            except Exception as e:
                self.logger.exception(f"Utilities Bill Due backend failed: {e}")

        all_items.sort(key=lambda x: x.due_date or date(9999, 12, 31))
        save_bills(self.component_name, all_items)
        self.logger.info(f"Utilities Bill Due: saved {len(all_items)} items to DB")
        update_after_run(self.component_name)
        try:
            result_queue.put((self.component_name, None))
        except Exception:
            pass

    def _build_backends(self, config: Dict[str, Any], cache_dir: Optional[str] = None) -> List[Any]:
        backends = []
        component_headless = config.get("headless")
        for entry in config.get("backends") or []:
            backend_type = entry.get("type")
            if not backend_type:
                continue
            entry_config = dict(entry)
            if "headless" not in entry_config and component_headless is not None:
                entry_config["headless"] = component_headless
            if cache_dir and "cache_dir" not in entry_config:
                entry_config["cache_dir"] = cache_dir
            be = get_backend(backend_type, entry_config, logger=self.logger)
            if be:
                backends.append(be)
        return backends
