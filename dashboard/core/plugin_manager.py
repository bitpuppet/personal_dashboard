import importlib
import pkgutil
from typing import Dict, Type, Any, Optional
import logging
from .component_base import DashboardComponent

class PluginManager:
    def __init__(self):
        self.components: Dict[str, Type[DashboardComponent]] = {}
        self.logger = logging.getLogger(__name__)
        self.discover_plugins()
        
    def discover_plugins(self, plugin_package: str = "dashboard.plugins") -> None:
        """Discover and register all plugins in the specified package"""
        package = importlib.import_module(plugin_package)
        self.logger.info(f"Discovering plugins in package: {plugin_package}")
        
        for _, name, is_pkg in pkgutil.iter_modules(package.__path__):
            if is_pkg:
                try:
                    self.logger.info(f"Importing module: {f"{plugin_package}.{name}"}")
                    module = importlib.import_module(f"{plugin_package}.{name}")
                    self.logger.debug(f"Found plugin module: {name}")
                    if hasattr(module, "register_components"):
                        module.register_components(self)
                        self.logger.info(f"Registered components from plugin: {name}")
                except Exception as e:
                    self.logger.error(f"Error loading plugin {name}: {e}")
                    self.logger.exception(e)
    
    def register_component(self, component_class: Type[DashboardComponent]) -> None:
        """Register a new component class"""
        self.logger.debug(f"Registering component: {component_class.name}")
        self.components[component_class.name] = component_class
    
    def create_component(self, app, name: str, config: Dict[str, Any]) -> Optional[DashboardComponent]:
        """Create an instance of a registered component if it's enabled in config"""
        if name not in self.components:
            self.logger.warning(f"Component '{name}' not found")
            return None
        
        # Only create component if it has config and is enabled
        if not config or not config.get("enable", False):
            self.logger.info(f"Component '{name}' disabled (enable: {config.get('enable', False) if config else False})")
            return None
            
        self.logger.debug(f"Creating component {name} with config: {config}")
        component = self.components[name](app, config)
        return component 