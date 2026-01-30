"""
Utilities Bill Due component: fetches bill due status from multiple backends
(Water, Gas, Electric) and displays Utility, Source, Due Date, Status (no amount on UI).
"""
import os
import tkinter as tk
from tkinter import ttk
from datetime import date, datetime, timedelta
from typing import Dict, Any, List, Optional

from dashboard.core.component_base import DashboardComponent
from .backends import BillDueInfo, get_backend


class UtilitiesBillDueComponent(DashboardComponent):
    name = "Utilities Bill Due"

    def __init__(self, app, config: Dict[str, Any]):
        super().__init__(app, config)
        self.cached_data: Optional[List[BillDueInfo]] = None
        self.cached_error: Optional[str] = None
        self._backends: List[Any] = []
        self._row_widgets: List[tk.Widget] = []

    def _build_backends(self) -> List[Any]:
        """Build list of backends from config['backends']."""
        backends = []
        component_headless = self.config.get("headless")
        cache_dir = self.app.config.data.get("cache", {}).get("directory")
        for entry in self.config.get("backends") or []:
            backend_type = entry.get("type")
            if not backend_type:
                continue
            # Allow component-level headless to override
            entry_config = dict(entry)
            if "headless" not in entry_config and component_headless is not None:
                entry_config["headless"] = component_headless
            if "cache_dir" not in entry_config and cache_dir:
                entry_config["cache_dir"] = cache_dir
            be = get_backend(backend_type, entry_config, logger=self.logger)
            if be:
                backends.append(be)
        return backends

    def _schedule_next_daily_run(self) -> None:
        """Schedule next run at schedule_time (e.g. 07:00) next day."""
        schedule_time = self.config.get("schedule_time")
        if not schedule_time:
            return
        try:
            parts = str(schedule_time).strip().split(":")
            hour = int(parts[0]) if parts else 0
            minute = int(parts[1]) if len(parts) > 1 else 0
        except (ValueError, IndexError):
            hour, minute = 7, 0
        now = datetime.now()
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if now >= target:
            target += timedelta(days=1)
        delay = int((target - now).total_seconds())
        task_name = f"{self.name}_daily_fetch"
        if task_name in self.app.task_manager.tasks:
            self.app.task_manager.tasks[task_name].cancel()
        self.app.task_manager.schedule_task(
            task_name,
            self._run_fetch_and_reschedule,
            delay,
            one_time=True,
        )
        self.logger.info(f"Utilities Bill Due: next daily fetch at {target.strftime('%H:%M')}")

    def _run_fetch_and_reschedule(self) -> None:
        """Run fetch then schedule next daily run (for schedule_time)."""
        self._fetch_bills()
        self._schedule_next_daily_run()

    def initialize(self, parent: tk.Frame) -> None:
        super().initialize(parent)
        padding = self.get_responsive_padding()

        self.main_container = tk.Frame(self.frame, relief=tk.GROOVE, borderwidth=1)
        self.main_container.pack(
            padx=padding["small"], pady=padding["small"], fill=tk.BOTH, expand=True
        )

        header_frame = tk.Frame(self.main_container)
        header_frame.pack(fill=tk.X, padx=padding["medium"], pady=(padding["small"], 0))

        self.create_label(
            header_frame,
            text=self.headline or self.name,
            font_size="heading",
            bold=True,
        ).pack(side=tk.LEFT)

        refresh_btn = self.create_label(
            header_frame,
            text="↻",
            font_size="heading",
            cursor="hand2",
            fg="#666666",
        )
        refresh_btn.pack(side=tk.RIGHT, padx=(0, padding["small"]))
        refresh_btn.bind("<Button-1>", lambda e: self._manual_refresh())
        refresh_btn.bind("<Enter>", lambda e: refresh_btn.configure(fg="#333333"))
        refresh_btn.bind("<Leave>", lambda e: refresh_btn.configure(fg="#666666"))

        self.table_frame = tk.Frame(self.main_container)
        self.table_frame.pack(
            fill=tk.BOTH, expand=True, padx=padding["medium"], pady=padding["small"]
        )

        headers = ["Utility", "Source", "Due Date", "Status"]
        for col, header in enumerate(headers):
            self.create_label(
                self.table_frame,
                text=header,
                font_size="small",
                bold=True,
            ).grid(row=0, column=col, padx=padding["small"], pady=2, sticky="w")
        for col in range(len(headers)):
            self.table_frame.columnconfigure(col, weight=1, minsize=50)
        sep = ttk.Separator(self.table_frame, orient="horizontal")
        sep.grid(row=1, column=0, columnspan=len(headers), sticky="ew", pady=padding["small"])

        self.content_start_row = 2
        self.error_label = self.create_label(
            self.main_container,
            text="",
            font_size="small",
            fg="#cc6666",
            wraplength=350,
        )
        self.error_label.pack(pady=padding["small"])

        # Run initial fetch in background so UI loads immediately (shows "Loading..." until done)
        self.app.task_manager.schedule_task(
            f"{self.name}_initial_fetch",
            self._fetch_bills,
            0,
            one_time=True,
        )

        schedule_time = self.config.get("schedule_time")
        update_interval = self.config.get("update_interval", 86400)
        if schedule_time:
            self._schedule_next_daily_run()
        else:
            self.app.task_manager.schedule_task(
                f"{self.name}_update",
                self._fetch_bills,
                update_interval,
                one_time=False,
            )

    def _fetch_bills(self) -> None:
        """Run in background: fetch from all backends, then update UI on main thread."""
        self.cached_error = None
        self._backends = self._build_backends()
        if not self._backends:
            self.cached_error = "Add at least one backend in config (backends: type, utility_type, username_env, password_env)"
            if self.frame and self.frame.winfo_exists():
                self.frame.after(0, self.update)
            return

        self.logger.info(f"Utilities Bill Due: starting fetch ({len(self._backends)} backend(s))")
        all_items: List[BillDueInfo] = []
        errors: List[str] = []
        for backend in self._backends:
            try:
                items = backend.get_bill_due_info()
                all_items.extend(items)
            except Exception as e:
                self.logger.exception(f"Utilities Bill Due: backend failed: {e}")
                errors.append(str(e))

        if errors:
            self.cached_error = "; ".join(errors[:2])
            if len(errors) > 2:
                self.cached_error += "..."

        all_items.sort(key=lambda x: x.due_date or date(9999, 12, 31))
        self.cached_data = all_items
        self.logger.info(f"Utilities Bill Due: fetch done, {len(all_items)} item(s)")
        if self.frame and self.frame.winfo_exists():
            self.frame.after(0, self.update)

    def update(self) -> None:
        """Redraw table from cached_data (main thread)."""
        padding = self.get_responsive_padding()
        for w in self._row_widgets:
            try:
                w.destroy()
            except Exception:
                pass
        self._row_widgets.clear()

        if self.cached_error:
            self.error_label.config(text=self.cached_error)
        else:
            self.error_label.config(text="")

        if not self.cached_data:
            row = self.content_start_row
            msg = "No bill data" if not self.cached_error else ""
            lbl = self.create_label(
                self.table_frame, text=msg or "Loading...", font_size="small"
            )
            lbl.grid(row=row, column=0, columnspan=4, padx=padding["small"], pady=4, sticky="w")
            self._row_widgets.append(lbl)
            return

        for i, item in enumerate(self.cached_data):
            row = self.content_start_row + i
            due_str = ""
            if item.due_date:
                due_str = item.due_date.strftime("%m/%d/%Y") if item.due_date else ""
            status = "Due" if item.payment_due else "Not due"
            utility_display = (item.utility_type or "").capitalize()
            for col, val in enumerate([
                utility_display,
                item.source or "—",
                due_str or "—",
                status,
            ]):
                lbl = self.create_label(
                    self.table_frame,
                    text=str(val)[:40] + ("..." if len(str(val)) > 40 else ""),
                    font_size="small",
                )
                lbl.grid(row=row, column=col, padx=padding["small"], pady=2, sticky="w")
                self._row_widgets.append(lbl)

    def _manual_refresh(self) -> None:
        task_name = f"{self.name}_manual_refresh"
        if task_name in self.app.task_manager.tasks:
            self.app.task_manager.tasks[task_name].cancel()
        self.app.task_manager.schedule_task(
            task_name,
            self._fetch_bills,
            0,
            one_time=True,
        )
