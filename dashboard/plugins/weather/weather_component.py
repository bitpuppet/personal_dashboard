import tkinter as tk
from tkinter import ttk
import requests
import logging
from dashboard.core.component_base import DashboardComponent
from typing import Dict, Any
from datetime import datetime, timedelta
from .icon_manager import IconManager
from .weather_backend import WeatherBackend, OpenWeatherMapBackend

class WeatherComponent(DashboardComponent):
    name = "Weather"
    
    def __init__(self, app, config: Dict[str, Any]):
        super().__init__(app, config)
        self.icon_manager = IconManager()
        self.logger.debug(f"WeatherComponent initialized with config: {config}")
        self.backend = self._create_backend()
        self.cached_data = None
        
        # Schedule daily cache refresh at 10 AM
        self._schedule_daily_cache_refresh()
    
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
                lambda: self.fetch_weather(force_fetch=True),
                delay,
                one_time=False  # Make it recurring
            )
            
            self.logger.info(f"Scheduled daily weather cache refresh for {target.strftime('%H:%M')}")
            
        except Exception as e:
            self.logger.error(f"Error scheduling daily cache refresh: {e}")
    
    def initialize(self, parent: tk.Frame) -> None:
        super().initialize(parent)
        
        # Get responsive sizing
        fonts = self.get_responsive_fonts()
        padding = self.get_responsive_padding()
        
        # Create main container with border and padding
        self.main_container = tk.Frame(self.frame, relief=tk.GROOVE, borderwidth=1)
        self.main_container.pack(padx=padding['small'], pady=padding['small'], fill=tk.BOTH, expand=True)
        
        # Header section
        header_frame = tk.Frame(self.main_container)
        header_frame.pack(fill=tk.X, padx=padding['medium'], pady=(padding['small'], 0))
        
        # Title
        self.create_label(
            header_frame,
            text=self.headline or "Weather",
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
        self._create_tooltip(refresh_button, "Refresh weather data")
        
        # City name on right
        city_frame = tk.Frame(header_frame)
        city_frame.pack(side=tk.RIGHT)
        
        self.create_label(
            city_frame,
            text=self.config.get('city', 'Unknown'),
            font_size='small'
        ).pack(anchor="e")
        
        # Forecast Section - Now in rows
        self.forecast_days = []
        for _ in range(7):  # 7 days forecast
            day_frame = tk.Frame(self.main_container)
            day_frame.pack(fill=tk.X, padx=padding['medium'], pady=2)
            
            # Left: Day name - reduced width and padding
            day_label = self.create_label(
                day_frame,
                text="--",
                font_size='heading',
                bold=True,
                width=10
            )
            day_label.pack(side=tk.LEFT, padx=(padding['small'], 2), pady=padding['small'])
            
            # Center: Weather Icon and Description
            center_frame = tk.Frame(day_frame)
            center_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
            
            # Create a sub-frame for icon and description stacked vertically
            icon_desc_frame = tk.Frame(center_frame)
            icon_desc_frame.pack(expand=True)
            
            icon_label = tk.Label(icon_desc_frame)
            icon_label.pack(pady=(2,0))
            
            desc_label = self.create_label(
                icon_desc_frame,
                text="--",
                font_size='tiny'
            )
            desc_label.pack(pady=(0,2))
            
            # Right: Temperature
            temp_frame = tk.Frame(day_frame)
            temp_frame.pack(side=tk.RIGHT, padx=padding['medium'])
            
            temp_label = self.create_label(
                temp_frame,
                text="--°F",
                font_size='body',
                bold=True,
                width=8
            )
            temp_label.pack()
            
            self.forecast_days.append({
                'frame': day_frame,
                'day': day_label,
                'icon': icon_label,
                'desc': desc_label,
                'temp': temp_label
            })
        
        # Error label
        self.error_label = self.create_label(
            self.main_container,
            text="",
            font_size='small',
            fg="red",
            wraplength=300
        )
        self.error_label.pack(pady=padding['small'])
        
        # Setup weather fetching
        if not isinstance(self.config, dict):
            self.show_error(f"Invalid config type: {type(self.config)}, expected dict")
            return
            
        api_key = self.config.get("api_key", "")
        self.logger.info(f"API Key found: {'Yes' if api_key else 'No'}")
        
        if not api_key:
            self.show_error("No API key configured for weather component")
            return
            
        # Validate coordinates
        self.lat = self.config.get("lat")
        self.lon = self.config.get("lon")
        
        if self.lat is None or self.lon is None:
            self.show_error("Latitude and longitude must be configured")
            return
            
        try:
            self.lat = float(self.lat)
            self.lon = float(self.lon)
        except ValueError:
            self.show_error("Invalid latitude or longitude values")
            return
            
        if not (-90 <= self.lat <= 90) or not (-180 <= self.lon <= 180):
            self.show_error("Latitude must be between -90 and 90, longitude between -180 and 180")
            return
        
        # Schedule initial fetch
        self._latest_result = self.fetch_weather()
        self.update()
        
        # Schedule periodic updates
        update_interval = self.config.get("update_interval", 600)
        self.logger.info(f"Weather Component update interval: {update_interval}")
        self.app.task_manager.schedule_task("Weather", self.fetch_weather, update_interval)
    
    def celsius_to_fahrenheit(self, celsius):
        """Convert Celsius to Fahrenheit"""
        return (celsius * 9/5) + 32
    
    def format_day(self, timestamp):
        """Format timestamp to day name"""
        return datetime.fromtimestamp(timestamp).strftime('%a')
    
    def update(self) -> None:
        """Update the display with latest weather data"""
        if not self._latest_result:
            return
            
        self.logger.debug(f"Updating display with result: {self._latest_result}")
        
        if "error" in self._latest_result:
            self.show_error(self._latest_result["error"])
            return
            
        try:
            # Update forecast
            daily = self._latest_result["daily"]
            for i, day_data in enumerate(daily[:7]):  # First 7 days
                day_frame = self.forecast_days[i]
                temp_f = int(round(self.celsius_to_fahrenheit(day_data["temp"]["day"])))  # Round to nearest integer
                desc = day_data["weather"][0]["description"]
                
                day_frame['day'].config(text=self.format_day(day_data["dt"]))
                day_frame['temp'].config(text=f"{temp_f}°F")  # Removed .1f formatting
                
                # Always show description text
                day_frame['desc'].config(text=desc.capitalize())
                
                # Add icon if available
                icon = self.icon_manager.get_icon(desc, size=(30, 30))
                if icon:
                    day_frame['icon'].config(image=icon)
                    day_frame['icon'].image = icon  # Keep reference
                else:
                    day_frame['icon'].config(image="")  # Clear icon
            
        except Exception as e:
            error_msg = f"Error parsing weather data: {str(e)}"
            self.logger.error(error_msg)
            self.show_error(error_msg)
    
    def show_error(self, message: str) -> None:
        """Display error message in the UI"""
        self.error_label.config(text=message)
        for day_frame in self.forecast_days:
            day_frame['day'].config(text="--")
            day_frame['temp'].config(text="--°F")
            day_frame['icon'].config(image="")
            day_frame['desc'].config(text="--")
    
    def clear_error(self) -> None:
        """Clear error message from the UI"""
        self.error_label.config(text="")
    
    def fetch_weather(self, force_fetch: bool = False) -> None:
        """Fetch weather data from backend"""
        try:
            weather_data = self.backend.get_weather(force_fetch)
            if weather_data:
                self.cached_data = weather_data
                self.frame.after(0, self.update)  # Update UI on main thread
        except Exception as e:
            self.logger.error(f"Error fetching weather: {e}")
    
    def destroy(self) -> None:
        """Clean up resources"""
        try:
            if hasattr(self, 'icon_manager'):
                self.icon_manager.clear_cache()
            super().destroy()
        except Exception as e:
            self.logger.error(f"Error destroying {self.name}: {e}")
    
    def _manual_refresh(self) -> None:
        """Handle manual refresh button click"""
        try:
            # Schedule the refresh task
            task_name = f"{self.name}_manual_refresh"
            
            # Cancel any existing refresh task
            if task_name in self.app.task_manager.tasks:
                self.app.task_manager.tasks[task_name].cancel()
            
            # Show refreshing status
            # Update your weather display widgets to show "Refreshing..."
            
            # Schedule the refresh task
            self.app.task_manager.schedule_task(
                task_name,
                lambda: self.fetch_weather(force_fetch=True),
                0,  # Run immediately
                one_time=True
            )
            
            self.logger.info("Manual weather refresh started")
            
        except Exception as e:
            self.logger.error(f"Error scheduling weather refresh: {e}")
    
    def _create_backend(self) -> WeatherBackend:
        """Create weather backend based on configuration"""
        try:
            # Currently we only support OpenWeatherMap
            return OpenWeatherMapBackend(self.config)
        except Exception as e:
            self.logger.error(f"Error creating weather backend: {e}")
            return None 
    
    def _create_tooltip(self, widget, text):
        """Create a tooltip for a widget"""
        def show_tooltip(event):
            tooltip = tk.Toplevel()
            tooltip.wm_overrideredirect(True)
            tooltip.wm_geometry(f"+{event.x_root+10}+{event.y_root+10}")
            
            label = tk.Label(tooltip, text=text, justify=tk.LEFT,
                           background="#ffffe0", relief=tk.SOLID, borderwidth=1,
                           font=("Arial", 10))
            label.pack()
            
            def hide_tooltip():
                tooltip.destroy()
            
            widget.tooltip = tooltip
            widget.bind('<Leave>', lambda e: hide_tooltip())
            tooltip.bind('<Leave>', lambda e: hide_tooltip())
        
        widget.bind('<Enter>', show_tooltip) 