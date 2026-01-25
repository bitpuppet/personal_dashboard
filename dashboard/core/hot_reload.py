"""
Hot reload manager for the dashboard application.
Watches for changes in config files and Python code, then restarts the application.
"""
import os
import sys
import logging
import time
import subprocess
from pathlib import Path
from typing import Optional
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileModifiedEvent, FileCreatedEvent

logger = logging.getLogger(__name__)


class HotReloadHandler(FileSystemEventHandler):
    """Handler for file system events that trigger hot reload"""
    
    def __init__(self, app, config_dir: Path, code_dirs: list[Path], cooldown: float = 1.0):
        self.app = app
        self.config_dir = config_dir
        self.code_dirs = code_dirs
        self.cooldown = cooldown
        self.last_reload = 0
        self.pending_reload = False
        
    def _should_reload(self, file_path: Path) -> bool:
        """Check if a file change should trigger a reload"""
        current_time = time.time()
        
        # Cooldown check
        if current_time - self.last_reload < self.cooldown:
            logger.debug(f"Skipping reload due to cooldown: {file_path}")
            return False
        
        # Resolve the file path to absolute
        try:
            file_path = file_path.resolve()
        except Exception:
            pass
        
        # Check if it's a config file (check if file is in config directory)
        try:
            config_dir_resolved = self.config_dir.resolve()
            # Python 3.9+ compatibility
            if hasattr(file_path, 'is_relative_to'):
                is_in_config_dir = file_path.is_relative_to(config_dir_resolved)
            else:
                # Python < 3.9 compatibility
                try:
                    file_path.relative_to(config_dir_resolved)
                    is_in_config_dir = True
                except ValueError:
                    is_in_config_dir = False
            
            if is_in_config_dir:
                # Watch for .yaml, .yml, and .env files
                if file_path.suffix in ['.yaml', '.yml'] or file_path.name.startswith('.env'):
                    logger.info(f"Config file change detected: {file_path}")
                    return True
        except Exception as e:
            logger.debug(f"Error checking config dir: {e}")
        
        # Check if it's a Python code file
        for code_dir in self.code_dirs:
            try:
                code_dir_resolved = code_dir.resolve()
                # Python 3.9+ compatibility
                if hasattr(file_path, 'is_relative_to'):
                    is_relative = file_path.is_relative_to(code_dir_resolved)
                else:
                    # Python < 3.9 compatibility
                    try:
                        file_path.relative_to(code_dir_resolved)
                        is_relative = True
                    except ValueError:
                        is_relative = False
                
                if is_relative:
                    if file_path.suffix == '.py':
                        # Ignore __pycache__ and .pyc files
                        file_str = str(file_path)
                        if '__pycache__' not in file_str and not file_path.name.endswith('.pyc'):
                            logger.info(f"Python code file change detected: {file_path}")
                            return True
            except Exception as e:
                logger.debug(f"Error checking code dir {code_dir}: {e}")
        
        return False
    
    def on_modified(self, event):
        """Handle file modification events"""
        if not isinstance(event, FileModifiedEvent):
            return
        
        # Skip directories
        if event.is_directory:
            return
        
        file_path = Path(event.src_path)
        
        logger.debug(f"File modified event: {file_path}")
        
        if self._should_reload(file_path):
            self.last_reload = time.time()
            logger.info(f"File change detected: {file_path} - triggering hot reload")
            self._schedule_reload()
    
    def on_created(self, event):
        """Handle file creation events"""
        if not isinstance(event, FileCreatedEvent):
            return
        
        # Skip directories
        if event.is_directory:
            return
        
        file_path = Path(event.src_path)
        
        logger.debug(f"File created event: {file_path}")
        
        if self._should_reload(file_path):
            self.last_reload = time.time()
            logger.info(f"File creation detected: {file_path} - triggering hot reload")
            self._schedule_reload()
    
    def _schedule_reload(self):
        """Schedule a reload (debounced)"""
        if self.pending_reload:
            return
        
        self.pending_reload = True
        
        # Schedule reload on the main thread after a short delay
        if hasattr(self.app, 'root') and self.app.root:
            self.app.root.after(500, self._perform_reload)  # 500ms delay for file writes to complete
        else:
            # If no root, reload immediately
            self._perform_reload()
    
    def _perform_reload(self):
        """Perform the actual reload by restarting the application"""
        try:
            self.pending_reload = False
            logger.info("Performing hot reload - restarting application...")
            
            # Get config path from app
            config_path = None
            if hasattr(self.app, 'config') and hasattr(self.app.config, 'config_file'):
                config_path = str(self.app.config.config_file)
                logger.info(f"Config path: {config_path}")
            
            # Always use module execution (-m dashboard.main) for more reliable imports
            # This ensures Python path is set correctly
            cmd = [sys.executable, "-m", "dashboard.main"]
            
            if config_path:
                cmd.extend(['--config', config_path])
            
            logger.info(f"Built restart command: {' '.join(cmd)}")
            
            # Close the current application gracefully
            if hasattr(self.app, 'root') and self.app.root:
                # Stop watchers first
                if hasattr(self.app, 'hot_reload_manager'):
                    self.app.hot_reload_manager.stop()
                if hasattr(self.app, 'config') and hasattr(self.app.config, 'observer'):
                    try:
                        self.app.config.observer.stop()
                        self.app.config.observer.join(timeout=1.0)
                    except:
                        pass
                
                # Schedule the restart - execute it immediately in a way that doesn't block
                def restart():
                    try:
                        logger.info(f"Executing restart callback with command: {' '.join(cmd)}")
                        # Start the new process
                        self._restart_process(cmd)
                    except Exception as e:
                        logger.error(f"Error in restart callback: {e}", exc_info=True)
                
                logger.info("Scheduling restart...")
                # Schedule restart to happen immediately, then quit
                self.app.root.after(0, restart)
                # Give it a moment to start the new process, then quit
                self.app.root.after(100, lambda: self.app.root.quit() if hasattr(self.app, 'root') and self.app.root.winfo_exists() else None)
            else:
                self._restart_process(cmd)
                
        except Exception as e:
            logger.error(f"Error during hot reload: {e}", exc_info=True)
            self.pending_reload = False
    
    def _restart_process(self, cmd):
        """Restart the process using subprocess"""
        try:
            logger.info(f"Restarting with command: {' '.join(cmd)}")
            logger.info(f"Current working directory: {os.getcwd()}")
            
            # On Unix-like systems, try os.execv first for a clean process replacement
            # This is more reliable than subprocess for restarting
            if sys.platform != 'win32':
                try:
                    # os.execv replaces the current process, so this is the last line
                    logger.info("Using os.execv for clean process replacement...")
                    
                    # Ensure we're in the project root directory (parent of dashboard/)
                    # This is needed for module execution to work correctly
                    project_root = Path.cwd()
                    # If we're in dashboard/, go up one level
                    if (project_root / "dashboard").exists():
                        pass  # Already in project root
                    elif (project_root.parent / "dashboard").exists():
                        project_root = project_root.parent
                        os.chdir(project_root)
                        logger.info(f"Changed working directory to: {project_root}")
                    
                    # Set PYTHONPATH to ensure module imports work
                    pythonpath = os.environ.get('PYTHONPATH', '')
                    if str(project_root) not in pythonpath.split(os.pathsep):
                        os.environ['PYTHONPATH'] = os.pathsep.join([str(project_root), pythonpath]) if pythonpath else str(project_root)
                        logger.info(f"Set PYTHONPATH to: {os.environ['PYTHONPATH']}")
                    
                    # os.execv replaces the current process
                    os.execv(sys.executable, cmd)
                    # This line should never be reached
                except Exception as e:
                    logger.warning(f"os.execv failed ({e}), falling back to subprocess")
                    import traceback
                    logger.debug(traceback.format_exc())
            
            # Fallback to subprocess (or use on Windows)
            # Ensure we're in the project root for module execution
            project_root = Path.cwd()
            if (project_root / "dashboard").exists():
                cwd = project_root
            elif (project_root.parent / "dashboard").exists():
                cwd = project_root.parent
            else:
                cwd = os.getcwd()
            
            logger.info(f"Starting subprocess from directory: {cwd}")
            
            if sys.platform == 'win32':
                # On Windows, use subprocess with CREATE_NEW_PROCESS_GROUP
                process = subprocess.Popen(
                    cmd,
                    cwd=cwd,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if hasattr(subprocess, 'CREATE_NEW_PROCESS_GROUP') else 0
                )
            else:
                # On Unix-like systems, use subprocess as fallback
                # Don't redirect stdout/stderr so we can see any errors
                env = os.environ.copy()
                if str(cwd) not in env.get('PYTHONPATH', '').split(os.pathsep):
                    pythonpath = env.get('PYTHONPATH', '')
                    env['PYTHONPATH'] = os.pathsep.join([str(cwd), pythonpath]) if pythonpath else str(cwd)
                
                process = subprocess.Popen(
                    cmd,
                    cwd=cwd,
                    env=env,
                    start_new_session=True
                )
            
            logger.info(f"New process started with PID: {process.pid}")
            
            # Give the new process a moment to start, then exit
            import time
            time.sleep(0.5)
            logger.info("Exiting current process...")
            sys.exit(0)
        except Exception as e:
            logger.error(f"Error restarting process: {e}", exc_info=True)
            import traceback
            logger.error(traceback.format_exc())


