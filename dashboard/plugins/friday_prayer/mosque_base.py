from abc import ABC, abstractmethod
from typing import Dict, Optional
import importlib
import logging
from dashboard.core.cache_helper import CacheHelper
import requests

class MosqueBase(ABC):
    def __init__(self, config: Dict):
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)
        self.cache_helper = CacheHelper(config.get('cache_dir'), "friday_prayer")
    
    @abstractmethod
    def get_name(self) -> str:
        """Get mosque name"""
        pass
    
    @abstractmethod
    def get_friday_times(self, force_fetch: bool = False) -> Optional[Dict]:
        """Get Friday prayer times
        Args:
            force_fetch: If True, bypass cache and fetch fresh content
        Returns:
            dict with keys: khutbah
        """
        pass

    def _fetch_page_content(self, url: str, force_fetch: bool = False) -> Optional[str]:
        """Fetch page content with caching
        Args:
            url: URL to fetch
            force_fetch: If True, bypass cache and fetch fresh content
        """
        if not force_fetch:
            # Try to get from cache first
            cached_content = self.cache_helper.get_cached_content(url)
            if cached_content:
                return cached_content
        
        # Fetch fresh content
        try:
            logging.info(f"Fetching fresh content from {url}")
            response = requests.get(url)
            response.raise_for_status()
            self.cache_helper.save_to_cache(url, response.text)
            return response.text
        except Exception as e:
            self.logger.error(f"Error fetching page: {e}")
            return None

    def _get_suffix(self, num: int) -> str:
        """Return the appropriate suffix for a number (1st, 2nd, 3rd, etc.)"""
        if num == 1:
            return "st"
        elif num == 2:
            return "nd"
        elif num == 3:
            return "rd"
        return "th" 
    