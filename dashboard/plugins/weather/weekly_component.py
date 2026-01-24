from .weather_base import WeatherBase
import tkinter as tk
from datetime import datetime, timedelta
from typing import Dict, Any, List
import requests
from PIL import Image, ImageTk
from io import BytesIO
import threading
from queue import Queue
from .icon_manager import IconManager
from dashboard.core.component_base import DashboardComponent
from .weather_backend import WeatherBackend, OpenWeatherMapBackend, NWSWeatherBackend

class WeeklyWeatherComponent(DashboardComponent):
    name = "Weekly Weather"
    
    def __init__(self, app, config: Dict[str, Any]):
        super().__init__(app, config)
        self.icon_cache = {}  # Cache for downloaded icons
        self.icon_queue = Queue()
        self._start_icon_thread()
        self.icon_manager = IconManager()
        self.backend = self._create_backend()
        self.cached_data = None
        
        # Schedule daily cache refresh at 10 AM
        self._schedule_daily_cache_refresh()
    
    def _start_icon_thread(self):
        """Start background thread for icon downloads"""
        self.icon_thread = threading.Thread(target=self._process_icon_queue, daemon=True)
        self.icon_thread.start()
    
    def _process_icon_queue(self):
        """Process icon downloads in background"""
        while True:
            try:
                url, label = self.icon_queue.get()
                if url not in self.icon_cache:
                    response = requests.get(url)
                    img = Image.open(BytesIO(response.content))
                    img = img.resize((50, 50), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
                    self.icon_cache[url] = photo
                else:
                    photo = self.icon_cache[url]
                
                # Update label in main thread
                label.after(0, lambda l=label, p=photo: l.configure(image=p))
            except Exception as e:
                self.logger.error(f"Error processing icon: {e}")
            finally:
                self.icon_queue.task_done()
    
    def _create_backend(self) -> WeatherBackend:
        """Create weather backend based on configuration"""
        try:
            backend_type = self.config.get('backend', 'nws')  # Default to NWS
            if backend_type == 'nws':
                return NWSWeatherBackend(self.config)
            elif backend_type == 'openweathermap':
                return OpenWeatherMapBackend(self.config)
            else:
                self.logger.error(f"Unknown backend type: {backend_type}")
                return None
        except Exception as e:
            self.logger.error(f"Error creating weather backend: {e}")
            return None
    
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
            text=self.headline or "7-Day Forecast",
            font_size='heading',
            bold=True
        ).pack(side=tk.LEFT)
        
        # Add refresh button
        refresh_button = self.create_label(
            header_frame,
            text="↻",
            font_size='heading',
            cursor="hand2",
            fg="#666666"
        )
        refresh_button.pack(side=tk.RIGHT, padx=(0, padding['small']))
        
        # Bind click events
        refresh_button.bind('<Button-1>', lambda e: self._manual_refresh())
        refresh_button.bind('<Enter>', lambda e: refresh_button.configure(fg="#333333"))
        refresh_button.bind('<Leave>', lambda e: refresh_button.configure(fg="#666666"))
        
        # Create tooltip
        self._create_tooltip(refresh_button, "Refresh forecast")
        
        # City name
        self.create_label(
            header_frame,
            text=self.config.get('city', 'Unknown'),
            font_size='small'
        ).pack(side=tk.RIGHT, padx=padding['small'])
        
        # Create forecast rows
        self.forecast_days = []
        for _ in range(7):
            day_frame = tk.Frame(self.main_container)
            day_frame.pack(fill=tk.X, padx=padding['medium'], pady=2)
            
            # Day name
            day_label = self.create_label(
                day_frame,
                text="--",
                font_size='small',
                bold=True,
                width=10
            )
            day_label.pack(side=tk.LEFT, padx=padding['small'])
            
            # Weather icon and description
            center_frame = tk.Frame(day_frame)
            center_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
            
            icon_label = tk.Label(center_frame)
            icon_label.pack(side=tk.LEFT, padx=padding['small'])
            
            desc_label = self.create_label(
                center_frame,
                text="--",
                font_size='tiny',
                width=20
            )
            desc_label.pack(side=tk.LEFT)
            
            # Temperature
            temp_label = self.create_label(
                day_frame,
                text="--°F",
                font_size='small',
                width=8
            )
            temp_label.pack(side=tk.RIGHT, padx=padding['small'])
            
            self.forecast_days.append({
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
        
        # Initial fetch
        self.fetch_weather()
        
        # Schedule updates
        update_interval = self.config.get('update_interval', 3600)  # Default 1 hour
        self.app.task_manager.schedule_task(
            f"{self.name}_update",
            self.fetch_weather,
            update_interval
        )
    
    def celsius_to_fahrenheit(self, celsius):
        """Convert Celsius to Fahrenheit"""
        return (celsius * 9/5) + 32
    
    def format_day(self, timestamp):
        """Format timestamp to day name"""
        return datetime.fromtimestamp(timestamp).strftime('%A')
    
    def update(self) -> None:
        """Update the display with latest weather data"""
        self.logger.debug(f"Updating display with cached data: {self.cached_data}")
        
        if not self.cached_data:
            self.logger.warning("No cached data available for update")
            return
        
        try:
            daily = self.cached_data.get('daily', [])
            self.logger.debug(f"Processing {len(daily)} daily forecasts")
            
            for i, day_data in enumerate(daily[:7]):
                self.logger.debug(f"Processing day {i}: {day_data}")
                day_frame = self.forecast_days[i]
                
                # Update day name
                day_frame['day'].config(text=self.format_day(day_data['dt']))
                
                # Update temperature (keep in Fahrenheit for NWS data)
                if 'temp' in day_data:
                    if isinstance(day_data['temp'], dict):
                        temp_f = int(round(self.celsius_to_fahrenheit(day_data['temp']['day'])))
                    else:
                        temp_f = int(round(day_data['temp']))  # Already in Fahrenheit for NWS
                    day_frame['temp'].config(text=f"{temp_f}°F")
                
                # Update description and icon
                if 'weather' in day_data and day_data['weather']:
                    weather = day_data['weather'][0]
                    desc = weather.get('description', '')
                    day_frame['desc'].config(text=desc.capitalize())
                    
                    # Handle icon
                    if 'icon' in weather:
                        icon = self.icon_manager.get_icon(desc, size=(30, 30))
                        if icon:
                            day_frame['icon'].config(image=icon)
                            day_frame['icon'].image = icon
                
            self.error_label.config(text="")
            
        except Exception as e:
            error_msg = f"Error updating display: {e}"
            self.logger.error(error_msg, exc_info=True)
            self.error_label.config(text=error_msg)
    
    def fetch_weather(self, force_fetch: bool = False) -> None:
        """Fetch weather data from backend"""
        try:
            self.logger.info("Fetching weather data...")
            weather_data = self.backend.get_weather(force_fetch)
            
            if weather_data:
                self.logger.info(f"Received weather data: {weather_data}")
                self.cached_data = weather_data
                self._latest_result = weather_data  # Add this line
                self.frame.after(0, self.update)
            else:
                self.logger.error("No weather data received from backend")
                self.error_label.config(text="Unable to fetch weather data")
        except Exception as e:
            self.logger.error(f"Error fetching weather: {e}")
            self.error_label.config(text=f"Error fetching weather: {e}")
    
    def _manual_refresh(self) -> None:
        """Handle manual refresh button click"""
        try:
            task_name = f"{self.name}_manual_refresh"
            
            # Cancel existing task if any
            if task_name in self.app.task_manager.tasks:
                self.app.task_manager.tasks[task_name].cancel()
            
            # Show refreshing status
            for day_frame in self.forecast_days:
                day_frame['temp'].config(text="...")
            
            # Schedule refresh
            self.app.task_manager.schedule_task(
                task_name,
                lambda: self.fetch_weather(force_fetch=True),
                0,
                one_time=True
            )
            
        except Exception as e:
            self.logger.error(f"Error in manual refresh: {e}")
    
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
    
    def _schedule_daily_cache_refresh(self) -> None:
        """Schedule daily cache refresh at 10 AM"""
        try:
            now = datetime.now()
            target = now.replace(hour=10, minute=0, second=0, microsecond=0)
            
            if now >= target:
                target += timedelta(days=1)
            
            delay = int((target - now).total_seconds())
            
            task_name = f"{self.name}_daily_cache_refresh"
            
            if task_name in self.app.task_manager.tasks:
                self.app.task_manager.tasks[task_name].cancel()
            
            self.app.task_manager.schedule_task(
                task_name,
                lambda: self.fetch_weather(force_fetch=True),
                delay,
                one_time=False
            )
            
            self.logger.info(f"Scheduled daily weather cache refresh for {target.strftime('%H:%M')}")
            
        except Exception as e:
            self.logger.error(f"Error scheduling daily cache refresh: {e}")
    
    def destroy(self) -> None:
        """Clean up resources"""
        self.icon_cache.clear()
        super().destroy() 