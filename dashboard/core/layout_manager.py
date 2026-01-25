import tkinter as tk
from typing import List, Dict, Optional, Tuple
from .component_base import DashboardComponent
import logging

class LayoutManager:
    def __init__(self, root: tk.Tk, container: tk.Frame = None, columns: int = 2, padding: int = 10, bg_color: Optional[str] = None):
        self.root = root
        self.container = container if container else root
        self.base_columns = columns
        self.base_padding = padding
        self.bg_color = bg_color
        self.frames: List[tk.Frame] = []
        self.components: Dict[str, DashboardComponent] = {}  # Track components by name
        self.logger = logging.getLogger(self.__class__.__name__)
        self._update_responsive_sizes()
        self._setup_grid()
    
    def _update_responsive_sizes(self) -> None:
        """Update responsive sizes based on current screen dimensions"""
        # Use base columns and padding (can be made responsive later if needed)
        self.columns = self.base_columns
        self.padding = self.base_padding
    
    def _setup_grid(self) -> None:
        """Create grid of frames for components"""
        self.root.update_idletasks()  # Ensure pending UI updates are processed
        
        # Update responsive sizes before setting up grid
        self._update_responsive_sizes()
        
        # Clear existing frames if any
        for frame in self.frames:
            if frame.winfo_exists():
                frame.destroy()
        self.frames = []
        
        # Update container padding if it exists
        if self.container and self.container.winfo_exists():
            self.container.pack_configure(padx=self.padding, pady=self.padding)
        
        # Create columns container
        if hasattr(self, 'columns_container') and self.columns_container.winfo_exists():
            self.columns_container.destroy()
        
        self.columns_container = tk.Frame(self.container, bg=self.bg_color)
        self.columns_container.pack(expand=True, fill=tk.BOTH)
        
        # Create column frames
        for i in range(self.columns):
            frame = tk.Frame(self.columns_container, bg=self.bg_color)
            frame.pack(side=tk.LEFT, expand=True, fill=tk.BOTH, padx=self.padding)
            self.frames.append(frame)
        
        self.root.update_idletasks()
    
    def _get_component_position(self, component: DashboardComponent) -> Tuple[Optional[int], Optional[int]]:
        """Get row and column position from component config"""
        config = component.config
        row = config.get('row')
        column = config.get('column')
        return row, column
    
    def _get_target_frame_index(self, component: DashboardComponent) -> int:
        """Determine which column frame a component should be placed in"""
        row, column = self._get_component_position(component)
        
        # If column is explicitly specified, use it
        if column is not None:
            # Ensure column is within valid range
            return max(0, min(column, self.columns - 1))
        
        # Fallback: find frame with fewest widgets (auto-placement)
        return min(range(len(self.frames)), key=lambda i: len(self.frames[i].winfo_children()))
    
    def add_component(self, component: DashboardComponent) -> None:
        """Add component to layout based on config row/column or auto-placement"""
        try:
            # Update responsive sizes before adding component
            self._update_responsive_sizes()
            
            self.components[component.name] = component
            
            if component.name == "System Logs":
                # Initialize in the main container for full width
                component.initialize(self.container)
                component.frame.pack(
                    fill=tk.BOTH,
                    expand=True,
                    pady=(self.padding, 0),
                    after=self.columns_container
                )
            else:
                # Get target frame based on config or auto-placement
                frame_index = self._get_target_frame_index(component)
                target_frame = self.frames[frame_index]
                
                component.initialize(target_frame)
                
                # Special handling for Friday Prayer Times - make it more compact
                if component.name == "Friday Prayer Times":
                    # Set maximum width to prevent it from taking too much space
                    max_width = component.config.get('max_width', 400)
                    if max_width:
                        component.frame.config(width=max_width)
                        component.frame.pack_propagate(True)
                    # Fill horizontally up to max width, don't expand
                    component.frame.pack(
                        fill=tk.X,  # Fill horizontally up to max width
                        expand=False,  # Don't expand
                        pady=(0, self.padding),
                        anchor='nw'  # Anchor to top-left
                    )
                else:
                    # Regular components
                    component.frame.pack(
                        fill=tk.BOTH,
                        expand=True,
                        pady=(0, self.padding)
                    )
                
            self.root.update_idletasks()
            
        except Exception as e:
            self.logger.error(f"Error adding component {component.name}: {e}", exc_info=True)
    
    def remove_component(self, component_name: str) -> None:
        """Remove a component from layout"""
        try:
            if component_name in self.components:
                component = self.components[component_name]
                if component.frame and component.frame.winfo_exists():
                    component.frame.destroy()
                del self.components[component_name]
                self.root.update_idletasks()
                
        except Exception as e:
            logging.error(f"Error removing component {component_name}: {e}")
            logging.exception(e)
    
    def update_layout(self, columns: int = None, padding: int = None) -> None:
        """Update layout configuration"""
        try:
            # Update base values
            if columns is not None:
                self.base_columns = columns
            if padding is not None:
                self.base_padding = padding
            
            # Recalculate responsive sizes
            self._update_responsive_sizes()
            
            # Rearrange components without destroying them
            self.arrange_components()
            
        except Exception as e:
            self.logger.error(f"Error updating layout: {e}", exc_info=True)

    def _reflow_components(self) -> None:
        """Reflow all components in the layout"""
        # Store current components
        components = []
        for frame in self.frames:
            for widget in frame.winfo_children():
                if isinstance(widget, tk.Frame):
                    components.append(widget)
                    widget.pack_forget()
            frame.destroy()
        
        # Recreate frames
        self.frames = []
        for i in range(self.columns):
            frame = tk.Frame(self.root)
            frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=self.padding)
            self.frames.append(frame)
        
        # Re-add components
        for i, component in enumerate(components):
            frame_index = i % self.columns
            component.pack(in_=self.frames[frame_index], fill=tk.X, pady=self.padding) 

    def arrange_components(self) -> None:
        """Rearrange all components in the grid based on their config positions"""
        try:
            # Store current components (excluding System Logs which is handled separately)
            components = [c for c in self.components.values() if c.name != "System Logs"]
            
            # Temporarily unpack components without destroying
            for component in components:
                if component.frame and component.frame.winfo_exists():
                    component.frame.pack_forget()
            
            # Update frame layout
            self._setup_grid()
            
            # Group components by column, then sort by row within each column
            components_by_column = {}
            components_no_position = []
            
            for component in components:
                row, column = self._get_component_position(component)
                if column is not None:
                    if column not in components_by_column:
                        components_by_column[column] = []
                    components_by_column[column].append((row if row is not None else 999, component))
                else:
                    components_no_position.append(component)
            
            # Sort components within each column by row
            for column in components_by_column:
                components_by_column[column].sort(key=lambda x: x[0])
            
            # Place components with explicit positions first
            for column in sorted(components_by_column.keys()):
                frame_index = max(0, min(column, self.columns - 1))
                for row, component in components_by_column[column]:
                    if component.frame and component.frame.winfo_exists():
                        self._place_component(component, frame_index)
            
            # Place components without explicit positions (auto-placement)
            for component in components_no_position:
                if component.frame and component.frame.winfo_exists():
                    frame_index = self._get_target_frame_index(component)
                    self._place_component(component, frame_index)
            
            self.root.update_idletasks()
            
        except Exception as e:
            self.logger.error(f"Error arranging components: {e}", exc_info=True)
    
    def _place_component(self, component: DashboardComponent, frame_index: int) -> None:
        """Place a component in the specified frame with appropriate settings"""
        if component.name == "Friday Prayer Times":
            # Set maximum width and don't expand
            max_width = component.config.get('max_width', 400)
            if max_width:
                component.frame.config(width=max_width)
                component.frame.pack_propagate(True)
            component.frame.pack(
                in_=self.frames[frame_index],
                fill=tk.X,
                expand=False,
                pady=(0, self.padding),
                anchor='nw'  # Anchor to top-left
            )
        else:
            component.frame.pack(
                in_=self.frames[frame_index],
                fill=tk.BOTH,
                expand=True,
                pady=(0, self.padding)
            )
