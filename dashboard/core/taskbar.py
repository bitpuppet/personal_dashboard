import tkinter as tk
from tkinter import ttk

class TaskBar(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        
        # Set background color to match app
        self.bg_color = parent.cget('bg')
        
        # Configure taskbar appearance
        self.configure(
            height=30,
            bg=self.bg_color
        )
        
        # Add separator line at the top
        separator = ttk.Separator(self, orient='horizontal')
        separator.pack(side=tk.TOP, fill=tk.X)
        
        # Create left section for system controls
        self.left_frame = tk.Frame(self, bg=self.bg_color)
        self.left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5)
        
        # Create right section for controls
        self.right_frame = tk.Frame(self, bg=self.bg_color)
        self.right_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=5)
        
        # Add volume control to right frame if enabled in config
        if self.app.config.data.get('taskbar', {}).get('show_volume_control', False):
            volume_frame = app.volume_control.create_ui(self.right_frame)
            volume_frame.pack(side=tk.RIGHT, padx=5, pady=2) 