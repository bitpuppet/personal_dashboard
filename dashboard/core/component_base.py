from abc import ABC, abstractmethod
import tkinter as tk
from typing import Optional, Dict, Any
import logging

# Base window dimensions for responsive scaling
BASE_WINDOW_WIDTH = 800
BASE_WINDOW_HEIGHT = 600

class DashboardComponent(ABC):
    def __init__(self, app, config: Dict[str, Any]):
        self.frame: Optional[tk.Frame] = None
        self.config = config
        self.app = app
        self.logger = logging.getLogger(self.name)
        self._latest_result = None
    
    def _get_window_dimensions(self) -> tuple:
        """Get current window dimensions (not screen size)"""
        if hasattr(self.app, 'root') and self.app.root.winfo_exists():
            # Get actual window size
            self.app.root.update_idletasks()  # Ensure window is rendered
            width = self.app.root.winfo_width()
            height = self.app.root.winfo_height()
            # If window hasn't been rendered yet, use geometry or screen size as fallback
            if width <= 1 or height <= 1:
                # Try to get from geometry string
                geometry = self.app.root.geometry()
                if geometry and 'x' in geometry:
                    try:
                        size_part = geometry.split('+')[0]
                        width, height = map(int, size_part.split('x'))
                    except (ValueError, IndexError):
                        # Fallback to screen size if geometry parsing fails
                        width = self.app.root.winfo_screenwidth()
                        height = self.app.root.winfo_screenheight()
                else:
                    # Fallback to screen size
                    width = self.app.root.winfo_screenwidth()
                    height = self.app.root.winfo_screenheight()
            return width, height
        return BASE_WINDOW_WIDTH, BASE_WINDOW_HEIGHT  # Default fallback
    
    def get_responsive_fonts(self) -> dict:
        """Get responsive font sizes for this component based on window size, with config overrides"""
        window_width, window_height = self._get_window_dimensions()
        
        # Calculate scale factor based on window size
        # Use average of width and height scaling for better responsiveness
        width_scale = window_width / BASE_WINDOW_WIDTH
        height_scale = window_height / BASE_WINDOW_HEIGHT
        # Use average for more balanced scaling, but ensure minimum readability
        scale = (width_scale + height_scale) / 2
        
        # Clamp scale to reasonable bounds (0.5x to 2x)
        scale = max(0.5, min(2.0, scale))
        
        # Base font sizes (defaults)
        base_fonts = {
            'title': max(10, int(16 * scale)),
            'heading': max(9, int(14 * scale)),
            'body': max(8, int(12 * scale)),
            'small': max(7, int(10 * scale)),
            'tiny': max(6, int(8 * scale)),
        }
        
        # Override with config if provided
        config_fonts = self.config.get('fonts', {})
        if config_fonts:
            for key in base_fonts:
                if key in config_fonts:
                    # If config provides a number, scale it
                    config_value = config_fonts[key]
                    if isinstance(config_value, (int, float)):
                        base_fonts[key] = max(6, int(config_value * scale))
                    elif isinstance(config_value, str) and config_value.endswith('px'):
                        # Support "16px" format
                        base_fonts[key] = max(6, int(float(config_value[:-2]) * scale))
        
        return base_fonts
    
    def get_font_colors(self) -> dict:
        """Get font colors for this component from config, with defaults"""
        # Default colors (white text for dark background)
        default_colors = {
            'text': '#ffffff',
            'heading': '#ffffff',
            'title': '#ffffff',
            'body': '#ffffff',
            'small': '#ffffff',
            'tiny': '#ffffff',
        }
        
        # Override with config if provided
        config_colors = self.config.get('colors', {})
        if config_colors:
            default_colors.update(config_colors)
        
        return default_colors
    
    def get_responsive_padding(self) -> dict:
        """Get responsive padding values for this component based on window size"""
        window_width, window_height = self._get_window_dimensions()
        # Calculate scale based on window size
        width_scale = window_width / BASE_WINDOW_WIDTH
        height_scale = window_height / BASE_WINDOW_HEIGHT
        scale = (width_scale + height_scale) / 2
        # Clamp scale
        scale = max(0.5, min(2.0, scale))
        return {
            'small': max(3, int(5 * scale)),
            'medium': max(5, int(10 * scale)),
            'large': max(8, int(15 * scale)),
            'xlarge': max(10, int(20 * scale)),
        }
    
    def scale_font(self, base_size: int) -> int:
        """Scale a font size based on window dimensions"""
        window_width, window_height = self._get_window_dimensions()
        
        # Calculate scale factor (average of width and height scaling)
        width_scale = window_width / BASE_WINDOW_WIDTH
        height_scale = window_height / BASE_WINDOW_HEIGHT
        scale = (width_scale + height_scale) / 2
        
        # Clamp scale to reasonable bounds (0.5x to 2x)
        scale = max(0.5, min(2.0, scale))
        
        scaled = int(base_size * scale)
        return max(6, scaled)  # Minimum readable size
    
    def scale_padding(self, base_padding: int) -> int:
        """Scale padding based on window dimensions"""
        window_width, window_height = self._get_window_dimensions()
        width_scale = window_width / BASE_WINDOW_WIDTH
        height_scale = window_height / BASE_WINDOW_HEIGHT
        scale = (width_scale + height_scale) / 2
        scale = max(0.5, min(2.0, scale))
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
    
    def create_label(self, parent, text="", font_size=None, bold=False, color=None, **kwargs) -> tk.Label:
        """Create a label with responsive font sizing and configurable colors"""
        fonts = self.get_responsive_fonts()
        colors = self.get_font_colors()
        
        # Determine font size
        font_size_key = None
        if font_size is None:
            font_size = fonts['body']
            font_size_key = 'body'
        elif isinstance(font_size, str):
            # Allow using named font sizes
            font_size_key = font_size
            font_size = fonts.get(font_size, fonts['body'])
        else:
            # Scale the provided font size
            font_size = self.scale_font(font_size)
            font_size_key = None
        
        # Determine font family
        font_family = kwargs.pop('font_family', self.config.get('font_family', 'Arial'))
        font_tuple = (font_family, font_size, "bold") if bold else (font_family, font_size)
        
        # Determine text color
        if color is None:
            # Use color based on font_size_key if it's a named size
            if font_size_key and font_size_key in colors:
                color = colors[font_size_key]
            elif bold:
                color = colors.get('heading', colors['text'])
            else:
                color = colors.get('text', '#ffffff')
        
        # Set foreground color if not already specified
        if 'fg' not in kwargs and 'foreground' not in kwargs:
            kwargs['fg'] = color
        
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