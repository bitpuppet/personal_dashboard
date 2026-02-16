"""
Background task: fetch weather data per component, save via service, persist next_run in DB.
One task class; component_name distinguishes Hourly Weather, Weekly Weather, Weather.
"""
import logging
from typing import Any, Dict, Optional

import requests

from dashboard.core.task import BaseTask, TaskType, update_after_run
from dashboard.plugins.weather.service import save_weather
from dashboard.plugins.weather.weather_backend import (
    NWSWeatherBackend,
    OpenWeatherMapBackend,
)

logger = logging.getLogger(__name__)

NWS_HEADERS = {
    "User-Agent": "(Personal Dashboard, your@email.com)",
    "Accept": "application/geo+json",
}


class WeatherTask(BaseTask):
    """Fetch weather for one component (Hourly Weather, Weekly Weather, or Weather)."""

    def __init__(self, component_name: str, config: Dict[str, Any]):
        schedule_type, schedule_config = self._schedule_from_config(config)
        super().__init__(component_name, schedule_type, schedule_config)
        self.config = config

    def _schedule_from_config(self, config: Dict[str, Any]) -> tuple:
        interval = config.get("update_interval")
        if interval is not None:
            try:
                sec = int(interval)
                return TaskType.INTERVAL_SECONDS, {"interval_seconds": max(60, sec)}
            except (TypeError, ValueError):
                pass
        # Default: daily at 10:00
        return TaskType.DAILY, {"time": "10:00"}

    def run(
        self,
        config: Dict[str, Any],
        result_queue: Any,
        config_data: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        data = None
        if self.component_name == "Hourly Weather":
            data = self._fetch_hourly(config, config_data)
        elif self.component_name == "Weekly Weather":
            data = self._fetch_weekly(config, config_data)
        else:
            # "Weather" (current/7-day)
            data = self._fetch_current(config, config_data)

        if data and "error" not in data:
            save_weather(self.component_name, data)
            logger.info(f"Weather: saved data for {self.component_name}")
        update_after_run(self.component_name)
        try:
            result_queue.put((self.component_name, data))
        except Exception:
            pass

    def _backend_config(self, config: Dict[str, Any], config_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        cfg = dict(config)
        if config_data:
            cache_dir = config_data.get("cache", {}).get("directory")
            if cache_dir:
                cfg["cache_dir"] = cache_dir
        return cfg

    def _fetch_hourly(self, config: Dict[str, Any], config_data: Optional[Dict[str, Any]]) -> Optional[Dict]:
        """Fetch NWS hourly forecast (points -> forecastHourly)."""
        lat = config.get("lat")
        lon = config.get("lon")
        if lat is None or lon is None:
            return {"error": "lat/lon required for Hourly Weather"}
        try:
            lat, lon = float(lat), float(lon)
        except (TypeError, ValueError):
            return {"error": "Invalid lat/lon"}
        points_url = f"https://api.weather.gov/points/{lat},{lon}"
        try:
            r = requests.get(points_url, headers=NWS_HEADERS, timeout=15)
            r.raise_for_status()
            points_data = r.json()
        except Exception as e:
            logger.exception("Hourly: points fetch failed: %s", e)
            return {"error": str(e)}
        hourly_url = points_data.get("properties", {}).get("forecastHourly")
        if not hourly_url:
            return {"error": "No forecastHourly in points"}
        try:
            r = requests.get(hourly_url, headers=NWS_HEADERS, timeout=15)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            logger.exception("Hourly: forecast fetch failed: %s", e)
            return {"error": str(e)}

    def _fetch_weekly(self, config: Dict[str, Any], config_data: Optional[Dict[str, Any]]) -> Optional[Dict]:
        """Fetch weekly forecast via backend (NWS or OpenWeatherMap)."""
        backend_type = config.get("backend", "nws")
        cfg = self._backend_config(config, config_data)
        if backend_type == "nws":
            backend = NWSWeatherBackend(cfg)
        elif backend_type == "openweathermap":
            backend = OpenWeatherMapBackend(cfg)
        else:
            return {"error": f"Unknown backend: {backend_type}"}
        return backend.get_weather(force_fetch=True)

    def _fetch_current(self, config: Dict[str, Any], config_data: Optional[Dict[str, Any]]) -> Optional[Dict]:
        """Fetch current/7-day via OpenWeatherMap (Weather component)."""
        cfg = self._backend_config(config, config_data)
        backend = OpenWeatherMapBackend(cfg)
        return backend.get_weather(force_fetch=True)
