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
from .weather_backend import WeatherBackend, OpenWeatherMapBackend, NWSWeatherBackend

class HourlyWeatherComponent(WeatherBase):
    name = "Hourly Weather"
    
    def __init__(self, app, config: Dict[str, Any]):
        super().__init__(app, config)
        self.hours_to_show = self.config.get("hours_to_show", 7)  # Default to 7 hours if not specified
        self.icon_cache = {}  # Cache for downloaded icons
        self.icon_queue = Queue()
        self._start_icon_thread()
        self.icon_manager = IconManager()
        self.backend = self._create_backend()
        self.cached_data = None
        self.last_fetch = None
        self.should_refresh_screen = True
        
        # Schedule daily cache refresh at 10 AM
        self._schedule_daily_cache_refresh()
        self.logger.debug(f"HourlyWeatherComponent initialized with config: {config}")
    
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
                    img = img.resize((40, 40), Image.Resampling.LANCZOS)  # Slightly smaller than weekly
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
            text=self.headline or "Today's Forecast",
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
        
        # Create scrollable frame for hourly data
        scroll_container = tk.Frame(self.main_container)
        scroll_container.pack(fill="x", expand=True)
        
        # Canvas for scrolling
        self.canvas = tk.Canvas(scroll_container, height=150)
        self.canvas.pack(side=tk.TOP, fill="x", expand=True)
        
        # Scrollbar - packed but initially hidden
        self.scrollbar = tk.Scrollbar(scroll_container, orient="horizontal", command=self.canvas.xview)
        self.scrollbar.pack(side=tk.BOTTOM, fill="x")
        
        # Content frame
        self.scrollable_frame = tk.Frame(self.canvas)
        
        # Configure canvas scrolling
        self.canvas.configure(xscrollcommand=self.scrollbar.set)
        self.canvas_window = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        
        # Bind events for dynamic scrollbar
        self.scrollable_frame.bind("<Configure>", self._on_frame_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        
        # Create hour frames
        self.hour_frames = []
        for _ in range(self.hours_to_show):  # Use configured number of hours
            hour_frame = tk.Frame(self.scrollable_frame)
            hour_frame.pack(side=tk.LEFT, padx=padding['small'], pady=padding['small'])
            
            time_label = self.create_label(
                hour_frame,
                text="--",
                font_size='small',
                bold=True
            )
            time_label.pack()
            
            icon_label = tk.Label(hour_frame)
            icon_label.pack(pady=2)
            
            temp_label = self.create_label(
                hour_frame,
                text="--°F",
                font_size='body'
            )
            temp_label.pack()
            
            desc_label = self.create_label(
                hour_frame,
                text="--",
                font_size='tiny',
                wraplength=100
            )
            desc_label.pack()
            
            self.hour_frames.append({
                'frame': hour_frame,
                'time': time_label,
                'icon': icon_label,
                'temp': temp_label,
                'desc': desc_label
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
        
        # Initialize weather data
        if not self.validate_coordinates():
            return
            
        # Get points data and schedule updates
        self.points_data = self.fetch_points_data()
        if self.points_data:
            self._latest_result = self.fetch_weather()
            self.update()
            
            update_interval = self.config.get("update_interval", 600)
            self.logger.info(f"Hourly Weather update interval: {update_interval}")
            self.app.task_manager.schedule_task(self.name, self.fetch_weather, update_interval)
    
    def _on_frame_configure(self, event=None):
        """Handle scrollable frame size changes"""
        # Update the canvas scrollregion
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        
        # Show/hide scrollbar based on content width
        self._update_scrollbar()
    
    def _on_canvas_configure(self, event=None):
        """Handle canvas size changes"""
        if event:
            # Update the width of the scrollable window to match canvas
            self.canvas.itemconfig(self.canvas_window, width=event.width)
        self._update_scrollbar()
    
    def _update_scrollbar(self):
        """Show or hide scrollbar based on content width"""
        # Get the total width of content and visible width
        content_width = self.scrollable_frame.winfo_reqwidth()
        visible_width = self.canvas.winfo_width()
        
        if content_width > visible_width:
            # Content is wider than visible area - show scrollbar
            self.scrollbar.pack(side=tk.BOTTOM, fill="x")
            self.canvas.configure(yscrollcommand=self.scrollbar.set)
        else:
            # Content fits - hide scrollbar
            self.scrollbar.pack_forget()
            self.canvas.configure(xscrollcommand=None)
    
    def fetch_weather(self, force_fetch=False):
        """Fetch hourly forecast data"""
        if not self.points_data:
            return {"error": "No points data available"}
            
        try:
            headers = {
                'User-Agent': '(Personal Dashboard, your@email.com)',
                'Accept': 'application/geo+json'
            }
            
            hourly_url = self.points_data["properties"]["forecastHourly"]
            self.logger.info(f"Fetching hourly forecast from: {hourly_url}")
            
            if force_fetch or not self.cached_data or datetime.now() - self.last_fetch > timedelta(minutes=5):
                response = requests.get(hourly_url, headers=headers)
                response.raise_for_status()
                
                data = response.json()
                self.logger.debug(f"Hourly forecast data: {data}")
                self.last_fetch = datetime.now()  # Store fetch time separately
                self.cached_data = data  # Store the actual weather data
                self._latest_result = data  # Store the actual weather data
                self.should_refresh_screen = True
                return data
            else:
                self.logger.info("Using cached weather data")
                return self.cached_data
            
        except Exception as e:
            error_msg = f"Error fetching hourly forecast: {str(e)}"
            self.logger.error(error_msg)
            return {"error": error_msg}
    
    def update(self) -> None:
        """Update the display with latest weather data"""
        if not self._latest_result:
            return
            
        if "error" in self._latest_result:
            self.show_error(self._latest_result["error"])
            return
        
        if not self.should_refresh_screen:
            return
            
        try:
            self.logger.info(f"Updating Hourly component results")
            periods = self._latest_result["properties"]["periods"][:self.hours_to_show]  # Use configured number of hours
            
            for i, (period, frame) in enumerate(zip(periods, self.hour_frames)):
                time = datetime.fromisoformat(period["startTime"]).strftime("%I%p")
                temp = int(round(period["temperature"]))  # Round temperature to integer
                desc = period["shortForecast"]
                
                frame['time'].config(text=time)
                frame['temp'].config(text=f"{temp}°F")
                frame['desc'].config(text=desc)
                
                # Update icon based on weather condition
                icon = self.icon_manager.get_icon(desc, size=(40, 40))
                if icon:
                    frame['icon'].config(image=icon)
                    frame['icon'].image = icon  # Keep reference
            
            self.error_label.config(text="")
            
        except Exception as e:
            error_msg = f"Error parsing weather data: {str(e)}"
            self.logger.error(error_msg)
            self.show_error(error_msg)
        finally:
            self.should_refresh_screen = False
    
    def destroy(self) -> None:
        """Clean up resources"""
        self.icon_cache.clear()
        super().destroy()
    
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
    
    def _manual_refresh(self) -> None:
        """Handle manual refresh button click"""
        try:
            task_name = f"{self.name}_manual_refresh"
            
            # Cancel existing task if any
            if task_name in self.app.task_manager.tasks:
                self.app.task_manager.tasks[task_name].cancel()
            
            # Show refreshing status
            for frame in self.hour_frames:
                frame['temp'].config(text="...")
            
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