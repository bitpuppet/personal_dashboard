from ..mosque_base import MosqueBase
from dashboard.core.cache_helper import CacheHelper
from typing import Dict, Optional
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import logging

class SachseIslamicCenterMosque(MosqueBase):
    def __init__(self, config: Dict):
        super().__init__(config)
        cache_dir = config.get('cache_dir')
        self.cache_helper = CacheHelper(cache_dir, "friday_prayer")
    
    def get_name(self) -> str:
        return self.config.get('name', 'Sachse Islamic Center')
    
    def get_friday_times(self, force_fetch: bool = False) -> Optional[Dict]:
        try:
            url = self.config.get('url')
            if not url:
                return None
            
            # Fetch the webpage with optional force fetch
            content = self._fetch_page_content(url, force_fetch)
            if not content:
                return None
            
            # Parse HTML
            soup = BeautifulSoup(content, 'html.parser')
            
            # Find the Friday prayer table using the class
            table = soup.find('table', class_='prayer_table')
            if not table:
                self.logger.error("Could not find Friday prayer table")
                return None
            
            # Extract data from the table
            rows = table.find_all('tr')[1:]  # Skip header row
            if not rows:  # Need at least one Jumuah
                self.logger.error("No rows found in Friday prayer table")
                return None
            
            # Get up to 3 Jumuah times
            found_times = {}  # Track found times by number
            
            for row in rows:
                cells = row.find_all('td')
                if len(cells) >= 2:
                    # Get text from first two columns
                    label = cells[0].get_text(strip=True)
                    time = cells[1].get_text(strip=True)
                    
                    # Look for variations of Jumuah labels
                    if "1st" in label:
                        found_times[1] = time
                    elif "2nd" in label:
                        found_times[2] = time
                    elif "3rd" in label:
                        found_times[3] = time
            
            # Format times in order with N/A for missing ones
            formatted_times = []
            for i in range(1, 4):
                time = found_times.get(i, "N/A")
                formatted_times.append(f"{i}{self._get_suffix(i)} Jumuah: {time}")
            
            if found_times:  # If we found at least one time
                return {
                    'khutbah': ", ".join(formatted_times)
                }
            
            self.logger.error("Could not find any Jumuah times in table")
            return None
            
        except Exception as e:
            self.logger.error(f"Error parsing Friday times from {self.get_name()}: {e}")
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