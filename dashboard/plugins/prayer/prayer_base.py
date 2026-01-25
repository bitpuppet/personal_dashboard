import requests
from datetime import datetime, time, timedelta
from typing import Dict, Any, Optional
import logging
from abc import ABC, abstractmethod
from dashboard.core.cache_helper import CacheHelper

class PrayerBackend(ABC):
    """Base class for prayer time calculation backends"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)
        self.cache_helper = CacheHelper(config.get('cache_dir'), "prayer_times")
    
    @abstractmethod
    def get_prayer_times(self, force_fetch: bool = False) -> Optional[Dict[str, datetime]]:
        """Get prayer times for today
        Args:
            force_fetch: If True, bypass cache and fetch fresh data
        Returns:
            Dictionary of prayer times or None on error
        """
        pass

class AladhanBackend(PrayerBackend):
    """Prayer times backend using api.aladhan.com"""
    
    PRAYER_NAMES = {
        'Fajr': 'Fajr',
        'Dhuhr': 'Dhuhr',
        'Asr': 'Asr',
        'Maghrib': 'Maghrib',
        'Isha': 'Isha'
    }
    
    def get_prayer_times(self, force_fetch: bool = False) -> Optional[Dict[str, datetime]]:
        """Get prayer times for current day"""
        try:
            today = datetime.now().date()
            cache_key = f"prayer_times_{today.strftime('%Y-%m-%d')}"
            
            if not force_fetch:
                self.logger.info(f"Trying to get from cache: {cache_key}")
                # Try to get from cache first
                cached_times = self.cache_helper.get_cached_content(cache_key)
                if cached_times:
                    self.logger.info(f"Got from cache: {cached_times}")
                    return self._parse_cached_times(cached_times)
            
            # Fetch fresh times from API
            self.logger.info("Fetching prayer times from API")
            prayer_times = self._get_api_prayer_times()
            
            # Cache the results
            self.cache_helper.save_to_cache(cache_key, self._format_times_for_cache(prayer_times))
            
            return prayer_times
            
        except Exception as e:
            self.logger.error(f"Error fetching prayer times: {e}")
            return None
    
    def _format_times_for_cache(self, prayer_times: Dict[str, datetime]) -> str:
        """Format prayer times for caching"""
        formatted = {}
        for prayer, time in prayer_times.items():
            formatted[prayer] = time.strftime('%Y-%m-%d %H:%M:%S')
        return str(formatted)
    
    def _parse_cached_times(self, cached_content: str) -> Dict[str, datetime]:
        """Parse cached prayer times back into datetime objects"""
        try:
            # Convert string representation back to dict
            time_dict = eval(cached_content)
            result = {}
            for prayer, time_str in time_dict.items():
                result[prayer] = datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S')
            
            # Override with any test times
            now = datetime.now()
            today = datetime.now().date()
            test_times = self.config.get('test_schedule', {}).get('times', {})
            self.logger.info(f"Test times: {test_times}")
            for prayer, time_str in test_times.items():
                self.logger.info(f"Overriding {prayer} with test time: {time_str}")
                try:
                    hour, minute = map(int, time_str.split(':'))
                    prayer_time = datetime.combine(today, time(hour, minute))
                    self.logger.info(f"Combined {prayer} with test time: {prayer_time}")
                    # If time has passed today, schedule for tomorrow
                    if prayer_time <= now:
                        prayer_time += timedelta(days=1)
                    
                    result[prayer] = prayer_time
                    self.logger.debug(f"Overrode {prayer} with test time: {prayer_time}")
                except (ValueError, TypeError) as e:
                    self.logger.error(f"Invalid test time format for {prayer}: {time_str}")
            
            return result
        except Exception as e:
            self.logger.error(f"Error parsing cached times: {e}")
            return None

    def _get_api_prayer_times(self) -> Dict[str, datetime]:
        """Fetch prayer times from API and override with test times if configured"""
        self.logger.info("Fetching prayer times from API")
        today = datetime.now().date()
        now = datetime.now()
        
        # Get API prayer times
        lat = self.config.get('lat')
        lon = self.config.get('lon')
        method = self.config.get('calculation_method', 2)
        
        url = f"http://api.aladhan.com/v1/timings/{datetime.now().strftime('%d-%m-%Y')}"
        params = {
            'latitude': lat,
            'longitude': lon,
            'method': method
        }
        
        self.logger.info(f"Making API request to {url} with params {params}")
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        
        # Get all API prayer times first
        timings = data['data']['timings']
        prayer_times = {}
        
        for prayer, display_name in self.PRAYER_NAMES.items():
            if prayer in timings:
                prayer_times[display_name] = datetime.strptime(
                    f"{today.strftime('%Y-%m-%d')} {timings[prayer]}",
                    '%Y-%m-%d %H:%M'
                )
        
        # Override with any test times
        test_times = self.config.get('test_schedule', {}).get('times', {})
        self.logger.info(f"Test times: {test_times}")
        for prayer, time_str in test_times.items():
            self.logger.info(f"Overriding {prayer} with test time: {time_str}")
            try:
                hour, minute = map(int, time_str.split(':'))
                prayer_time = datetime.combine(today, time(hour, minute))
                self.logger.info(f"Combined {prayer} with test time: {prayer_time}")
                # If time has passed today, schedule for tomorrow
                if prayer_time <= now:
                    prayer_time += timedelta(days=1)
                
                prayer_times[prayer] = prayer_time
                self.logger.debug(f"Overrode {prayer} with test time: {prayer_time}")
            except (ValueError, TypeError) as e:
                self.logger.error(f"Invalid test time format for {prayer}: {time_str}")
        
        self.logger.info(f"Final prayer times: {prayer_times}")
        return prayer_times 