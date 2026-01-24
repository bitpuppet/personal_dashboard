import tkinter as tk
from tkinter import ttk
import pygame
import json
import os
from typing import Dict
import logging

class VolumeControl:
    def __init__(self, config: Dict):
        pygame.mixer.init()
        self.logger = logging.getLogger("VolumeControl")
        self.config = config
        self.volume = self._load_volume()
        self.popup_visible = False
        
        # Set initial pygame mixer volume
        pygame.mixer.music.set_volume(self.volume)
    
    def create_ui(self, parent: tk.Widget) -> tk.Frame:
        """Create and return the volume control UI component"""
        # Get parent background color
        bg_color = parent.cget('bg')
        self.root = parent.winfo_toplevel()
        
        # Create container frame
        volume_frame = tk.Frame(parent, bg=bg_color)
        
        # Volume icon (clickable)
        self.volume_icon = tk.Label(
            volume_frame,
            text="🔊",
            font=("Arial", 12),
            bg=bg_color,
            cursor="hand2"
        )
        self.volume_icon.pack(side=tk.LEFT, padx=2)
        self.volume_icon.bind('<Button-1>', self._toggle_popup)
        
        # Create popup frame for volume slider
        self.popup = tk.Toplevel(self.root)
        self.popup.withdraw()
        self.popup.overrideredirect(True)
        self.popup.transient(self.root)
        self.popup.configure(bg=bg_color)
        
        # Add border
        self.popup_frame = tk.Frame(
            self.popup,
            bg=bg_color,
            relief='solid',
            borderwidth=1
        )
        self.popup_frame.pack(fill=tk.BOTH, expand=True)
        
        # Create and store the variable for the scale
        self.scale_var = tk.DoubleVar(value=self.volume * 100)
        
        # Vertical volume slider using tk.Scale
        self.scale = tk.Scale(
            self.popup_frame,
            from_=100.0,
            to=0.0,
            orient=tk.VERTICAL,
            variable=self.scale_var,
            command=self._update_volume,
            length=100,
            width=10,
            sliderlength=20,
            resolution=1,
            showvalue=False,
            bg=bg_color,
            highlightthickness=0,
            troughcolor='#d0d0d0',
            activebackground=bg_color
        )
        self.scale.pack(padx=5, pady=5)
        
        # Bind global click event
        self.root.bind('<Button-1>', self._on_click_away)
        
        # Prevent click propagation from slider and popup
        self.scale.bind('<Button-1>', lambda e: self._handle_scale_click(e))
        self.popup.bind('<Button-1>', lambda e: self._handle_popup_click(e))
        self.popup_frame.bind('<Button-1>', lambda e: self._handle_popup_click(e))
        
        return volume_frame
    
    def _handle_scale_click(self, event):
        """Handle clicks on the scale"""
        event.widget.focus_set()
        return "break"  # Prevent event propagation
    
    def _handle_popup_click(self, event):
        """Handle clicks on the popup"""
        return "break"  # Prevent event propagation
    
    def _toggle_popup(self, event=None):
        """Show/hide volume popup"""
        if self.popup_visible:
            self._hide_popup()
        else:
            self._show_popup()
        return "break"  # Prevent event propagation
    
    def _show_popup(self):
        """Show volume popup"""
        if not self.popup_visible:
            # Position popup above volume icon
            x = self.volume_icon.winfo_rootx()
            y = self.volume_icon.winfo_rooty() - self.popup.winfo_reqheight() - 5
            self.popup.geometry(f"+{x}+{y}")
            self.popup.deiconify()
            self.popup.lift()
            self.popup_visible = True
    
    def _hide_popup(self):
        """Hide volume popup"""
        if self.popup_visible:
            self.popup.withdraw()
            self.popup_visible = False
    
    def _on_click_away(self, event):
        """Hide popup when clicking away"""
        if not self.popup_visible:
            return
            
        # Get the widget under the cursor
        clicked = event.widget.winfo_containing(event.x_root, event.y_root)
        
        # Handle volume icon click
        if clicked == self.volume_icon:
            return
            
        # Close if click is outside popup and volume icon
        if clicked not in [self.popup, self.popup_frame, self.scale]:
            self._hide_popup()
    
    def _update_volume(self, value: str):
        """Update volume and icon"""
        try:
            volume = float(value) / 100
            self.volume = volume
            pygame.mixer.music.set_volume(volume)
            self._save_volume()
            
            # Update icon based on volume level
            if volume == 0:
                self.volume_icon.config(text="🔇")
            elif volume < 0.33:
                self.volume_icon.config(text="🔈")
            elif volume < 0.66:
                self.volume_icon.config(text="🔉")
            else:
                self.volume_icon.config(text="🔊")
        except Exception as e:
            self.logger.error(f"Error updating volume: {e}")
    
    def _load_volume(self) -> float:
        """Load saved volume from file"""
        try:
            volumes_file = os.path.expanduser('~/.personal_dashboard/volume.json')
            if os.path.exists(volumes_file):
                with open(volumes_file, 'r') as f:
                    saved = json.load(f)
                    return saved.get('volume', 0.7)
        except Exception as e:
            self.logger.error(f"Error loading saved volume: {e}")
        
        return 0.7
    
    def _save_volume(self) -> None:
        """Save current volume to file"""
        try:
            volumes_file = os.path.expanduser('~/.personal_dashboard/volume.json')
            os.makedirs(os.path.dirname(volumes_file), exist_ok=True)
            with open(volumes_file, 'w') as f:
                json.dump({'volume': self.volume}, f)
        except Exception as e:
            self.logger.error(f"Error saving volume: {e}")
    
    def get_volume(self) -> float:
        """Get current volume"""
        return self.volume
    
    def set_volume(self, volume: float) -> None:
        """Set volume and update UI if it exists"""
        self.volume = max(0.0, min(1.0, volume))
        pygame.mixer.music.set_volume(self.volume)
        self._save_volume()
        if hasattr(self, 'scale_var'):
            self.scale_var.set(self.volume * 100) 