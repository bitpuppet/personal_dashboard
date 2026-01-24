from .weather_component import WeatherComponent
from .hourly_component import HourlyWeatherComponent
from .weekly_component import WeeklyWeatherComponent

def register_components(plugin_manager):
    plugin_manager.register_component(WeatherComponent)
    plugin_manager.register_component(HourlyWeatherComponent)
    plugin_manager.register_component(WeeklyWeatherComponent) 