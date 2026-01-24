from abc import ABC, abstractmethod
import tkinter as tk
from typing import Optional, Dict, Any
import logging

class DashboardComponent(ABC):
    def __init__(self, app, config: Dict[str, Any]):
        self.frame: Optional[tk.Frame] = None
        self.config = config
        self.app = app
        self.logger = logging.getLogger(self.name)
        self._latest_result = None
    
    def _get_screen_dimensions(self) -> tuple:
        """Get screen dimensions"""
        if hasattr(self.app, 'root'):
            return self.app.root.winfo_screenwidth(), self.app.root.winfo_screenheight()
        return 1920, 1080  # Default fallback
    
    def get_responsive_fonts(self) -> dict:
        """Get responsive font sizes for this component"""
        screen_width, screen_height = self._get_screen_dimensions()
        # Simple scaling based on screen size (base: 1920x1080)
        scale = min(screen_width / 1920, screen_height / 1080)
        return {
            'title': max(8, int(16 * scale)),
            'heading': max(8, int(14 * scale)),
            'body': max(8, int(12 * scale)),
            'small': max(8, int(10 * scale)),
            'tiny': max(8, int(8 * scale)),
        }
    
    def get_responsive_padding(self) -> dict:
        """Get responsive padding values for this component"""
        screen_width, screen_height = self._get_screen_dimensions()
        # Simple scaling based on screen size (base: 1920x1080)
        scale = min(screen_width / 1920, screen_height / 1080)
        return {
            'small': max(3, int(5 * scale)),
            'medium': max(5, int(10 * scale)),
            'large': max(8, int(15 * scale)),
            'xlarge': max(10, int(20 * scale)),
        }
    
    def scale_font(self, base_size: int) -> int:
        """Scale a font size based on screen dimensions"""
        screen_width, screen_height = self._get_screen_dimensions()
        scale = min(screen_width / 1920, screen_height / 1080)
        scaled = int(base_size * scale)
        return max(8, scaled)  # Minimum readable size
    
    def scale_padding(self, base_padding: int) -> int:
        """Scale padding based on screen dimensions"""
        screen_width, screen_height = self._get_screen_dimensions()
        scale = min(screen_width / 1920, screen_height / 1080)
        return max(3, int(base_padding * scale))
        
    @property
    @abstractmethod
    def name(self) -> str:
        """Return the name of the component"""
        pass
    
    @property
    def headline(self) -> str:
        """Return the display name for the component"""
        return self.config.get("headline", self.name)
    
    @abstractmethod
    def initialize(self, parent: tk.Frame) -> None:
        """Initialize the component with a parent frame"""
        self.frame = tk.Frame(parent)
        # Use responsive padding by default
        padding = self.get_responsive_padding()['medium']
        self.frame.pack(pady=padding, padx=padding, fill=tk.X)
    
    def create_label(self, parent, text="", font_size=None, bold=False, **kwargs) -> tk.Label:
        """Create a label with responsive font sizing"""
        fonts = self.get_responsive_fonts()
        
        if font_size is None:
            font_size = fonts['body']
        elif isinstance(font_size, str):
            # Allow using named font sizes
            font_size = fonts.get(font_size, fonts['body'])
        else:
            # Scale the provided font size
            font_size = self.scale_font(font_size)
        
        font_family = kwargs.pop('font_family', 'Arial')
        font_tuple = (font_family, font_size, "bold") if bold else (font_family, font_size)
        
        return tk.Label(parent, text=text, font=font_tuple, **kwargs)
    
    def get_padding(self, size='medium') -> int:
        """Get responsive padding value by size name"""
        padding = self.get_responsive_padding()
        return padding.get(size, padding['medium'])
    
    @abstractmethod
    def update(self) -> None:
        """Update component display with latest result"""
        pass
    
    def handle_background_result(self, result: Any) -> None:
        """Store result and trigger update"""
        self._latest_result = result
    
    def destroy(self) -> None:
        """Clean up resources"""
        try:
            if hasattr(self, 'frame') and self.frame:
                if self.frame.winfo_exists():
                    for widget in self.frame.winfo_children():
                        if widget.winfo_exists():
                            widget.destroy()
                    self.frame.destroy()
                self.frame = None
            self.logger.debug(f"Component {self.name} destroyed")
        except Exception as e:
            self.logger.error(f"Error destroying component {self.name}: {e}")
    
    def update_config(self, new_config: Dict[str, Any]) -> None:
        """Update component configuration"""
        self.config = new_config
        self.logger.info(f"Updated config for {self.name}")
        self._handle_config_update()
    
    def _handle_config_update(self) -> None:
        """Handle configuration updates"""
        try:
            self.logger.debug(f"Handling config update for {self.name}")
            
            # Only update config-dependent values without destroying widgets
            if hasattr(self, 'update_from_config'):
                self.update_from_config()
            else:
                self.update()  # Fallback to regular update
                
        except Exception as e:
            self.logger.error(f"Error handling config update for {self.name}: {e}", exc_info=True) 