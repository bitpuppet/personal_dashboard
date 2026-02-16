from .weather_base import WeatherBase
import tkinter as tk
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import requests
from dashboard.core.component_base import _make_json_serializable
from PIL import Image, ImageTk
from io import BytesIO
import threading
from queue import Queue
from .icon_manager import IconManager
from .weather_backend import WeatherBackend, OpenWeatherMapBackend, NWSWeatherBackend
from .service import get_latest_weather
from .task import WeatherTask


class HourlyWeatherComponent(WeatherBase):
    name = "Hourly Weather"

    def __init__(self, app, config: Dict[str, Any]):
        super().__init__(app, config)
        self.hours_to_show = self.config.get("hours_to_show", 7)
        self.icon_cache = {}
        self.icon_queue = Queue()
        self._start_icon_thread()
        self.icon_manager = IconManager()
        self.backend = self._create_backend()
        self.should_refresh_screen = True

        self.task = WeatherTask(self.name, config)
        self.task.ensure_scheduled()
        self.app.task_manager.register_task(self.name, self.task.run)
        self.app.task_manager.schedule_registered_task(
            self.name, config, self.app.config.data
        )
        self.logger.debug(f"HourlyWeatherComponent initialized with config: {config}")

    def get_api_data(self) -> Optional[Dict[str, Any]]:
        """Expose hourly weather data from DB for the API (JSON-serializable)."""
        data = get_latest_weather(self.name)
        if data is None:
            return None
        return _make_json_serializable(data)

    def handle_background_result(self, result: Any) -> None:
        """Called when task finishes; task already saved to DB, refresh display from DB."""
        if result is None:
            return
        self.should_refresh_screen = True
        self.app.root.after(0, self.update)
    
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
        
        # Responsive hourly strip (no scrollbar) - hours share space and wrap to fit
        self.hours_container = tk.Frame(self.main_container)
        self.hours_container.pack(fill=tk.BOTH, expand=True)
        
        # Create hour frames in a grid so they share width equally
        self.hour_frames = []
        for col in range(self.hours_to_show):
            hour_frame = tk.Frame(self.hours_container)
            hour_frame.grid(row=0, column=col, padx=padding['small'], pady=padding['small'], sticky="nsew")
            self.hours_container.columnconfigure(col, weight=1, minsize=50)
            
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
            
            # Responsive wraplength (pixels) so description fits when hours share space
            wrap = max(40, self.scale_padding(25) * 2)
            desc_label = self.create_label(
                hour_frame,
                text="--",
                font_size='tiny',
                wraplength=wrap
            )
            desc_label.pack()
            
            self.hour_frames.append({
                'frame': hour_frame,
                'time': time_label,
                'icon': icon_label,
                'temp': temp_label,
                'desc': desc_label
            })
        self.hours_container.rowconfigure(0, weight=1)
        
        # Error label
        self.error_label = self.create_label(
            self.main_container,
            text="",
            font_size='small',
            fg="red",
            wraplength=300
        )
        self.error_label.pack(pady=padding['small'])
        
        if not self.validate_coordinates():
            return

        self.update()

    def _get_hourly_periods_to_show(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Return list of periods to display: 1 hour ago, current hour, and next 5 (hours_to_show total)."""
        try:
            all_periods = data.get("properties", {}).get("periods") or []
            if not all_periods:
                return []
            n = self.hours_to_show
            now = datetime.now(timezone.utc)
            # Find index of period that contains "now" (last period with startTime <= now, or first if all future)
            current_index = 0
            for i, p in enumerate(all_periods):
                start = datetime.fromisoformat(p["startTime"].replace("Z", "+00:00"))
                if start.tzinfo is None:
                    start = start.replace(tzinfo=timezone.utc)
                if start <= now:
                    current_index = i
                else:
                    break
            # From (current - 1) to (current + 5) inclusive = 7 hours
            start_index = max(0, current_index - 1)
            end_index = min(len(all_periods), start_index + n)
            return all_periods[start_index:end_index]
        except (KeyError, TypeError, ValueError):
            return []

    def update(self) -> None:
        """Update the display with latest weather data from DB."""
        if not self.should_refresh_screen:
            return
        data = get_latest_weather(self.name)
        if not data:
            return
        if "error" in data:
            self.show_error(data["error"])
            self.should_refresh_screen = False
            return
        try:
            self.logger.info(f"Updating Hourly component results")
            periods = self._get_hourly_periods_to_show(data)

            for i, (period, frame) in enumerate(zip(periods, self.hour_frames)):
                time = datetime.fromisoformat(period["startTime"]).strftime("%I%p")
                temp = int(round(period["temperature"]))  # Round temperature to integer
                desc = period["shortForecast"]
                
                frame['time'].config(text=time)
                frame['temp'].config(text=f"{temp}°F")
                frame['desc'].config(text=desc)
                
                # Update icon based on weather condition (responsive size)
                icon_size = max(24, min(48, self.scale_font(12) * 3))
                icon = self.icon_manager.get_icon(desc, size=(icon_size, icon_size))
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
    
    def _manual_refresh(self) -> None:
        """Trigger task run in background; UI updates via handle_background_result."""
        try:
            for frame in self.hour_frames:
                frame["temp"].config(text="...")
            threading.Thread(
                target=lambda: self.app.task_manager.run_task_now(self.name),
                daemon=True,
            ).start()
        except Exception as e:
            self.logger.error(f"Error starting manual refresh: {e}")
    
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