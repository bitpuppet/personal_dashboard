from .log_component import LogComponent

def register_components(plugin_manager):
    plugin_manager.register_component(LogComponent) 