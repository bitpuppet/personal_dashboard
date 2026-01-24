from .prayer_component import PrayerTimesComponent

def register_components(plugin_manager):
    """Register prayer components"""
    plugin_manager.register_component(PrayerTimesComponent) 