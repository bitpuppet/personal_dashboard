"""
Background task: fetch Friday prayer times from mosques, save via service, persist next_run in DB.
"""
from typing import Any, Dict, List, Optional

from dashboard.core.task import (
    BaseTask,
    TaskType,
    update_after_run,
)
from dashboard.plugins.friday_prayer.service import save_friday_times
from dashboard.plugins.friday_prayer.mosque_factory import create_mosque


class FridayPrayerTask(BaseTask):
    """Fetch Friday times from all mosques, save to DB, update next_run."""

    def __init__(self, component_name: str, config: Dict[str, Any]):
        schedule_type, schedule_config = self._schedule_from_config(config)
        super().__init__(component_name, schedule_type, schedule_config)
        self.config = config

    def _schedule_from_config(self, config: Dict[str, Any]) -> tuple:
        daily = config.get("daily_update") or {}
        if daily.get("enabled", True):
            time_str = daily.get("time", "10:00")
            try:
                parts = str(time_str).strip().split(":")
                hour = int(parts[0]) if parts else 10
                minute = int(parts[1]) if len(parts) > 1 else 0
                return TaskType.DAILY, {"time": f"{hour:02d}:{minute:02d}"}
            except (ValueError, IndexError):
                return TaskType.DAILY, {"time": "10:00"}
        return TaskType.INTERVAL_SECONDS, {"interval_seconds": 86400}

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
        mosques = self._build_mosques(config, cache_dir)
        if not mosques:
            try:
                result_queue.put((self.component_name, {}))
            except Exception:
                pass
            return
        times_list: List[dict] = []
        for mosque in mosques:
            try:
                name = mosque.get_name()
                times = mosque.get_friday_times(force_fetch=True)
                if times:
                    times_list.append({"mosque_name": name, "times": times})
            except Exception as e:
                self.logger.exception(f"Friday prayer fetch failed for {mosque.get_name()}: {e}")
        save_friday_times(self.component_name, times_list)
        self.logger.info(f"Friday Prayer: saved {len(times_list)} mosque(s) to DB")
        update_after_run(self.component_name)
        # Convert to cached_times dict for component
        cached = {t["mosque_name"]: t["times"] for t in times_list}
        try:
            result_queue.put((self.component_name, cached))
        except Exception:
            pass

    def _build_mosques(self, config: Dict[str, Any], cache_dir: Optional[str] = None) -> List[Any]:
        mosques = []
        for mosque_config in config.get("mosques") or []:
            mosque_type = mosque_config.get("type")
            if not mosque_type:
                continue
            cfg = dict(mosque_config)
            if cache_dir and "cache_dir" not in cfg:
                cfg["cache_dir"] = cache_dir
            mosque = create_mosque(mosque_type, cfg)
            if mosque:
                mosques.append(mosque)
        return mosques
