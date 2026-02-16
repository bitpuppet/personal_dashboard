import tkinter as tk
import tkinter.messagebox as messagebox
from typing import Dict, Any, List, Optional
import logging
import sys
from pathlib import Path
from .task_manager import TaskManager
from .component_base import DashboardComponent
from .volume_control import VolumeControl
from .plugin_manager import PluginManager
from .config import Config
from .layout_manager import LayoutManager
from .context import DashboardContext
from .hot_reload import HotReloadManager

class DashboardApp:
    def __init__(self, config_path: Optional[str] = None):
        # Initialize main window first
        self.root = tk.Tk()
        
        # Initialize logger
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Initialize configuration with root window
        self.config = Config(root=self.root, config_path=config_path)
        self.config.register_change_callback(self.handle_config_change)
        
        # Setup logging
        self._setup_logging()
        
        # Configure window
        self._configure_window()
        
        # Apply background color
        self._apply_background_color()
        
        # Create main container for components
        self.main_container = tk.Frame(self.root)
        self.main_container.pack(fill=tk.BOTH, expand=True)
        
        # Apply background color to main container
        bg_color = self.config.data.get("window", {}).get("background_color")
        if bg_color:
            self.main_container.configure(bg=bg_color)

        # Initialize database (before managers so tables exist)
        from .db import init_db
        init_db(self.config.data)

        # Initialize managers and core services
        self.plugin_manager = PluginManager()
        self.task_manager = TaskManager()
        self.volume_control = VolumeControl(self.config.data)
        
        # Get screen dimensions for responsive layout
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
        # Get background color for layout manager
        bg_color = self.config.data.get("window", {}).get("background_color")
        
        # Initialize layout manager with responsive sizing
        self.layout_manager = LayoutManager(
            self.root,  # Pass root for screen dimension access
            container=self.main_container,  # Pass container for component placement
            columns=self.config.data["layout"].get("columns", 2),
            padding=self.config.data["layout"].get("padding", 10),
            bg_color=bg_color  # Pass background color
        )
        
        # Create taskbar
        from .taskbar import TaskBar
        self.taskbar = TaskBar(self.root, self)
        self.taskbar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Load components
        self.components = []
        self.initialize_components()

        # Sync component registry to DB (config remains source of truth; DB holds current state)
        from .models import sync_components_from_config
        sync_components_from_config(self.config.data)

        # Start API server if enabled (api.enabled in config)
        try:
            from dashboard.api import run_api_server
            run_api_server(self)
        except Exception as e:
            self.logger.warning(f"API server not started: {e}")

        # Setup hot reload (watches config and code files)
        self.hot_reload_manager = HotReloadManager(
            app=self,
            config_dir=self.config.config_dir,
            code_dirs=[Path(__file__).parent.parent],  # Watch dashboard directory
            enabled=True
        )

    def _setup_logging(self):
        """Configure logging to write to both file and stdout"""
        root_logger = logging.getLogger()
        root_logger.handlers.pop()
        root_logger.setLevel(getattr(logging, self.config.data["logging"]["level"]))
        
        # Create formatter with line numbers
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
        )
        
        # File handler
        file_handler = logging.FileHandler(self.config.data["logging"]["file"])
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
        
        # Log startup message
        logging.info("Dashboard application starting...")

    def _on_window_resize(self, event=None) -> None:
        """Handle window resize events to update responsive layout"""
        # Only handle main window resize, not child widget resizes
        if event and event.widget != self.root:
            return
        
        try:
            # Update layout manager responsive sizes
            if hasattr(self, 'layout_manager'):
                self.layout_manager._update_responsive_sizes()
                # Optionally rearrange components on significant size changes
                # For now, we'll just update sizes without rearranging
        except Exception as e:
            self.logger.debug(f"Error handling window resize: {e}")
    
    def _configure_window(self) -> None:
        """Configure window size and appearance"""
        window_config = self.config.data["window"]
        
        # Set window title
        self.root.title("Personal Dashboard")
        
        # Remove window decorations if borderless is True
        if window_config["borderless"]:
            self.root.overrideredirect(True)
        
        # Configure window size
        if window_config["auto_size"]:
            # Get screen dimensions
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()
            
            # Calculate margins
            margin = int(min(screen_width, screen_height) * window_config["margin_percent"] / 100)
            width = screen_width - (2 * margin)
            height = screen_height - (2 * margin)
            
            # Center the window
            x = margin
            y = margin
            
            self.root.geometry(f"{width}x{height}+{x}+{y}")
        else:
            # Use configured size
            self.root.geometry(f"{window_config['width']}x{window_config['height']}")
        
        # Set fullscreen if configured
        if window_config["fullscreen"]:
            self.root.attributes('-fullscreen', True)
        
        # Make sure window stays on top if borderless
        if window_config["borderless"]:
            self.root.attributes('-topmost', True)
            
            # Add key binding to exit (useful for borderless mode)
            self.root.bind('<Escape>', lambda e: self.root.quit())
        
        # Bind window resize event to update responsive layout
        self.root.bind('<Configure>', self._on_window_resize)
    
    def _apply_background_color(self) -> None:
        """Apply background color to the root window"""
        bg_color = self.config.data.get("window", {}).get("background_color")
        if bg_color:
            self.root.configure(bg=bg_color)
            # Also set the default background for all widgets
            self.root.option_add('*background', bg_color)
            self.root.option_add('*Background', bg_color)

    def initialize_components(self):
        try:
            self.plugin_manager.discover_plugins()
            
            for component_name in self.plugin_manager.components:
                logging.debug(f"Checking component: {component_name}")
                component_config = self.config.get_component_config(component_name)
                
                # Create component only if it has config
                component = self.plugin_manager.create_component(self, component_name, component_config)
                if component:
                    logging.debug(f"Initializing component: {component_name}")
                    self.layout_manager.add_component(component)
                    self.components.append(component)
                    logging.debug(f"Component {component_name} initialized successfully")
                else:
                    logging.debug(f"Skipping disabled component: {component_name}")
                
        except Exception as e:
            logging.error(f"Error initializing components: {e}")
            messagebox.showerror("Error", f"Failed to initialize components: {e}")
            logging.exception(e)

    def update_components(self):
        try:
            # Check for background task results
            while not self.task_manager.result_queue.empty():
                task_name, result = self.task_manager.result_queue.get_nowait()
                logging.debug(f"Processing task result for {task_name}: {result}")
                for component in self.components:
                    if component.name == task_name:
                        logging.debug(f"Sending result to component {component.name}")
                        component.handle_background_result(result)
            
            # Update components
            for component in self.components:
                component.update()
                update_interval = component.config.get("update_interval", self.config.data["update_interval"])
                self.logger.info(f"Scheduling next update for {component.name} in {update_interval} milliseconds")
                self.root.after(update_interval, component.update)    
            
            # self.root.after(
            #     self.config.data["update_interval"],
            #     self.update_components
            # )
            
        except Exception as e:
            logging.error(f"Error updating components: {e}")
            logging.exception(e)

    def handle_config_change(self, new_config: Dict[str, Any]) -> None:
        """Handle configuration changes"""
        self.logger.info("Handling config change")
        try:
            # Update internal config
            self.config.data.update(new_config)
            
            # Update layout if needed
            if (self.config.data["layout"]["columns"] != new_config["layout"]["columns"] or
                self.config.data["layout"]["padding"] != new_config["layout"]["padding"]):
                self.layout_manager.update_layout(
                    columns=new_config["layout"]["columns"],
                    padding=new_config["layout"]["padding"]
                )
            
            # Update components
            for component in self.components:
                if component.name in new_config.get('components', {}):
                    component_config = new_config['components'][component.name]
                    component.config.update(component_config)
                    component._handle_config_update()
            
        except Exception as e:
            self.logger.error(f"Error handling config change: {e}", exc_info=True)

    def update_config(self, new_config: Dict[str, Any]) -> None:
        """Update application configuration"""
        try:
            self.logger.info("Updating application configuration")
            old_config = self.config.copy()
            self.config.update(new_config)
            
            # Store original menubar reference
            original_menubar = self.root.nametowidget('.')['menu']
            
            # Update window settings if changed
            if old_config.get('window') != new_config.get('window'):
                self._configure_window()
                self._apply_background_color()
                # Update main container background
                bg_color = new_config.get('window', {}).get('background_color')
                if bg_color:
                    self.main_container.configure(bg=bg_color)
                # Update layout manager background
                if hasattr(self, 'layout_manager'):
                    self.layout_manager.bg_color = bg_color
                    self.layout_manager._setup_grid()  # Recreate frames with new color
            
            # Restore menubar
            self.root['menu'] = original_menubar
            
            # Update components with new config
            self._update_components_config(new_config.get('components', {}))
            
            self.logger.info("Configuration update completed successfully")
            
        except Exception as e:
            self.logger.error(f"Error updating configuration: {e}", exc_info=True)
            # Rollback config if update fails
            self.config = old_config
            
    def _update_components_config(self, new_component_configs: Dict[str, Any]) -> None:
        """Update component configurations"""
        try:
            # Store current component states
            current_components = self.components.copy()
            
            for name, config in new_component_configs.items():
                if name in self.components:
                    component = self.components[name]
                    # Update component config
                    component.config.update(config)
                    # Trigger component's config update handler
                    if hasattr(component, '_handle_config_update'):
                        component._handle_config_update()
                else:
                    # New component - create it
                    if config.get('enable', True):
                        self.plugin_manager.create_component(self, name, config)
            
            # Remove disabled components
            for name in list(self.components.keys()):
                if name in new_component_configs:
                    if not new_component_configs[name].get('enable', True):
                        self.components[name].destroy()
                        del self.components[name]
            
            # Refresh layout
            self._arrange_components()
            
        except Exception as e:
            self.logger.error(f"Error updating components: {e}", exc_info=True)
            # Rollback to previous components if update fails
            self.components = current_components

    def _drain_result_queue(self) -> None:
        """Drain background task results and notify components (called from main thread)."""
        try:
            while not self.task_manager.result_queue.empty():
                task_name, result = self.task_manager.result_queue.get_nowait()
                logging.debug(f"Processing task result for {task_name}: {result}")
                for component in self.components:
                    if component.name == task_name:
                        logging.debug(f"Sending result to component {component.name}")
                        component.handle_background_result(result)
                        break
        except Exception as e:
            logging.error(f"Error draining result queue: {e}")
        self.root.after(1000, self._drain_result_queue)

    def run(self):
        try:
            with DashboardContext.app_context(self):
                self.update_components()
                self.root.after(1000, self._drain_result_queue)
                self.root.mainloop()
        finally:
            self.task_manager.stop()
            if hasattr(self, 'hot_reload_manager'):
                self.hot_reload_manager.stop()
            self.config.cleanup() 