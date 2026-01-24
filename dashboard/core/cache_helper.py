import os
import json
from datetime import datetime
import logging
from typing import Optional, Dict
import hashlib

logger = logging.getLogger(__name__)

class CacheHelper:
    DEFAULT_CACHE_DIR = ".cache"
    
    def __init__(self, cache_dir: Optional[str] = None, component_name: str = ""):
        """Initialize cache helper with specific cache directory
        Args:
            cache_dir: Base cache directory from config, if None uses DEFAULT_CACHE_DIR
            component_name: Component specific subdirectory
        """
        # Use config cache_dir or default, then add component subdirectory
        base_dir = os.path.expanduser(cache_dir or self.DEFAULT_CACHE_DIR)
        self.cache_dir = os.path.join(base_dir, component_name) if component_name else base_dir
        os.makedirs(self.cache_dir, exist_ok=True)
    
    def _get_cache_file(self, url: str) -> str:
        """Generate cache filename from URL"""
        # Create a unique filename based on URL
        url_hash = hashlib.md5(url.encode()).hexdigest()
        return os.path.join(self.cache_dir, f"{url_hash}.json")
    
    def get_cached_content(self, url: str) -> Optional[str]:
        """Get cached content if it exists and is from today"""
        try:
            cache_file = self._get_cache_file(url)
            if not os.path.exists(cache_file):
                return None
            
            with open(cache_file, 'r') as f:
                cached = json.load(f)
            
            # Check if cache is from today
            cache_date = datetime.strptime(cached['date'], '%Y-%m-%d').date()
            if cache_date == datetime.now().date():
                return cached['content']
            
            return None
            
        except Exception as e:
            logger.error(f"Error reading cache: {e}")
            return None
    
    def save_to_cache(self, url: str, content: str) -> None:
        """Save content to cache with today's date"""
        try:
            cache_data = {
                'date': datetime.now().strftime('%Y-%m-%d'),
                'content': content
            }
            
            cache_file = self._get_cache_file(url)
            with open(cache_file, 'w') as f:
                json.dump(cache_data, f)
                
        except Exception as e:
            logger.error(f"Error saving to cache: {e}") 