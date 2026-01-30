"""
Classroom Homework component: fetches due homework from Google Classroom
for multiple student accounts and displays in a table.
"""
import os
import tkinter as tk
from tkinter import ttk
from dashboard.core.component_base import DashboardComponent
from typing import Dict, Any, List, Optional
from datetime import datetime
from .classroom_client import ClassroomClient
from .classroom_scraper import ClassroomScraper
from typing import Union

# Type for either API client or scraper (same interface: get_due_assignments)
ClassroomFetcher = Union[ClassroomClient, ClassroomScraper]

class ClassroomHomeworkComponent(DashboardComponent):
    name = "Classroom Homework"

    def __init__(self, app, config: Dict[str, Any]):
        super().__init__(app, config)
        self.cached_data: Optional[List[Dict[str, Any]]] = None
        self.cached_error: Optional[str] = None
        self._fetchers: List[ClassroomFetcher] = []
        self._row_widgets: List[tk.Widget] = []

    def _get_client_secret_path(self) -> str:
        path = self.config.get("client_secret_path") or os.environ.get(
            "GOOGLE_CLASSROOM_CLIENT_SECRET", ""
        )
        if path:
            path = os.path.expanduser(os.path.expandvars(path))
        return path

    def _build_fetchers(self) -> List[ClassroomFetcher]:
        """Build list of ClassroomClient (api) or ClassroomScraper (scrape) from config."""
        fetchers: List[ClassroomFetcher] = []
        backend = (self.config.get("backend") or "api").lower()
        students = self.config.get("students") or []

        if backend == "scrape":
            for entry in students:
                name = entry.get("name")
                profile_path = entry.get("profile_path")
                if not name or not profile_path:
                    continue
                profile_path = os.path.expanduser(os.path.expandvars(profile_path))
                fetchers.append(
                    ClassroomScraper(
                        student_name=name,
                        profile_path=profile_path,
                        logger=self.logger,
                    )
                )
            return fetchers

        # backend == "api"
        client_secret = self._get_client_secret_path()
        for entry in students:
            name = entry.get("name")
            token_file = entry.get("token_file")
            if not name or not token_file:
                continue
            token_file = os.path.expanduser(os.path.expandvars(token_file))
            fetchers.append(
                ClassroomClient(
                    student_name=name,
                    client_secret_path=client_secret,
                    token_path=token_file,
                    logger=self.logger,
                )
            )
        return fetchers

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
            text=self.headline or "Classroom Homework",
            font_size="heading",
            bold=True,
        ).pack(side=tk.LEFT)

        refresh_button = self.create_label(
            header_frame,
            text="↻",
            font_size="heading",
            cursor="hand2",
            fg="#666666",
        )
        refresh_button.pack(side=tk.RIGHT, padx=(0, padding["small"]))
        refresh_button.bind("<Button-1>", lambda e: self._manual_refresh())
        refresh_button.bind("<Enter>", lambda e: refresh_button.configure(fg="#333333"))
        refresh_button.bind("<Leave>", lambda e: refresh_button.configure(fg="#666666"))
        self._create_tooltip(refresh_button, "Refresh homework")

        self.table_frame = tk.Frame(self.main_container)
        self.table_frame.pack(
            fill=tk.BOTH, expand=True, padx=padding["medium"], pady=padding["small"]
        )

        headers = ["Student", "Course", "Assignment", "Due", "Status"]
        for col, header in enumerate(headers):
            self.create_label(
                self.table_frame,
                text=header,
                font_size="small",
                bold=True,
            ).grid(row=0, column=col, padx=padding["small"], pady=2, sticky="w")
        self.table_frame.columnconfigure(0, weight=1, minsize=60)
        self.table_frame.columnconfigure(1, weight=1, minsize=80)
        self.table_frame.columnconfigure(2, weight=2, minsize=100)
        self.table_frame.columnconfigure(3, weight=1, minsize=70)
        self.table_frame.columnconfigure(4, weight=1, minsize=70)

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

        self._fetch_homework()
        update_interval = self.config.get("update_interval", 900)
        self.app.task_manager.schedule_task(
            f"{self.name}_update",
            self._fetch_homework,
            update_interval,
            one_time=False,
        )

    def _create_tooltip(self, widget: tk.Widget, text: str) -> None:
        def show_tooltip(event):
            tooltip = tk.Toplevel()
            tooltip.wm_overrideredirect(True)
            tooltip.wm_geometry(f"+{event.x_root + 10}+{event.y_root + 10}")
            fonts = self.get_responsive_fonts()
            label = tk.Label(
                tooltip,
                text=text,
                justify=tk.LEFT,
                background="#ffffe0",
                relief=tk.SOLID,
                borderwidth=1,
                font=("Arial", fonts["small"]),
            )
            label.pack()

            def hide_tooltip():
                tooltip.destroy()

            widget.tooltip = tooltip
            widget.bind("<Leave>", lambda e: hide_tooltip())
            tooltip.bind("<Leave>", lambda e: hide_tooltip())

        widget.bind("<Enter>", show_tooltip)

    def _fetch_homework(self) -> None:
        """Run in background: fetch for all students, then update UI on main thread."""
        self.cached_error = None
        backend = (self.config.get("backend") or "api").lower()
        self.logger.info(f"Classroom Homework: starting fetch (backend={backend})")
        if backend == "api":
            client_secret = self._get_client_secret_path()
            if not client_secret or not os.path.isfile(client_secret):
                self.cached_error = "Set GOOGLE_CLASSROOM_CLIENT_SECRET or client_secret_path"
                if self.frame and self.frame.winfo_exists():
                    self.frame.after(0, self.update)
                return

        fetchers = self._build_fetchers()
        self.logger.info(f"Classroom Homework: built {len(fetchers)} fetcher(s)")
        if not fetchers:
            if backend == "scrape":
                self.cached_error = "Add at least one student (name, profile_path) in config"
            else:
                self.cached_error = "Add at least one student (name, token_file) in config"
            if self.frame and self.frame.winfo_exists():
                self.frame.after(0, self.update)
            return

        all_assignments: List[Dict[str, Any]] = []
        errors: List[str] = []
        for fetcher in fetchers:
            try:
                self.logger.info(f"Classroom Homework: fetching for {fetcher.student_name}")
                assignments = fetcher.get_due_assignments(
                    include_overdue=True,
                    fetch_submission_status=True,
                )
                all_assignments.extend(assignments)
            except Exception as e:
                self.logger.exception(f"Fetch failed for {fetcher.student_name}")
                errors.append(f"{fetcher.student_name}: {e}")

        if errors:
            self.cached_error = "; ".join(errors[:2])
            if len(errors) > 2:
                self.cached_error += "..."

        all_assignments.sort(key=lambda a: a.get("due_datetime") or datetime.max)
        self.cached_data = all_assignments
        self.logger.info(f"Classroom Homework: fetch done, {len(all_assignments)} assignment(s)")
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
            msg = "No due homework" if not self.cached_error else ""
            lbl = self.create_label(
                self.table_frame, text=msg or "Loading...", font_size="small"
            )
            lbl.grid(row=row, column=0, columnspan=5, padx=padding["small"], pady=4, sticky="w")
            self._row_widgets.append(lbl)
            return

        for i, item in enumerate(self.cached_data):
            row = self.content_start_row + i
            due_dt = item.get("due_datetime")
            due_str = due_dt.strftime("%m/%d %I:%M %p") if due_dt else "--"
            status = item.get("status") or "--"
            for col, val in enumerate(
                [
                    item.get("student_name", "--"),
                    item.get("course_name", "--"),
                    item.get("title", "--"),
                    due_str,
                    status,
                ]
            ):
                lbl = self.create_label(
                    self.table_frame,
                    text=str(val)[:50] + ("..." if len(str(val)) > 50 else ""),
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
            self._fetch_homework,
            0,
            one_time=True,
        )
