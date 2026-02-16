"""
Single place for scheduling: in-memory timers and DB-backed registered tasks.
"""
import asyncio
import logging
import threading
from datetime import datetime, timezone
from queue import Queue
from threading import Timer
from typing import Any, Callable, Dict, List, Optional

from dashboard.core.task import get_next_run_from_db


class TaskManager:
    def __init__(self):
        self.tasks: Dict[str, Any] = {}
        self.result_queue = Queue()
        self.logger = logging.getLogger("TaskManager")
        self._registered_tasks: Dict[str, Callable[..., None]] = {}
        self._registered_config: Dict[str, tuple] = {}  # component_name -> (config, config_data)
        self._setup_async_loop()

    def _setup_async_loop(self) -> None:
        """Setup async event loop in background thread."""
        self.async_loop = asyncio.new_event_loop()

        def run_async_loop():
            asyncio.set_event_loop(self.async_loop)
            self.async_loop.run_forever()

        self.async_thread = threading.Thread(target=run_async_loop, daemon=True)
        self.async_thread.start()

    def schedule_task(self, name: str, callback: Callable, delay: int, one_time: bool = True) -> None:
        """Schedule a task to run after delay seconds."""
        try:
            self.logger.info(f"Scheduling task {name} with delay {delay} seconds")
            if name in self.tasks:
                self.logger.info(f"Cancelling existing task {name}")
                self.tasks[name].cancel()

            scheduled_time = datetime.now().timestamp() + delay
            timer = Timer(delay, self._run_task, args=(name, callback, delay, one_time))
            timer.daemon = True
            timer.scheduled_time = scheduled_time

            self.tasks[name] = timer
            timer.start()
            self.logger.info(f"Timer started for {name}, scheduled for {datetime.fromtimestamp(scheduled_time)}")
        except Exception as e:
            self.logger.error(f"Error scheduling task {name}: {e}")

    def _run_task(self, name: str, callback: Callable, delay: int, one_time: bool) -> None:
        """Run the task and reschedule if needed."""
        try:
            callback()
            if name in self.tasks:
                self.tasks[name].last_run = datetime.now().timestamp()
            if not one_time:
                self.schedule_task(name, callback, delay, one_time)
        except Exception as e:
            self.logger.error(f"Error running task {name}: {e}")

    def register_task(self, component_name: str, runnable: Callable[..., None]) -> None:
        """Register a runnable for a component. runnable(config, result_queue, **kwargs) does the work and updates next_run in DB."""
        self._registered_tasks[component_name] = runnable
        self.logger.debug(f"Registered task for component: {component_name}")

    def schedule_registered_task(
        self,
        component_name: str,
        config: Dict[str, Any],
        config_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Schedule a registered task: run at next_run from DB (or immediately if past due).
        After running, the runnable updates next_run in DB; we reschedule again for the new next_run.
        """
        if component_name not in self._registered_tasks:
            self.logger.warning(f"No task registered for component: {component_name}")
            return
        self._registered_config[component_name] = (config, config_data)
        next_run = get_next_run_from_db(component_name)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        # If next_run_at is null (no row or column null), run immediately
        if next_run is None:
            delay = 0
        else:
            delta = (next_run - now).total_seconds()
            delay = max(0, int(delta))
        callback = lambda: self._run_registered_and_reschedule(component_name)
        self.schedule_task(component_name, callback, delay, one_time=True)

    def _run_registered_and_reschedule(self, component_name: str) -> None:
        """Run the registered runnable then reschedule for next_run from DB."""
        runnable = self._registered_tasks.get(component_name)
        if runnable:
            try:
                config, config_data = self._registered_config.get(component_name, (None, None))
                if config is None:
                    return
                if config_data is not None:
                    runnable(config, self.result_queue, config_data=config_data)
                else:
                    runnable(config, self.result_queue)
            except Exception as e:
                self.logger.exception(f"Registered task {component_name} failed: {e}")
        config, config_data = self._registered_config.get(component_name, (None, None))
        if config is not None:
            self.schedule_registered_task(component_name, config, config_data)

    def get_active_timers(self) -> List[Dict[str, Any]]:
        """Return list of active timer names and their next run time (for API)."""
        result = []
        for name, timer in self.tasks.items():
            if getattr(timer, "scheduled_time", None) is not None:
                next_run = datetime.fromtimestamp(timer.scheduled_time, tz=timezone.utc)
                result.append({"name": name, "next_run_at": next_run})
        return result

    def run_task_now(
        self,
        component_name: str,
        config: Dict[str, Any],
        config_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Run a registered task once immediately (e.g. manual refresh). Puts result on result_queue."""
        runnable = self._registered_tasks.get(component_name)
        if not runnable:
            self.logger.warning(f"No task registered for component: {component_name}")
            return
        try:
            if config_data is not None:
                runnable(config, self.result_queue, config_data=config_data)
            else:
                runnable(config, self.result_queue)
        except Exception as e:
            self.logger.exception(f"Run task now {component_name} failed: {e}")

    def stop(self) -> None:
        """Stop all scheduled tasks."""
        for task in self.tasks.values():
            task.cancel()
        if hasattr(self, "async_loop"):
            self.async_loop.call_soon_threadsafe(self.async_loop.stop)
