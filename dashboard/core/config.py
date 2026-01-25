import yaml
from pathlib import Path
import os
from typing import Any, Dict, Optional, List, Callable
import logging
import sys
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileModifiedEvent
import time
import tkinter as tk
import re

class ConfigChangeHandler(FileSystemEventHandler):
    def __init__(self, config):
        self.config = config
        self.last_modified = 0
        self.cooldown = 1.0  # Cooldown period in seconds
        
    def on_modified(self, event):
        if not isinstance(event, FileModifiedEvent):
            return
            
        current_time = time.time()
        if current_time - self.last_modified < self.cooldown:
            return
            
        if event.src_path == str(self.config.config_file):
            try:
                self.last_modified = current_time
                self.config.reload()
            except Exception as e:
                logging.error(f"Error handling config change: {e}")

class Config:
    def __init__(self, root: Optional[tk.Tk] = None, config_path: Optional[str] = None):
        logging.debug("Initializing Config class")
        
        self.root = root
        self.change_callbacks: List[Callable] = []
        self._loading = False  # Lock to prevent recursive reloading
        
        if config_path:
            self.config_file = Path(config_path).resolve()
            self.config_dir = self.config_file.parent
        else:
            self.config_dir = Path(__file__).parent.parent
            self.config_file = self.config_dir / "config.yaml"
            
        logging.debug(f"Using config directory: {self.config_dir}")
        logging.debug(f"Using config file: {self.config_file}")
        
        self.component_configs: Dict[str, Dict[str, Any]] = {}
        
        # Load environment variables from .env file
        self._load_env_file()
        
        self._ensure_config_exists()
        self._load_config()
        
        # Setup file watching
        self.observer = Observer()
        handler = ConfigChangeHandler(self)
        logging.info(f"Path monitored for reloading: {self.config_dir}")
        self.observer.schedule(handler, str(self.config_dir), recursive=False)
        self.observer.start()
    
    def register_change_callback(self, callback: Callable) -> None:
        """Register a callback to be called when config changes"""
        self.change_callbacks.append(callback)
    
    def reload(self) -> None:
        """Reload config and notify listeners"""
        if self._loading:
            return
            
        self._loading = True
        try:
            logging.info("Config file change detected - reloading configuration")
            
            # Wait briefly for file to be fully written
            time.sleep(0.1)
            
            old_config = self.data.copy() if hasattr(self, 'data') else {}
            self._load_config()
            
            # Log changes
            self._log_config_changes(old_config, self.data)
            
            # Notify listeners in a safe manner
            for callback in self.change_callbacks:
                try:
                    if self.root:
                        self.root.after_idle(lambda cb=callback: cb(self.data))
                    else:
                        callback(self.data)
                except Exception as e:
                    logging.error(f"Error in config change callback: {e}")
                    
        except Exception as e:
            logging.error(f"Error reloading config: {e}")
            logging.exception(e)
        finally:
            self._loading = False
    
    def _log_config_changes(self, old_config: Dict, new_config: Dict) -> None:
        """Log the differences between old and new configs"""
        def compare_dict(path: str, dict1: Dict, dict2: Dict) -> None:
            all_keys = set(dict1.keys()) | set(dict2.keys())
            for key in all_keys:
                current_path = f"{path}.{key}" if path else key
                
                # Key exists in both configs
                if key in dict1 and key in dict2:
                    if isinstance(dict1[key], dict) and isinstance(dict2[key], dict):
                        compare_dict(current_path, dict1[key], dict2[key])
                    elif dict1[key] != dict2[key]:
                        logging.info(f"Config changed: {current_path}: {dict1[key]} -> {dict2[key]}")
                
                # Key only in old config
                elif key in dict1:
                    logging.info(f"Config removed: {current_path}: {dict1[key]}")
                
                # Key only in new config
                else:
                    logging.info(f"Config added: {current_path}: {dict2[key]}")
        
        logging.info("=== Configuration Changes Detected ===")
        compare_dict("", old_config, new_config)
        logging.info("=== End of Configuration Changes ===")
    
    def cleanup(self) -> None:
        """Stop the file observer"""
        self.observer.stop()
        self.observer.join()
    
    def _ensure_config_exists(self) -> None:
        """Create default config if it doesn't exist"""
        if not self.config_dir.exists():
            logging.info(f"Creating config directory: {self.config_dir}")
            self.config_dir.mkdir(parents=True)
            
        if not self.config_file.exists():
            logging.info(f"Creating default config file: {self.config_file}")
            default_config = {
                "window": {
                    "fullscreen": False,
                    "borderless": False,  # Remove window decorations
                    "width": 800,
                    "height": 600,
                    "auto_size": True,  # Use screen size if True
                    "margin_percent": 5,  # Screen margin when auto_size is True
                },
                "layout": {
                    "columns": 2,
                    "padding": 10
                },
                "components": {
                    "System Logs": {
                        "enable": True,
                        "level": "INFO"
                    }
                },
                "update_interval": 1000,  # milliseconds
                "logging": {
                    "level": "INFO",
                    "file": str(self.config_dir / "dashboard.log")
                }
            }
            self.config_file.write_text(yaml.dump(default_config))
    
    def _load_env_file(self) -> None:
        """Load environment variables from .env file"""
        # Look for .env file in config directory or project root
        env_files = [
            self.config_dir / ".env",
            self.config_dir.parent / ".env",
            Path.cwd() / ".env"
        ]
        
        env_file = None
        for path in env_files:
            if path.exists():
                env_file = path
                break
        
        if not env_file:
            logging.debug("No .env file found, skipping environment variable loading")
            return
        
        logging.info(f"Loading environment variables from: {env_file}")
        try:
            with open(env_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    # Skip empty lines and comments
                    if not line or line.startswith('#'):
                        continue
                    
                    # Parse KEY=VALUE format
                    match = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$', line)
                    if match:
                        key, value = match.groups()
                        # Remove quotes if present
                        value = value.strip('"').strip("'")
                        # Set environment variable if not already set
                        if key not in os.environ:
                            os.environ[key] = value
                            logging.debug(f"Loaded env var: {key}")
        except Exception as e:
            logging.warning(f"Error loading .env file: {e}")
    
    def _substitute_env_vars(self, data: Any) -> Any:
        """Recursively substitute environment variables in config data"""
        if isinstance(data, dict):
            result = {}
            for key, value in data.items():
                result[key] = self._substitute_env_vars(value)
            return result
        elif isinstance(data, list):
            return [self._substitute_env_vars(item) for item in data]
        elif isinstance(data, str):
            # Check if string is an environment variable reference
            # Format: ${VAR_NAME} or $VAR_NAME
            if data.startswith('${') and data.endswith('}'):
                var_name = data[2:-1]
                return os.environ.get(var_name, data)
            elif data.startswith('$') and len(data) > 1:
                var_name = data[1:]
                return os.environ.get(var_name, data)
            return data
        else:
            return data
    
    def _load_config(self) -> None:
        """Load configuration from file"""
        try:
            logging.debug(f"Loading config from: {self.config_file}")
            with open(self.config_file) as f:
                new_data = yaml.safe_load(f)
                
            if not isinstance(new_data, dict):
                raise ValueError("Invalid config format: root must be a dictionary")
            
            # Substitute environment variables
            new_data = self._substitute_env_vars(new_data)
                
            self.data = new_data
            logging.debug(f"Loaded config data: {self.data}")
            
            # Expand ~ in log file path
            if "logging" in self.data and "file" in self.data["logging"]:
                self.data["logging"]["file"] = os.path.expanduser(self.data["logging"]["file"])
                
        except Exception as e:
            logging.error(f"Error loading config: {e}")
            if hasattr(self, 'data'):
                logging.info("Keeping previous configuration")
            else:
                logging.info("Using default configuration")
                self.data = self._get_default_config()
    
    def get_component_config(self, component_name: str) -> Optional[Dict[str, Any]]:
        """Get config for a specific component"""
        components = self.data.get("components", {})
        return components.get(component_name, None)
    
    def save_component_config(self, component_name: str, config: Dict[str, Any]) -> None:
        """Save configuration for a specific component"""
        if "components" not in self.data:
            self.data["components"] = {}
        self.data["components"][component_name] = config
        
        with open(self.config_file, "w") as f:
            yaml.dump(self.data, f) 