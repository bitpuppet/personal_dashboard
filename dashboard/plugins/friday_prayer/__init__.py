from .friday_prayer_component import FridayPrayerComponent

def register_components(plugin_manager):
    """Register prayer components"""
    plugin_manager.register_component(FridayPrayerComponent) 