"""
Utilities Bill Due component: displays bill due status from DB.
Data is filled by the registered task; UI reads via service.
"""
import threading
import tkinter as tk
from tkinter import ttk
from typing import Any, Dict, List, Optional

from dashboard.core.component_base import DashboardComponent
from .backends import BillDueInfo
from .service import get_latest_bills
from .task import UtilitiesBillDueTask


class UtilitiesBillDueComponent(DashboardComponent):
    name = "Utilities Bill Due"

    def __init__(self, app, config: Dict[str, Any]):
        super().__init__(app, config)
        self._row_widgets: List[tk.Widget] = []
        self.task = UtilitiesBillDueTask(self.name, config)
        self.task.ensure_scheduled()
        self.app.task_manager.register_task(self.name, self.task.run)
        self.app.task_manager.schedule_registered_task(
            self.name, config, self.app.config.data
        )

    def handle_background_result(self, result: Any) -> None:
        """Called on main thread when task finishes; redraw from DB."""
        self.update()

    def get_api_data(self) -> Optional[Dict[str, Any]]:
        """Expose latest bill data for the API (serializable dict)."""
        try:
            items = get_latest_bills(self.name)
        except Exception:
            return None
        out = []
        for item in items:
            out.append({
                "utility_type": item.utility_type,
                "source": item.source,
                "due_date": item.due_date.isoformat() if item.due_date else None,
                "amount_due": item.amount_due,
                "payment_due": item.payment_due,
                "current_balance": item.current_balance,
                "current_bill_billed_date": item.current_bill_billed_date.isoformat() if item.current_bill_billed_date else None,
                "last_payment_amount": item.last_payment_amount,
                "last_payment_date": item.last_payment_date.isoformat() if item.last_payment_date else None,
                "raw_status": item.raw_status,
                "usage": item.usage,
            })
        return {"bills": out}

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

        headers = ["Utility", "Source", "Due Date", "Usage", "Status"]
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

        self.update()

    def update(self) -> None:
        """Redraw table from DB via service (main thread)."""
        padding = self.get_responsive_padding()
        for w in self._row_widgets:
            try:
                w.destroy()
            except Exception:
                pass
        self._row_widgets.clear()
        self.error_label.config(text="")

        try:
            items: List[BillDueInfo] = get_latest_bills(self.name)
        except Exception as e:
            self.logger.exception(f"Failed to load utilities from DB: {e}")
            self.error_label.config(text=str(e))
            items = []

        if not items:
            lbl = self.create_label(
                self.table_frame, text="No bill data", font_size="small"
            )
            lbl.grid(row=self.content_start_row, column=0, columnspan=5, padx=padding["small"], pady=4, sticky="w")
            self._row_widgets.append(lbl)
            return

        for i, item in enumerate(items):
            row = self.content_start_row + i
            due_str = item.due_date.strftime("%m/%d/%Y") if item.due_date else ""
            raw = (getattr(item, "raw_status", None) or "").strip()
            if raw and not raw.lower().startswith("balance="):
                status = raw
            elif (item.source or "").strip() in ("CoServ", "Farmers Electric"):
                status = "Due (autopay)" if item.payment_due else "Not due (autopay)"
            else:
                status = "Due" if item.payment_due else "Not due"
            utility_display = (item.utility_type or "").capitalize()
            usage_str = getattr(item, "usage", None) or "—"
            for col, val in enumerate([
                utility_display,
                item.source or "—",
                due_str or "—",
                usage_str,
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
        """Run task once in background; UI refreshes via result_queue."""
        def run():
            self.app.task_manager.run_task_now(
                self.name, self.config, self.app.config.data
            )

        threading.Thread(target=run, daemon=True).start()
