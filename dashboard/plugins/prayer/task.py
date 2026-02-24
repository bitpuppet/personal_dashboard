"""
Background task: fetch prayer times from backend, save via service, persist next_run in DB.
"""
from datetime import datetime
from typing import Any, Dict, Optional

from dashboard.core.task import (
    BaseTask,
    TaskType,
    update_after_run,
)
from dashboard.plugins.prayer.prayer_base import AladhanBackend
from dashboard.plugins.prayer.service import save_prayer_times


class PrayerTimesTask(BaseTask):
    """Fetch prayer times from backend, save to DB, update next_run."""

    def __init__(self, component_name: str, config: Dict[str, Any]):
        schedule_type, schedule_config = self._schedule_from_config(config)
        super().__init__(component_name, schedule_type, schedule_config)
        self.config = config

    def _schedule_from_config(self, config: Dict[str, Any]) -> tuple:
        schedule_time = config.get("schedule_time")
        update_interval = config.get("update_interval", 3600)
        if schedule_time:
            try:
                parts = str(schedule_time).strip().split(":")
                hour = int(parts[0]) if parts else 0
                minute = int(parts[1]) if len(parts) > 1 else 0
                return TaskType.DAILY, {"time": f"{hour:02d}:{minute:02d}"}
            except (ValueError, IndexError):
                return TaskType.DAILY, {"time": "10:00"}
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
        backend = self._create_backend(config, cache_dir)
        if not backend:
            try:
                result_queue.put((self.component_name, None))
            except Exception:
                pass
            return
        try:
            prayer_times = backend.get_prayer_times(force_fetch=True)
        except Exception as e:
            self.logger.exception(f"Prayer Times backend failed: {e}")
            try:
                result_queue.put((self.component_name, None))
            except Exception:
                pass
            return
        if not prayer_times:
            try:
                result_queue.put((self.component_name, None))
            except Exception:
                pass
            return
        today = datetime.now().date()
        save_prayer_times(self.component_name, today, prayer_times)
        self.logger.info(f"Prayer Times: saved to DB for {today}")
        update_after_run(self.component_name)
        try:
            result_queue.put((self.component_name, prayer_times))
        except Exception:
            pass

    def _create_backend(self, config: Dict[str, Any], cache_dir: Optional[str] = None) -> Optional[Any]:
        backend_type = config.get("backend", "aladhan")
        if backend_type != "aladhan":
            self.logger.warning(f"Prayer task only supports aladhan backend, got {backend_type}")
            return None
        cfg = dict(config)
        if cache_dir and "cache_dir" not in cfg:
            cfg["cache_dir"] = cache_dir
        return AladhanBackend(cfg)