class HotReloadManager:
    """Manages hot reload functionality for the dashboard"""
    
    def __init__(self, app, config_dir: Path, code_dirs: Optional[list[Path]] = None, enabled: bool = True):
        self.app = app
        self.config_dir = config_dir
        self.enabled = enabled
        self.observer: Optional[Observer] = None
        
        # Determine code directories to watch
        if code_dirs is None:
            # Default: watch the dashboard directory
            dashboard_dir = Path(__file__).parent.parent
            self.code_dirs = [dashboard_dir]
        else:
            self.code_dirs = code_dirs
        
        if self.enabled:
            self._setup_watcher()
    
    def _setup_watcher(self):
        """Setup file system watcher"""
        try:
            self.observer = Observer()
            handler = HotReloadHandler(
                self.app,
                self.config_dir,
                self.code_dirs,
                cooldown=1.0  # 1 second cooldown between reloads
            )
            
            # Watch config directory
            if self.config_dir.exists():
                logger.info(f"Watching config directory for changes: {self.config_dir}")
                self.observer.schedule(handler, str(self.config_dir), recursive=True)
            else:
                logger.warning(f"Config directory does not exist: {self.config_dir}")
            
            # Watch code directories
            for code_dir in self.code_dirs:
                if code_dir.exists():
                    logger.info(f"Watching code directory for changes: {code_dir}")
                    self.observer.schedule(handler, str(code_dir), recursive=True)
                else:
                    logger.warning(f"Code directory does not exist: {code_dir}")
            
            self.observer.start()
            logger.info("Hot reload watcher started successfully")
            logger.info(f"Watching for changes in: config={self.config_dir}, code={self.code_dirs}")
            
        except Exception as e:
            logger.error(f"Error setting up hot reload watcher: {e}", exc_info=True)
            self.enabled = False
    
    def stop(self):
        """Stop the hot reload watcher"""
        if self.observer:
            try:
                self.observer.stop()
                self.observer.join(timeout=2.0)
                logger.info("Hot reload watcher stopped")
            except Exception as e:
                logger.error(f"Error stopping hot reload watcher: {e}")
