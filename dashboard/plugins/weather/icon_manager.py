import tkinter as tk
from PIL import Image, ImageTk
from pathlib import Path
import logging
from typing import Dict, Optional

class IconManager:
    """Manages weather icons and their mapping to weather conditions"""
    
    def __init__(self):
        self.icon_cache: Dict[str, ImageTk.PhotoImage] = {}
        self.icon_dir = Path(__file__).parent / "icons"
        self.logger = logging.getLogger("IconManager")
        
        # Map weather conditions to icon filenames
        self.icon_map = {
            "clear": "clear.png",
            "sunny": "sun.png",
            "mostly clear": "partly-cloudy.png",
            "partly cloudy": "partly-cloudy.png",
            "mostly cloudy": "cloudy.png",
            "cloudy": "cloudy.png",
            "rain": "rain.png",
            "showers": "rain.png",
            "thunderstorm": "storm.png",
            "snow": "snow.png",
            "fog": "fog.png",
            "haze": "haze.png",
            "few clouds": "few-clouds.png",
            "scattered clouds": "few-clouds.png",
            "default": "weather.png"  # Default icon
        }
    
    def get_icon(self, condition: str, size: tuple = (30, 30)) -> Optional[ImageTk.PhotoImage]:
        """Get icon for weather condition"""
        try:
            # Normalize condition text
            condition = condition.lower()
            
            # Find matching icon
            icon_file = None
            for key, filename in self.icon_map.items():
                if key in condition:
                    icon_file = filename
                    break
            
            # Use default if no match found
            if not icon_file:
                icon_file = self.icon_map["default"]
            
            # Create cache key
            cache_key = f"{icon_file}_{size[0]}x{size[1]}"
            
            # Return cached icon if available
            if cache_key in self.icon_cache:
                return self.icon_cache[cache_key]
            
            # Load and resize icon
            icon_path = self.icon_dir / icon_file
            if not icon_path.exists():
                self.logger.error(f"Icon file not found: {icon_path}")
                return None
                
            img = Image.open(icon_path)
            img = img.resize(size, Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            
            # Cache the icon
            self.icon_cache[cache_key] = photo
            return photo
            
        except Exception as e:
            self.logger.error(f"Error loading icon for condition '{condition}': {e}")
            return None
    
    def clear_cache(self) -> None:
        """Clear icon cache"""
        self.icon_cache.clear() 