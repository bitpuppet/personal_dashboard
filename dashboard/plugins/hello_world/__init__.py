from .hello_component import HelloWorldComponent

def register_components(plugin_manager):
    plugin_manager.register_component(HelloWorldComponent) 