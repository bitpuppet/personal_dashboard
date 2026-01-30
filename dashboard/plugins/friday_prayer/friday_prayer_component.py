import tkinter as tk
from tkinter import ttk
from dashboard.core.component_base import DashboardComponent
from typing import Dict, Any, List
from datetime import datetime, timedelta
from .mosque_base import MosqueBase
from .mosque_factory import create_mosque
import time

class FridayPrayerComponent(DashboardComponent):
    name = "Friday Prayer"
    
    def __init__(self, app, config: Dict[str, Any]):
        super().__init__(app, config)
        self.mosques = self._initialize_mosques()
        self.cached_times = {}
        self.should_refresh_screen = True
        
        # Setup daily update if enabled
        daily_update_config = self.config.get('daily_update', {})
        if daily_update_config.get('enabled', True):
            self._schedule_daily_update(daily_update_config.get('time', '10:00'))
    
    def _initialize_mosques(self) -> List[MosqueBase]:
        """Initialize mosque backends from config"""
        mosques = []
        mosque_configs = self.config.get('mosques', [])
        
        # Get cache directory from main config
        cache_dir = self.app.config.data.get('cache', {}).get('directory')
        
        for mosque_config in mosque_configs:
            mosque_type = mosque_config.get('type')
            if mosque_type:
                # Add cache_dir to mosque config
                mosque_config['cache_dir'] = cache_dir
                mosque = create_mosque(mosque_type, mosque_config)
                if mosque:
                    mosques.append(mosque)
                else:
                    self.logger.error(f"Failed to initialize mosque: {mosque_type}")
        
        return mosques
    
    def initialize(self, parent: tk.Frame) -> None:
        super().initialize(parent)
        
        # Get responsive sizing
        fonts = self.get_responsive_fonts()
        padding = self.get_responsive_padding()
        
        # Create main container
        self.main_container = tk.Frame(self.frame, relief=tk.GROOVE, borderwidth=1)
        self.main_container.pack(padx=padding['small'], pady=padding['small'], fill=tk.BOTH, expand=True)
        
        # Header section
        header_frame = tk.Frame(self.main_container)
        header_frame.pack(fill=tk.X, padx=padding['medium'], pady=(padding['small'], 0))
        
        # Title
        self.create_label(
            header_frame,
            text=self.headline or "Friday Prayer Times",
            font_size='heading',
            bold=True
        ).pack(side=tk.LEFT)
        
        # Add refresh button with icon
        refresh_button = self.create_label(
            header_frame,
            text="↻",  # Unicode refresh symbol
            font_size='heading',
            cursor="hand2",
            fg="#666666"  # Slightly darker color for the icon
        )
        refresh_button.pack(side=tk.RIGHT, padx=(0, padding['small']))
        
        # Bind click events
        refresh_button.bind('<Button-1>', lambda e: self._manual_refresh())
        refresh_button.bind('<Enter>', lambda e: refresh_button.configure(fg="#333333"))  # Darker on hover
        refresh_button.bind('<Leave>', lambda e: refresh_button.configure(fg="#666666"))  # Normal color
        
        # Create tooltip for refresh button
        self._create_tooltip(refresh_button, "Refresh prayer times")
        
        # Create table
        self.table_frame = tk.Frame(self.main_container)
        self.table_frame.pack(fill=tk.BOTH, expand=True, padx=padding['medium'], pady=padding['small'])
        
        # Configure column weights for responsive sizing
        # Make mosque name column take more space to show full names
        self.table_frame.columnconfigure(0, weight=3, minsize=150)  # Mosque name - increased for full display
        self.table_frame.columnconfigure(1, weight=1, minsize=60)  # 1st Khutba
        self.table_frame.columnconfigure(2, weight=1, minsize=60)  # 2nd Khutba
        self.table_frame.columnconfigure(3, weight=1, minsize=60)  # 3rd Khutba
        
        # Headers - use shorter text to save space
        headers = ["Mosque", "1st", "2nd", "3rd"]
        for col, header in enumerate(headers):
            self.create_label(
                self.table_frame,
                text=header,
                font_size='small',
                bold=True
            ).grid(row=0, column=col, padx=padding['small'], pady=2, sticky='w')
        
        # Add separator after headers
        separator = ttk.Separator(self.table_frame, orient='horizontal')
        separator.grid(row=1, column=0, columnspan=len(headers), sticky='ew', pady=padding['small'])
        
        # Initialize rows for each mosque
        self.mosque_rows = {}
        self._create_mosque_rows()
        
        # Schedule updates
        self.update()
    
    def _create_mosque_rows(self) -> None:
        """Create rows for each mosque's prayer times"""
        padding = self.get_responsive_padding()
        current_row = 2  # Start after headers and separator
        
        for mosque in self.mosques:
            mosque_name = mosque.get_name()
            
            # Create labels for this mosque's times
            # Remove width constraint from mosque name to allow full display
            mosque_labels = {
                'name': self.create_label(self.table_frame, text=mosque_name, font_size='small'),
                'juma1': self.create_label(self.table_frame, text="--:--", font_size='small', width=8),
                'juma2': self.create_label(self.table_frame, text="--:--", font_size='small', width=8),
                'juma3': self.create_label(self.table_frame, text="--:--", font_size='small', width=8)
            }
            
            # Grid the labels - mosque name can expand, times stay fixed
            mosque_labels['name'].grid(row=current_row, column=0, padx=padding['small'], pady=2, sticky='w')
            mosque_labels['juma1'].grid(row=current_row, column=1, padx=padding['small'], pady=2, sticky='w')
            mosque_labels['juma2'].grid(row=current_row, column=2, padx=padding['small'], pady=2, sticky='w')
            mosque_labels['juma3'].grid(row=current_row, column=3, padx=padding['small'], pady=2, sticky='w')
            
            self.mosque_rows[mosque_name] = mosque_labels
            
            # Add separator after each mosque
            current_row += 1
            separator = ttk.Separator(self.table_frame, orient='horizontal')
            separator.grid(row=current_row, column=0, columnspan=4, sticky='ew', pady=padding['small'])
            current_row += 1
    
    def _schedule_daily_update(self, time_str: str) -> None:
        """Schedule daily update at specified time"""
        try:
            # Parse update time
            hour, minute = map(int, time_str.split(':'))
            now = datetime.now()
            
            # Set target time for today
            target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            
            # If it's past target time, schedule for tomorrow
            if now >= target:
                target += timedelta(days=1)
            
            # Calculate delay in seconds
            delay = int((target - now).total_seconds())
            
            # Schedule the task
            task_name = f"{self.name}_daily_update"
            
            # Cancel existing task if any
            if task_name in self.app.task_manager.tasks:
                self.app.task_manager.tasks[task_name].cancel()
            
            # Schedule new task
            self.app.task_manager.schedule_task(
                task_name,
                self._daily_update,
                delay,
                one_time=False  # Make it recurring
            )
            
            self.logger.info(f"Scheduled daily Friday times update for {target.strftime('%H:%M')}")
            
        except Exception as e:
            self.logger.error(f"Error scheduling daily update: {e}")
    
    def _daily_update(self) -> None:
        """Perform daily update at 10 AM"""
        try:
            # Clear component cache
            self.cached_times.clear()
            
            # Fetch new times with force_fetch
            for mosque in self.mosques:
                mosque_name = mosque.get_name()
                # Pass force_fetch=True to get fresh content
                times = mosque.get_friday_times(force_fetch=True)
                if times:
                    self.cached_times[mosque_name] = times
            
            # Update display
            self.frame.after(0, self.update)  # Schedule update on main thread
            self.should_refresh_screen = True

        except Exception as e:
            self.logger.error(f"Error in daily update: {e}")
    
    def update(self) -> None:
        """Update prayer times display"""
        if not self.should_refresh_screen:
            return
        try:
            for mosque in self.mosques:
                self.logger.info(f"Updating times for {mosque.get_name()}")
                mosque_name = mosque.get_name()
                if mosque_name in self.mosque_rows:
                    # Use cached times if available
                    times = self.cached_times.get(mosque_name)
                    if not times:
                        times = mosque.get_friday_times()
                        if times:
                            self.cached_times[mosque_name] = times
                    
                    labels = self.mosque_rows[mosque_name]
                    if times:
                        time_text = times.get('khutbah', '')
                        juma_times = self._parse_juma_times(time_text)
                        
                        labels['juma1'].config(text=juma_times.get(1, "N/A"))
                        labels['juma2'].config(text=juma_times.get(2, "N/A"))
                        labels['juma3'].config(text=juma_times.get(3, "N/A"))
            
        except Exception as e:
            self.logger.error(f"Error updating Friday prayer times: {e}")
        finally:
            self.should_refresh_screen = False
    
    def _parse_juma_times(self, time_text: str) -> Dict[int, str]:
        """Parse the combined time string into individual times"""
        times = {}
        try:
            for part in time_text.split(", "):
                if "Jumuah" in part:
                    # Extract the number and time
                    if "1st" in part:
                        times[1] = part.split(": ")[1]
                    elif "2nd" in part:
                        times[2] = part.split(": ")[1]
                    elif "3rd" in part:
                        times[3] = part.split(": ")[1]
        except Exception as e:
            self.logger.error(f"Error parsing Jumu'ah times: {e}")
        return times
    
    def _create_tooltip(self, widget, text):
        """Create a tooltip for a widget"""
        def show_tooltip(event):
            tooltip = tk.Toplevel()
            tooltip.wm_overrideredirect(True)
            tooltip.wm_geometry(f"+{event.x_root+10}+{event.y_root+10}")
            
            # Use responsive font size for tooltip
            fonts = self.get_responsive_fonts()
            label = tk.Label(tooltip, text=text, justify=tk.LEFT,
                           background="#ffffe0", relief=tk.SOLID, borderwidth=1,
                           font=("Arial", fonts['small']))
            label.pack()
            
            def hide_tooltip():
                tooltip.destroy()
            
            widget.tooltip = tooltip
            widget.bind('<Leave>', lambda e: hide_tooltip())
            tooltip.bind('<Leave>', lambda e: hide_tooltip())
        
        widget.bind('<Enter>', show_tooltip)
    
    def _manual_refresh(self) -> None:
        """Handle manual refresh button click"""
        try:
            # Schedule the refresh task
            task_name = f"{self.name}_manual_refresh"
            
            # Cancel any existing refresh task
            if task_name in self.app.task_manager.tasks:
                self.app.task_manager.tasks[task_name].cancel()
            
            # Show refreshing status
            for mosque_name, labels in self.mosque_rows.items():
                for key in ['juma1', 'juma2', 'juma3']:
                    labels[key].config(text="Refreshing...")
            
            # Schedule the refresh task
            self.app.task_manager.schedule_task(
                task_name,
                self._do_refresh,
                0,  # Run immediately
                one_time=True
            )
            
            self.logger.info("Manual refresh started")
            
        except Exception as e:
            self.logger.error(f"Error scheduling manual refresh: {e}")
    
    def _do_refresh(self) -> None:
        """Perform the actual refresh in background"""
        try:
            # Clear component cache
            self.cached_times.clear()
            
            # Fetch new times with force_fetch
            for mosque in self.mosques:
                mosque_name = mosque.get_name()
                times = mosque.get_friday_times(force_fetch=True)
                if times:
                    self.cached_times[mosque_name] = times
            
            # Update display on main thread
            self.frame.after(0, self.update)
            
            self.logger.info("Manual refresh completed")
            
        except Exception as e:
            self.logger.error(f"Error in manual refresh: {e}")
            # Update display on error
            self.frame.after(0, self.update) 