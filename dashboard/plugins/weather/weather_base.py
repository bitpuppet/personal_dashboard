import requests
import tkinter as tk
from dashboard.core.component_base import DashboardComponent
from typing import Dict, Any, Optional
from .icon_manager import IconManager
from .weather_backend import WeatherBackend, OpenWeatherMapBackend, NWSWeatherBackend

class WeatherBase(DashboardComponent):
    def __init__(self, app, config: Dict[str, Any]):
        super().__init__(app, config)
        self.points_data: Optional[Dict] = None
        self.icon_manager = IconManager()
        self.backend = self._create_backend()
        self.cached_data = None
        self.logger.debug(f"{self.name} initialized with config: {config}")
    
    def _create_backend(self) -> WeatherBackend:
        """Create weather backend based on configuration"""
        try:
            backend_type = self.config.get('backend', 'nws')  # Default to NWS
            if backend_type == 'nws':
                return NWSWeatherBackend(self.config)
            elif backend_type == 'openweathermap':
                return OpenWeatherMapBackend(self.config)
            else:
                self.logger.error(f"Unknown backend type: {backend_type}")
                return None
        except Exception as e:
            self.logger.error(f"Error creating weather backend: {e}")
            return None
    
    def validate_coordinates(self) -> bool:
        """Validate and set coordinates"""
        self.lat = self.config.get("lat")
        self.lon = self.config.get("lon")
        self.city = self.config.get("city", "Unknown Location")
        
        if self.lat is None or self.lon is None:
            self.show_error("Latitude and longitude must be configured")
            return False
            
        try:
            self.lat = float(self.lat)
            self.lon = float(self.lon)
        except ValueError:
            self.show_error("Invalid latitude or longitude values")
            return False
            
        if not (-90 <= self.lat <= 90) or not (-180 <= self.lon <= 180):
            self.show_error("Latitude must be between -90 and 90, longitude between -180 and 180")
            return False
            
        return True
    
    def fetch_points_data(self) -> Optional[Dict]:
        """Fetch grid points data from NWS API"""
        try:
            headers = {
                'User-Agent': '(Personal Dashboard, your@email.com)',
                'Accept': 'application/geo+json'
            }
            url = f"https://api.weather.gov/points/{self.lat},{self.lon}"
            
            self.logger.debug(f"Fetching points data from: {url}")
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            
            data = response.json()
            self.logger.debug(f"Points data: {data}")
            return data
            
        except Exception as e:
            self.logger.error(f"Error fetching points data: {e}")
            return None
    
    def show_error(self, message: str) -> None:
        """Display error message in the UI"""
        if hasattr(self, 'error_label'):
            self.error_label.config(text=message) 
    
    def _handle_config_update(self) -> None:
        """Handle configuration updates"""
        if self.validate_coordinates():
            self.points_data = self.fetch_points_data()
            if self.points_data:
                self._latest_result = self.fetch_weather()
                self.update() 
    
    def destroy(self) -> None:
        """Clean up resources"""
        try:
            if hasattr(self, 'icon_manager'):
                self.icon_manager.clear_cache()
            super().destroy()
        except Exception as e:
            self.logger.error(f"Error destroying {self.name}: {e}") 