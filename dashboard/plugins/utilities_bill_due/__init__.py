from .utility_component import UtilitiesBillDueComponent


def register_components(plugin_manager):
    """Register Utilities Bill Due component."""
    plugin_manager.register_component(UtilitiesBillDueComponent)
