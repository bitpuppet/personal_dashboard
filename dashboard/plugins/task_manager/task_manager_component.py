import tkinter as tk
from tkinter import ttk
from dashboard.core.component_base import DashboardComponent
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

class TaskManagerComponent(DashboardComponent):
    name = "Task Manager"
    
    def __init__(self, app, config: Dict[str, Any]):
        super().__init__(app, config)
        self.update_interval = config.get('update_interval', 1000)  # Update every second by default
    
    def initialize(self, parent: tk.Frame) -> None:
        super().initialize(parent)
        
        # Get responsive sizing
        fonts = self.get_responsive_fonts()
        padding = self.get_responsive_padding()
        
        # Create main container
        self.main_container = tk.Frame(self.frame, relief=tk.GROOVE, borderwidth=1)
        self.main_container.pack(padx=padding['small'], pady=padding['small'], fill=tk.BOTH, expand=True)
        
        # Header
        header_frame = tk.Frame(self.main_container)
        header_frame.pack(fill=tk.X, padx=padding['medium'], pady=(padding['small'], 0))
        
        self.create_label(
            header_frame,
            text=self.headline or "Scheduled Tasks",
            font_size='heading',
            bold=True
        ).pack(side=tk.LEFT)
        
        # Create table
        self.table_frame = tk.Frame(self.main_container)
        self.table_frame.pack(fill=tk.BOTH, expand=True, padx=padding['medium'], pady=padding['small'])
        
        # Headers
        headers = ["Task", "Next Run", "Status", "Interval"]
        for col, header in enumerate(headers):
            self.create_label(
                self.table_frame,
                text=header,
                font_size='small',
                bold=True
            ).grid(row=0, column=col, padx=padding['small'], pady=2, sticky='w')
        
        # Add separator
        separator = ttk.Separator(self.table_frame, orient='horizontal')
        separator.grid(row=1, column=0, columnspan=len(headers), sticky='ew', pady=padding['small'])
        
        # Initialize task rows
        self.task_rows = {}
        self._create_task_rows()
        
        # Schedule updates
        self.update()
    
    def _create_task_rows(self) -> None:
        """Create rows for each scheduled task"""
        padding = self.get_responsive_padding()
        current_row = 2  # Start after headers and separator
        
        for task_name, task in self.app.task_manager.tasks.items():
            # Create labels for this task
            task_labels = {
                'name': self.create_label(self.table_frame, text=task_name, font_size='small'),
                'next_run': self.create_label(self.table_frame, text="--:--", font_size='small'),
                'status': self.create_label(self.table_frame, text="--", font_size='small'),
                'interval': self.create_label(self.table_frame, text="--", font_size='small')
            }
            
            # Grid the labels
            task_labels['name'].grid(row=current_row, column=0, padx=padding['small'], pady=2, sticky='w')
            task_labels['next_run'].grid(row=current_row, column=1, padx=padding['small'], pady=2)
            task_labels['status'].grid(row=current_row, column=2, padx=padding['small'], pady=2)
            task_labels['interval'].grid(row=current_row, column=3, padx=padding['small'], pady=2)
            
            self.task_rows[task_name] = task_labels
            
            # Add separator
            current_row += 1
            separator = ttk.Separator(self.table_frame, orient='horizontal')
            separator.grid(row=current_row, column=0, columnspan=4, sticky='ew', pady=padding['small'])
            current_row += 1
    
    def _format_timedelta(self, td: timedelta) -> str:
        """Format timedelta into readable string"""
        total_seconds = int(td.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        
        if hours > 0:
            return f"{hours}h {minutes}m"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"
    
    def _get_next_run(self, task) -> Optional[float]:
        """Calculate next run time for a task"""
        try:
            if hasattr(task, 'interval') and hasattr(task, 'last_run'):
                if task.last_run is None:  # Task hasn't run yet
                    return datetime.now().timestamp()
                return task.last_run + task.interval
            return None
        except Exception as e:
            self.logger.error(f"Error calculating next run time: {e}")
            return None

    def update(self) -> None:
        """Update task display"""
        try:
            now = datetime.now()
            
            # Check if we need to recreate rows (new tasks added)
            current_tasks = set(self.app.task_manager.tasks.keys())
            displayed_tasks = set(self.task_rows.keys())
            
            if current_tasks != displayed_tasks:
                # Clear existing rows
                for widgets in self.table_frame.winfo_children():
                    widgets.destroy()
                # Recreate rows
                self._create_task_rows()
            
            # Update existing task info
            for task_name, task in self.app.task_manager.tasks.items():
                if task_name in self.task_rows:
                    labels = self.task_rows[task_name]
                    
                    # Update next run time
                    next_run_time = None
                    
                    # Try to get scheduled_time from timer (stored when task was created)
                    if hasattr(task, 'scheduled_time'):
                        next_run_time = task.scheduled_time
                    # Fallback: try _when attribute (private Timer attribute)
                    elif hasattr(task, '_when') and task._when is not None:
                        next_run_time = task._when
                    # Fallback: calculate from last_run + interval if recurring
                    elif hasattr(task, 'last_run') and task.last_run and hasattr(task, 'interval') and task.interval:
                        next_run_time = task.last_run + task.interval
                    # Fallback: calculate from delay if task hasn't run yet
                    elif hasattr(task, 'delay'):
                        next_run_time = datetime.now().timestamp() + task.delay
                    
                    if next_run_time:
                        time_left = next_run_time - now.timestamp()
                        if time_left > 0:
                            labels['next_run'].config(
                                text=self._format_timedelta(timedelta(seconds=time_left))
                            )
                        else:
                            labels['next_run'].config(text="Due")
                    else:
                        labels['next_run'].config(text="Unknown")
                    
                    # Update status
                    labels['status'].config(
                        text="Active" if not task.finished.is_set() else "Finished"
                    )
                    
                    # Update interval
                    if hasattr(task, 'interval') and task.interval is not None:
                        labels['interval'].config(
                            text=self._format_timedelta(timedelta(seconds=task.interval))
                        )
                    else:
                        labels['interval'].config(text="One-time")
            
            # Schedule next update
            self.frame.after(self.update_interval, self.update)
            
        except Exception as e:
            self.logger.error(f"Error updating task manager display: {e}") 