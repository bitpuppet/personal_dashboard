from ..mosque_base import MosqueBase
from dashboard.core.cache_helper import CacheHelper
from typing import Dict, Optional
import re
from bs4 import BeautifulSoup
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
            
            # Fetch the webpage with optional force fetch (re-download)
            content = self._fetch_page_content(url, force_fetch)
            if not content:
                return None
            
            # Parse HTML
            soup = BeautifulSoup(content, 'html.parser')
            
            found_times = {}
            
            # Strategy 1: Find table with class prayer_table
            table = soup.find('table', class_='prayer_table')
            if table:
                found_times = self._parse_table_rows(table)
            
            # Strategy 2: MadinaApps-style - main article, second table (like East Plano)
            if not found_times:
                main_content = soup.select_one('main article')
                if main_content:
                    tables = main_content.find_all('table')
                    if len(tables) >= 2:
                        found_times = self._parse_table_rows(tables[1])
            
            # Strategy 3: Any table containing Jumuah text
            if not found_times:
                for table in soup.find_all('table'):
                    found_times = self._parse_table_rows(table)
                    if found_times:
                        break
            
            # Strategy 4: Regex on full page text (e.g. "1st Jumuah - 01:15", "2nd Jumuah - 02:15")
            if not found_times:
                page_text = soup.get_text(separator=' ', strip=True)
                # Match: 1st Jumuah - 01:15 or 2nd Jumu'ah - 02:15 etc.
                pattern = r'(1st|2nd|3rd)\s+Jumu[\']?ah\s*[-–]\s*(\d{1,2}:\d{2})'
                for match in re.finditer(pattern, page_text, re.IGNORECASE):
                    ordinal, time_str = match.groups()
                    num = {'1st': 1, '2nd': 2, '3rd': 3}.get(ordinal, 0)
                    if num:
                        found_times[num] = time_str
            
            if found_times:
                formatted_times = []
                for i in range(1, 4):
                    time_val = found_times.get(i, "N/A")
                    formatted_times.append(f"{i}{self._get_suffix(i)} Jumuah: {time_val}" + " PM" if time_val != "N/A" else "")
                return {'khutbah': ", ".join(formatted_times)}
            
            self.logger.warning("Could not find any Jumuah times on Sachse page")
            return None
            
        except Exception as e:
            self.logger.error(f"Error parsing Friday times from {self.get_name()}: {e}", exc_info=True)
            return None
    
    def _parse_table_rows(self, table) -> Dict[int, str]:
        """Extract Jumuah times from a table. Returns dict like {1: '1:15 PM', 2: '2:15 PM'}."""
        found_times = {}
        rows = table.find_all('tr')[1:]  # Skip header row
        for row in rows:
            cells = row.find_all('td')
            if len(cells) >= 2:
                label = cells[0].get_text(strip=True)
                time_val = cells[1].get_text(strip=True)
                if "1st" in label or ("1" in label and "Jumuah" in label):
                    found_times[1] = time_val
                elif "2nd" in label or ("2" in label and "Jumuah" in label):
                    found_times[2] = time_val
                elif "3rd" in label or ("3" in label and "Jumuah" in label):
                    found_times[3] = time_val
        return found_times
 