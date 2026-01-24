import tkinter as tk
from dashboard.core.component_base import DashboardComponent
from typing import Dict, Any
import asyncio
from datetime import datetime, timedelta
from .prayer_base import AladhanBackend
from .audio_manager import AdhanManager
from tkinter import ttk  # For download button icon

class PrayerTimesComponent(DashboardComponent):
    name = "Prayer Times"
    
    def __init__(self, app, config: Dict[str, Any]):
        super().__init__(app, config)
        self.backend = self._create_backend()
        self.adhan_manager = AdhanManager(config)
        self.enable_adhan = self.config.get('enable_adhan', True)
        # Initialize playing state attributes
        self.playing_prayer = None
        self.playing_labels = {}
        self.playing_icons = {}
        
        # Schedule daily cache refresh at 10 AM
        self._schedule_daily_cache_refresh()
        
    def _create_backend(self):
        """Create prayer times backend based on configuration"""
        backend_type = self.config.get('backend', 'aladhan')
        if backend_type == 'aladhan':
            return AladhanBackend(self.config)
        else:
            raise ValueError(f"Unknown prayer times backend: {backend_type}")
    
    def initialize(self, parent: tk.Frame) -> None:
        super().initialize(parent)
        
        # Get responsive sizing
        fonts = self.get_responsive_fonts()
        padding = self.get_responsive_padding()
        
        # Create main container
        self.main_container = tk.Frame(self.frame, relief=tk.GROOVE, borderwidth=1)
        self.main_container.pack(padx=padding['small'], pady=padding['small'], fill=tk.BOTH, expand=True)
        
        # Create custom styles for buttons
        style = ttk.Style()
        style.configure(
            "Play.TButton",
            padding=2,
            relief="flat",
            background="#4CAF50",  # Green
            foreground="white",
            font=("Arial", fonts['small'])
        )
        
        # Header section
        header_frame = tk.Frame(self.main_container)
        header_frame.pack(fill=tk.X, padx=padding['medium'], pady=(padding['small'], 0))
        
        # Title
        self.create_label(
            header_frame,
            text=self.headline or "Prayer Times",
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
        
        # City name on right
        right_frame = tk.Frame(header_frame)
        right_frame.pack(side=tk.RIGHT)
        
        self.create_label(
            right_frame,
            text=self.config.get('city', 'Unknown'),
            font_size='small'
        ).pack(side=tk.RIGHT)
        
        # Prayer times table
        table_frame = tk.Frame(self.main_container)
        table_frame.pack(fill=tk.BOTH, expand=True, padx=padding['medium'], pady=padding['small'])
        
        # Headers
        # Adjust column widths based on test buttons visibility
        prayer_width = 20
        time_width = 20
        
        self.create_label(
            table_frame,
            text="Prayer",
            font_size='small',
            bold=True,
            width=prayer_width
        ).grid(row=0, column=0, padx=padding['small'], pady=2)
        self.create_label(
            table_frame,
            text="Time",
            font_size='small',
            bold=True,
            width=time_width
        ).grid(row=0, column=1, padx=padding['small'], pady=2)
        
        # Download status column
        download_col = 2
        tk.Label(table_frame, text="", width=4).grid(
            row=0, 
            column=download_col, 
            padx=padding['small'],
            pady=2
        )
        
        # Prayer time rows
        self.prayer_labels = {}
        self.playing_icons = {}
        
        # Get prayer names from backend
        prayer_names = list(self.backend.PRAYER_NAMES.values())
        
        # Get test schedule configuration
        test_times = self.config.get('test_schedule', {}).get('times', {})
        
        for i, prayer in enumerate(prayer_names, 1):
            # Prayer name with adjusted width
            self.create_label(
                table_frame,
                text=prayer,
                font_size='small',
                width=prayer_width
            ).grid(row=i, column=0, padx=padding['small'], pady=2)
            
            # Time container frame
            time_frame = tk.Frame(table_frame)
            time_frame.grid(row=i, column=1, padx=padding['small'], pady=2)
            
            # Time label
            time_label = self.create_label(
                time_frame,
                text="--:--",
                font_size='small',
                width=time_width
            )
            time_label.pack(side=tk.LEFT)
            self.prayer_labels[prayer] = time_label
            
            # Test button if prayer has test time configured
            if prayer in test_times:
                test_btn = ttk.Button(
                    table_frame,
                    text="Test",
                    width=6,
                    style="TButton",  # Use default style
                    command=lambda p=prayer: self._test_adhan(p)
                )
                test_btn.grid(row=i, column=2, padx=padding['small'], pady=2)
                self._create_tooltip(test_btn, f"Test {prayer} Adhan")
            
            # Playing icon (initially hidden) - make it clickable
            playing_icon = self.create_label(
                time_frame,
                text="⏹",
                font_size='small',
                cursor="hand2"
            )
            playing_icon.pack(side=tk.LEFT, padx=(2, 0))
            playing_icon.pack_forget()
            playing_icon.bind("<Button-1>", lambda e, p=prayer: self._stop_adhan())
            self._create_tooltip(playing_icon, "Click to stop Adhan")
            self.playing_icons[prayer] = playing_icon
        
        # Error label
        self.error_label = self.create_label(
            self.main_container,
            text="",
            font_size='small',
            fg="red",
            wraplength=300
        )
        self.error_label.pack(pady=padding['small'])
        
        # Add countdown label after the prayer times table
        self.countdown_frame = tk.Frame(self.main_container)
        self.countdown_frame.pack(fill=tk.X, padx=padding['medium'], pady=(padding['small'], 0))
        
        self.countdown_label = self.create_label(
            self.countdown_frame,
            text="",
            font_size='small',
            fg="#666666"
        )
        self.countdown_label.pack(side=tk.LEFT)
        
        # Start countdown update
        self._update_countdown()
        
        # Initial update and schedule daily update
        self.fetch_and_schedule_prayers()
        
        # Schedule next day's update at midnight
        self._schedule_next_day_update()
    
    def _schedule_next_day_update(self) -> None:
        """Schedule the next day's prayer times update at midnight"""
        now = datetime.now()
        midnight = (now.replace(hour=0, minute=0, second=0, microsecond=0) + 
                   timedelta(days=1))
        delay = (midnight - now).total_seconds()
        
        self.app.task_manager.schedule_task(
            f"{self.name}_daily_update",
            self.fetch_and_schedule_prayers,
            delay
        )
    
    def fetch_and_schedule_prayers(self, force_fetch: bool = False) -> None:
        """Fetch prayer times and schedule adhans"""
        try:
            self.logger.info("Fetching and scheduling prayer times")
            prayer_times = self.backend.get_prayer_times(force_fetch)
            
            if prayer_times:
                self.logger.debug(f"Received prayer times: {prayer_times}")
                for prayer, time in prayer_times.items():
                    self.schedule_adhan(prayer, time)
                    self.logger.info(f"Scheduled adhan for {prayer} at {time}")
                
                self._latest_result = prayer_times
                self.frame.after(0, self.update)
            else:
                self.logger.error("Failed to fetch prayer times")
                
        except Exception as e:
            self.logger.error(f"Error scheduling prayers: {e}", exc_info=True)
    
    def _schedule_adhans(self, prayer_times: Dict[str, datetime]) -> None:
        """Schedule only the next available prayer adhan"""
        now = datetime.now()
        next_prayer = None
        next_time = None
        
        # Find the next prayer time
        for prayer, time in prayer_times.items():
            if time > now:
                if next_time is None or time < next_time:
                    next_prayer = prayer
                    next_time = time
        
        if next_prayer and next_time:
            # Calculate delay until prayer time
            delay = (next_time - now).total_seconds()
            
            # Cancel any existing scheduled adhans
            if hasattr(self, 'app') and hasattr(self.app, 'task_manager'):
                for name in list(self.app.task_manager.tasks.keys()):
                    if name.startswith(f"{self.name}_") and name.endswith("_adhan"):
                        self.app.task_manager.tasks[name].cancel()
                        del self.app.task_manager.tasks[name]
            
            # Schedule adhan task
            task_name = f"{self.name}_{next_prayer}_adhan"
            self.app.task_manager.schedule_task(
                task_name,
                lambda p=next_prayer: self._schedule_next_after_adhan(p),
                delay,
                one_time=True
            )
            
            self.logger.info(f"Scheduled {next_prayer} adhan for {next_time}")
    
    def _schedule_next_after_adhan(self, prayer: str) -> None:
        """Play adhan and schedule next prayer"""
        # Play current adhan
        if self.enable_adhan and hasattr(self, 'adhan_manager'):
            if self.adhan_manager.play_adhan(prayer):
                self._show_playing_state(prayer)
        
        # Schedule next prayer
        self.fetch_and_schedule_prayers()
    
    def update(self) -> None:
        """Update component display with latest result"""
        if not self._latest_result:
            return
            
        try:
            if isinstance(self._latest_result, dict) and 'error' in self._latest_result:
                self.error_label.config(text=self._latest_result['error'])
                return
            
            # Update prayer times from latest result
            for prayer, time in self._latest_result.items():
                if prayer in self.prayer_labels:
                    time_text = time.strftime("%I:%M %p")
                    self.prayer_labels[prayer].config(text=time_text)
            
            # Check for adhan if enabled
            if self.enable_adhan:
                playing = self.adhan_manager.check_prayer_times(self._latest_result)
                if playing:
                    self._show_playing_state(playing)
                elif not self.adhan_manager.is_playing and self.playing_prayer:
                    self._clear_playing_state()
            
            # Update countdown
            self._update_countdown()
            
            self.error_label.config(text="")
            
        except Exception as e:
            error_msg = f"Error updating prayer times display: {e}"
            self.error_label.config(text=error_msg)
            self.logger.error(error_msg)
    
    def handle_background_result(self, result: Any) -> None:
        """Handle results from background task"""
        self._latest_result = result
        self.update()
    
    def _test_adhan(self, prayer: str) -> None:
        """Test adhan for specific prayer"""
        if hasattr(self, 'adhan_manager'):
            # Stop any currently playing adhan first
            if self.playing_prayer:
                self.adhan_manager.stop_adhan()
                self._clear_playing_state()
            
            # Try to play the new adhan
            if self.adhan_manager.play_adhan(prayer, test_mode=True):
                self._show_playing_state(prayer)
    
    def _stop_adhan(self, event=None) -> None:
        """Stop currently playing adhan"""
        if hasattr(self, 'adhan_manager'):
            self.adhan_manager.stop_adhan()
            self._clear_playing_state()
    
    def _show_playing_state(self, prayer: str) -> None:
        """Show which prayer's adhan is playing"""
        self._clear_playing_state()
        self.playing_prayer = prayer
        
        # Show stop icon next to prayer time
        if prayer in self.playing_icons:
            self.playing_icons[prayer].pack()
    
    def _clear_playing_state(self) -> None:
        """Clear playing state indicators"""
        if self.playing_prayer and self.playing_prayer in self.playing_icons:
            self.playing_icons[self.playing_prayer].pack_forget()
        
        self.playing_prayer = None
    
    def _create_tooltip(self, widget, text):
        """Create a tooltip for a widget"""
        def show_tooltip(event):
            tooltip = tk.Toplevel()
            tooltip.wm_overrideredirect(True)
            tooltip.wm_geometry(f"+{event.x_root+10}+{event.y_root+10}")
            
            label = tk.Label(tooltip, text=text, justify=tk.LEFT,
                           background="#ffffe0", relief=tk.SOLID, borderwidth=1)
            label.pack()
            
            def hide_tooltip():
                tooltip.destroy()
            
            widget.tooltip = tooltip
            widget.bind('<Leave>', lambda e: hide_tooltip())
            tooltip.bind('<Leave>', lambda e: hide_tooltip())
        
        widget.bind('<Enter>', show_tooltip)
    
    def _update_countdown(self) -> None:
        """Update the countdown to next prayer"""
        if not hasattr(self, '_latest_result') or not self._latest_result:
            self.countdown_label.config(text="")
            self.frame.after(60000, self._update_countdown)  # Check again in a minute
            return
            
        now = datetime.now()
        next_prayer = None
        next_time = None
        
        # Find the next prayer time
        for prayer, time in self._latest_result.items():
            if time > now:
                if next_time is None or time < next_time:
                    next_prayer = prayer
                    next_time = time
        
        if next_prayer and next_time:
            # Calculate time difference
            time_diff = next_time - now
            total_seconds = time_diff.total_seconds()
            
            if total_seconds <= 0:
                # Time to refresh prayer times
                self.fetch_and_schedule_prayers()
                self.frame.after(1000, self._update_countdown)  # Update again in a second
                return
            
            hours = int(total_seconds // 3600)
            minutes = int((total_seconds % 3600) // 60)
            
            # Format countdown text
            if hours > 0:
                countdown_text = f"Next adhan: {next_prayer} in {hours} hour{'s' if hours != 1 else ''}"
                if minutes > 0:
                    countdown_text += f" and {minutes} minute{'s' if minutes != 1 else ''}"
            else:
                countdown_text = f"Next adhan: {next_prayer} in {minutes} minute{'s' if minutes != 1 else ''}"
            
            countdown_text += f" ({next_time.strftime('%I:%M %p')})"
            self.countdown_label.config(text=countdown_text)
            
            # Update more frequently when close to prayer time
            if total_seconds < 300:  # Less than 5 minutes
                self.frame.after(1000, self._update_countdown)  # Update every second
            elif total_seconds < 3600:  # Less than 1 hour
                self.frame.after(30000, self._update_countdown)  # Update every 30 seconds
            else:
                self.frame.after(60000, self._update_countdown)  # Update every minute
        else:
            self.countdown_label.config(text="All prayers completed for today")
            # Check again in a minute
            self.frame.after(60000, self._update_countdown)
    
    def _manual_refresh(self) -> None:
        """Handle manual refresh button click"""
        try:
            # Schedule the refresh task
            task_name = f"{self.name}_manual_refresh"
            
            # Cancel any existing refresh task
            if task_name in self.app.task_manager.tasks:
                self.app.task_manager.tasks[task_name].cancel()
            
            # Show refreshing status
            for prayer, label in self.prayer_labels.items():
                label.config(text="Refreshing...")
            
            # Schedule the refresh task
            self.app.task_manager.schedule_task(
                task_name,
                self._do_refresh,
                0,  # Run immediately
                one_time=True
            )
            
            self.logger.info("Manual prayer times refresh started")
            
        except Exception as e:
            self.logger.error(f"Error scheduling prayer times refresh: {e}")
    
    def _do_refresh(self) -> None:
        """Perform the actual refresh in background"""
        try:
            # Clear cache
            self.cached_times = None
            
            # Fetch new times
            times = self.prayer_backend.get_prayer_times(force_fetch=True)
            if times:
                self.cached_times = times
            
            # Update display on main thread
            self.frame.after(0, self.update)
            
            self.logger.info("Manual prayer times refresh completed")
            
        except Exception as e:
            self.logger.error(f"Error in prayer times refresh: {e}")
            # Update display on error
            self.frame.after(0, self.update)
    
    def _schedule_daily_cache_refresh(self) -> None:
        """Schedule daily cache refresh at 10 AM"""
        try:
            now = datetime.now()
            target = now.replace(hour=10, minute=0, second=0, microsecond=0)
            
            # If it's past 10 AM, schedule for tomorrow
            if now >= target:
                target += timedelta(days=1)
            
            delay = int((target - now).total_seconds())
            
            # Schedule the task
            task_name = f"{self.name}_daily_cache_refresh"
            
            # Cancel existing task if any
            if task_name in self.app.task_manager.tasks:
                self.app.task_manager.tasks[task_name].cancel()
            
            # Schedule new task
            self.app.task_manager.schedule_task(
                task_name,
                lambda: self.fetch_and_schedule_prayers(force_fetch=True),
                delay,
                one_time=False  # Make it recurring
            )
            
            self.logger.info(f"Scheduled daily prayer times cache refresh for {target.strftime('%H:%M')}")
            
        except Exception as e:
            self.logger.error(f"Error scheduling daily cache refresh: {e}")

    def schedule_adhan(self, prayer_name: str, prayer_time: datetime) -> None:
        """Schedule adhan for a prayer time"""
        try:
            now = datetime.now()
            if prayer_time <= now:
                self.logger.debug(f"Prayer time {prayer_name} has already passed: {prayer_time}")
                return
            
            delay = int((prayer_time - now).total_seconds())
            task_name = f"{self.name}_{prayer_name}_adhan"
            
            # Cancel any existing adhan task for this prayer
            if task_name in self.app.task_manager.tasks:
                self.app.task_manager.tasks[task_name].cancel()
            
            # Schedule new adhan task
            self.logger.info(f"Scheduling adhan for {prayer_name} in {delay} seconds")
            self.app.task_manager.schedule_task(
                task_name,
                lambda p=prayer_name: self.play_adhan(p),
                delay,
                one_time=True
            )
            
        except Exception as e:
            self.logger.error(f"Error scheduling adhan for {prayer_name}: {e}", exc_info=True)

    def play_adhan(self, prayer_name: str) -> None:
        """Play adhan for a specific prayer"""
        try:
            if not self.enable_adhan:
                self.logger.info(f"Adhan is disabled, skipping {prayer_name}")
                return
                
            self.logger.info(f"Playing adhan for {prayer_name}")
            
            # Get prayer-specific URL if configured, otherwise use default
            prayer_config = self.config.get('adhan', {}).get('prayer_specific', {}).get(prayer_name, {})
            adhan_url = prayer_config.get('url') or self.config['adhan']['default_url']
            
            # Set prayer-specific volume if configured, otherwise use default
            volume = prayer_config.get('volume', self.config['adhan'].get('volume', 1.0))
            
            # Play the adhan
            self.adhan_manager.play_adhan(adhan_url, volume)
            
            # Update UI to show which prayer is playing
            self.playing_prayer = prayer_name
            if prayer_name in self.playing_labels:
                self.playing_labels[prayer_name].config(text="🔊")
            
        except Exception as e:
            self.logger.error(f"Error playing adhan for {prayer_name}: {e}", exc_info=True) 