from ..mosque_base import MosqueBase
from dashboard.core.cache_helper import CacheHelper
from typing import Dict, Optional
from bs4 import BeautifulSoup
import logging

class EastPlanoMosque(MosqueBase):
    def __init__(self, config: Dict):
        super().__init__(config)
        cache_dir = config.get('cache_dir')  # Get from mosque config
        self.cache_helper = CacheHelper(cache_dir, "friday_prayer")
    
    def get_name(self) -> str:
        return self.config.get('name', 'East Plano Islamic Center')
    
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
            
            # Find the Friday prayer table
            main_content = soup.select_one('main article')
            if not main_content:
                self.logger.error("Could not find main content")
                return None
                
            tables = main_content.find_all('table')
            if len(tables) < 2:
                self.logger.error("Could not find Friday prayer table")
                return None
                
            friday_table = tables[1]
            
            # Extract data from the table
            rows = friday_table.find_all('tr')
            if len(rows) < 2:  # Need at least header and one Jumuah
                self.logger.error("No rows found in Friday prayer table")
                return None
            
            # Get up to 3 Jumuah times
            jumuah_times = []
            found_times = {}  # Track found times by number
            
            for row in rows[1:]:  # Skip header row
                cells = row.find_all('td')
                if len(cells) >= 2:
                    jumuah_text = cells[0].get_text(strip=True)
                    time = cells[1].get_text(strip=True)
                    
                    # Check for Jumuah text and extract number
                    if "Jumuah" in jumuah_text or "Jumu'ah" in jumuah_text:
                        if "1st" in jumuah_text:
                            found_times[1] = time
                        elif "2nd" in jumuah_text:
                            found_times[2] = time
                        elif "3rd" in jumuah_text:
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
