from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import logging
import requests
from datetime import datetime
from dashboard.core.cache_helper import CacheHelper


class WeatherBackend(ABC):
    """Base class for weather data providers"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)
        self.cache_helper = CacheHelper(config.get('cache_dir'), "weather")
    
    @abstractmethod
    def get_weather(self, force_fetch: bool = False) -> Optional[Dict]:
        """Get weather data
        Args:
            force_fetch: If True, bypass cache and fetch fresh data
        Returns:
            Weather data dictionary or None on error
        """
        pass

class OpenWeatherMapBackend(WeatherBackend):
    def get_weather(self, force_fetch: bool = False) -> Optional[Dict]:
        """Get current weather and forecast"""
        try:
            cache_key = f"weather_{datetime.now().strftime('%Y-%m-%d_%H')}"
            
            if not force_fetch:
                # Try to get from cache first
                cached_data = self.cache_helper.get_cached_content(cache_key)
                if cached_data:
                    return eval(cached_data)  # Convert string back to dict
            
            # Fetch fresh data from API
            self.logger.info("Fetching weather data from API")
            weather_data = self._fetch_weather_data()
            
            # Cache the results
            if weather_data:
                self.cache_helper.save_to_cache(cache_key, str(weather_data))
            
            return weather_data
            
        except Exception as e:
            self.logger.error(f"Error fetching weather data: {e}")
            return None
    
    def _fetch_weather_data(self) -> Optional[Dict]:
        """Fetch weather data from OpenWeatherMap API"""
        try:
            api_key = self.config.get('api_key')
            lat = self.config.get('lat')
            lon = self.config.get('lon')
            
            url = f"http://api.openweathermap.org/data/3.0/onecall"  # Updated to v3.0 API
            params = {
                'lat': lat,
                'lon': lon,
                'exclude': 'minutely,hourly,alerts',
                'units': 'metric',
                'appid': api_key
            }
            
            self.logger.debug(f"Making API request to {url}")
            response = requests.get(url, params=params)
            
            if response.status_code == 401:
                self.logger.error("Invalid API key or unauthorized access")
                return None
            
            response.raise_for_status()
            
            data = response.json()
            self.logger.info(f"Successfully fetched weather data for coordinates: {lat}°N, {lon}°E")
            
            # Validate response structure
            if 'daily' not in data:
                self.logger.error("Invalid response format - missing daily forecast")
                return None
                
            # Ensure we have 7 days of forecast
            if len(data['daily']) < 7:
                self.logger.error("Incomplete forecast data")
                return None
            
            return data
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Network error fetching weather data: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Error fetching weather data: {e}")
            return None 

class NWSWeatherBackend(WeatherBackend):
    """Weather backend using weather.gov (National Weather Service) API"""
    
    def get_weather(self, force_fetch: bool = False) -> Optional[Dict]:
        """Get current weather and forecast"""
        try:
            cache_key = f"weather_{datetime.now().strftime('%Y-%m-%d_%H')}"
            
            if not force_fetch:
                # Try to get from cache first
                cached_data = self.cache_helper.get_cached_content(cache_key)
                if cached_data:
                    return eval(cached_data)  # Convert string back to dict
            
            # Fetch fresh data from API
            self.logger.info("Fetching weather data from NWS API")
            weather_data = self._fetch_weather_data()
            
            # Cache the results
            if weather_data:
                self.cache_helper.save_to_cache(cache_key, str(weather_data))
            
            return weather_data
            
        except Exception as e:
            self.logger.error(f"Error fetching weather data: {e}")
            return None
    
    def _fetch_weather_data(self) -> Optional[Dict]:
        """Fetch weather data from NWS API"""
        try:
            lat = self.config.get('lat')
            lon = self.config.get('lon')
            
            headers = {
                'User-Agent': '(Personal Weather Dashboard, your@email.com)',
                'Accept': 'application/geo+json'
            }
            
            # First, get the grid points
            points_url = f"https://api.weather.gov/points/{lat},{lon}"
            self.logger.debug(f"Fetching points data from: {points_url}")
            
            points_response = requests.get(points_url, headers=headers)
            points_response.raise_for_status()
            points_data = points_response.json()
            
            # Get both forecast URLs
            forecast_url = points_data['properties']['forecast']
            hourly_url = points_data['properties']['forecastHourly']
            
            self.logger.debug(f"Fetching forecast from: {forecast_url}")
            forecast_response = requests.get(forecast_url, headers=headers)
            forecast_response.raise_for_status()
            forecast_data = forecast_response.json()
            
            self.logger.debug(f"Fetching hourly forecast from: {hourly_url}")
            hourly_response = requests.get(hourly_url, headers=headers)
            hourly_response.raise_for_status()
            hourly_data = hourly_response.json()
            
            # Transform the data to match our expected format
            transformed_data = self._transform_forecast_data(forecast_data, hourly_data)
            
            self.logger.info(f"Successfully fetched weather data for coordinates: {lat}°N, {lon}°E")
            return transformed_data
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Network error fetching weather data: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Error fetching weather data: {e}")
            return None
    
    def _transform_forecast_data(self, forecast_data: Dict, hourly_data: Dict = None) -> Dict:
        """Transform NWS forecast data to match our expected format"""
        try:
            result = {}
            
            # Transform daily forecast
            daily = []
            periods = forecast_data['properties']['periods']
            
            for i in range(0, len(periods)):
                period = periods[i]
                if period.get('isDaytime', True):
                    temp_f = period['temperature']
                    
                    daily_data = {
                        'dt': int(datetime.strptime(period['startTime'], '%Y-%m-%dT%H:%M:%S%z').timestamp()),
                        'temp': temp_f,
                        'weather': [{
                            'description': period['shortForecast'],
                            'icon': period['icon']
                        }]
                    }
                    daily.append(daily_data)
                    
                    if len(daily) >= 7:
                        break
            
            result['daily'] = daily
            
            # Transform hourly forecast if available
            if hourly_data:
                hourly = []
                hourly_periods = hourly_data['properties']['periods']
                
                for period in hourly_periods[:24]:  # Get next 24 hours
                    hourly_data = {
                        'dt': int(datetime.strptime(period['startTime'], '%Y-%m-%dT%H:%M:%S%z').timestamp()),
                        'temp': period['temperature'],
                        'weather': [{
                            'description': period['shortForecast'],
                            'icon': period['icon']
                        }]
                    }
                    hourly.append(hourly_data)
                
                result['hourly'] = hourly
            
            self.logger.debug(f"Transformed data: {result}")
            return result
            
        except Exception as e:
            self.logger.error(f"Error transforming forecast data: {e}", exc_info=True)
            return None
