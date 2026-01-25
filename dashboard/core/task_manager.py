import asyncio
from typing import Any, Callable
import logging
from queue import Queue
import threading
from datetime import datetime
from threading import Timer

class TaskManager:
    def __init__(self):
        self.tasks = {}
        self.result_queue = Queue()
        self.logger = logging.getLogger("TaskManager")
        self._setup_async_loop()
    
    def _setup_async_loop(self):
        """Setup async event loop in background thread"""
        self.async_loop = asyncio.new_event_loop()
        def run_async_loop():
            asyncio.set_event_loop(self.async_loop)
            self.async_loop.run_forever()
        
        self.async_thread = threading.Thread(target=run_async_loop, daemon=True)
        self.async_thread.start()
    
    def schedule_task(self, name: str, callback, delay: int, one_time: bool = True) -> None:
        """Schedule a task to run after delay seconds"""
        try:
            # Cancel existing task if any
            self.logger.info(f"Scheduling task {name} with delay {delay} seconds")
            if name in self.tasks:
                self.logger.info(f"Cancelling existing task {name}")
                self.tasks[name].cancel()
            
            # Calculate when the task should run
            scheduled_time = datetime.now().timestamp() + delay
            
            # Create new timer
            timer = Timer(delay, self._run_task, args=(name, callback, delay, one_time))
            timer.daemon = True
            
            # Store metadata on the timer for display purposes
            timer.scheduled_time = scheduled_time
            # timer.delay = delay
            # timer.interval = delay if not one_time else None
            # timer.one_time = one_time
            # timer.last_run = None  # Will be set when task runs
            
            # Store and start timer
            self.tasks[name] = timer
            timer.start()
            self.logger.info(f"Timer started for {name}, scheduled for {datetime.fromtimestamp(scheduled_time)}")
        except Exception as e:
            self.logger.error(f"Error scheduling task {name}: {e}")

    def _run_task(self, name: str, callback, delay: int, one_time: bool) -> None:
        """Run the task and reschedule if needed"""
        try:
            # Run the callback
            callback()
            
            # Update last run time
            if name in self.tasks:
                self.tasks[name].last_run = datetime.now().timestamp()
            
            # Reschedule if not one time
            if not one_time:
                self.schedule_task(name, callback, delay, one_time)
                
        except Exception as e:
            self.logger.error(f"Error running task {name}: {e}")
    
    def stop(self) -> None:
        """Stop all scheduled tasks"""
        for task in self.tasks.values():
            task.cancel()
        if hasattr(self, 'async_loop'):
            self.async_loop.call_soon_threadsafe(self.async_loop.stop) 