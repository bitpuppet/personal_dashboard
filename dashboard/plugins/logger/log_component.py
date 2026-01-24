import tkinter as tk
from tkinter import ttk
import logging
import queue
from dashboard.core.component_base import DashboardComponent
from typing import Dict, Any

class QueueHandler(logging.Handler):
    """Handler that puts logs into a queue for the UI"""
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue
        self.setFormatter(
            logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
            )
        )

    def emit(self, record):
        self.log_queue.put(self.format(record))

class LogComponent(DashboardComponent):
    name = "System Logs"
    
    def __init__(self, app, config: Dict[str, Any]):
        super().__init__(app, config)
        self.log_queue = queue.Queue()
        self.queue_handler = QueueHandler(self.log_queue)
        
        # Initialize level tracking
        self.level_var = tk.StringVar()
        self.current_level = config.get("level", "INFO")
        self.level_var.set(self.current_level)
        
        # Set the handler level
        self.queue_handler.setLevel(getattr(logging, self.current_level))
        
        # Add handler to root logger
        logging.getLogger().addHandler(self.queue_handler)
    
    def initialize(self, parent: tk.Frame) -> None:
        # Get responsive sizing
        fonts = self.get_responsive_fonts()
        padding = self.get_responsive_padding()
        
        # Create a frame that spans the full width
        self.frame = tk.Frame(parent)
        self.frame.pack(side=tk.BOTTOM, fill=tk.X, expand=True, padx=padding['medium'], pady=padding['medium'])
        
        # Add a title
        title = self.create_label(
            self.frame,
            text="System Logs",
            font_size='heading',
            bold=True
        )
        title.pack(pady=(padding['medium'], padding['small']))
        
        # Create log display area
        self.log_frame = tk.Frame(self.frame)
        self.log_frame.pack(fill=tk.BOTH, expand=True, padx=padding['medium'], pady=padding['small'])
        
        # Add text widget with scrollbar
        self.log_text = tk.Text(
            self.log_frame,
            height=8,
            wrap=tk.WORD,
            font=("Courier", fonts['tiny']),
            background="#f0f0f0"
        )
        scrollbar = ttk.Scrollbar(self.log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        
        # Pack widgets
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Configure tags for different log levels
        self.log_text.tag_configure("ERROR", foreground="red")
        self.log_text.tag_configure("WARNING", foreground="orange")
        self.log_text.tag_configure("INFO", foreground="black")
        self.log_text.tag_configure("DEBUG", foreground="gray")
        
        # Make text widget read-only
        self.log_text.configure(state='disabled')
        
        # Add clear button
        self.clear_button = tk.Button(
            self.frame,
            text="Clear Logs",
            command=self.clear_logs
        )
        self.clear_button.pack(pady=(0, padding['medium']))
    
    def update(self) -> None:
        """Process any new log messages in the queue"""
        while True:
            try:
                message = self.log_queue.get_nowait()
                
                # Determine the log level for coloring
                tag = "INFO"  # default
                for level in ["ERROR", "WARNING", "INFO", "DEBUG"]:
                    if level in message:
                        tag = level
                        break
                
                # Enable editing, add text, then disable again
                self.log_text.configure(state='normal')
                self.log_text.insert(tk.END, message + "\n", tag)
                self.log_text.configure(state='disabled')
                
                # Auto-scroll to bottom
                self.log_text.see(tk.END)
                
            except queue.Empty:
                break
    
    def clear_logs(self):
        """Clear the log display"""
        self.log_text.configure(state='normal')
        self.log_text.delete(1.0, tk.END)
        self.log_text.configure(state='disabled')
    
    def destroy(self) -> None:
        """Clean up resources"""
        logging.getLogger().removeHandler(self.queue_handler)
        super().destroy()

    def update_from_config(self) -> None:
        """Update component based on new configuration"""
        try:
            # Update log level if changed
            new_level = self.config.get('level', 'INFO')
            if new_level != self.current_level:
                self.current_level = new_level
                self.level_var.set(new_level)
                # Update handler level
                self.queue_handler.setLevel(getattr(logging, new_level))
            
            # Update other config-dependent values without recreating widgets
            if hasattr(self, 'headline_label'):
                self.headline_label.config(text=self.headline)
            
        except Exception as e:
            self.logger.error(f"Error updating from config: {e}", exc_info=True) 