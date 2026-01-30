# Personal Dashboard

A Tkinter-based personal dashboard that displays weather, utilities, prayer times, and other widgets. Plugins are discovered from `dashboard/plugins` and configured via `config/config.yaml`.

## Plugins

| Plugin | Description |
|--------|-------------|
| **Hello World** | Minimal example component; displays "Hello, World!". |
| **Hourly Weather** | Today's hourly forecast (NWS or OpenWeatherMap backend). |
| **Weekly Weather** | Multi-day outlook (NWS or OpenWeatherMap backend). Set `forecast_days` (1–14) in config; default 4. |
| **Weather** | Legacy weather component (single view). |
| **Utilities Bill Due** | Bill due dates and status for water, gas, electric, and other utilities. Supports scraped backends (Murphy TX, Farmers Electric, CoServ) and a **manual** backend where you define entries in config (name, source, due date, optional amount/status). Due dates can be fixed (e.g. `YYYY-MM-DD`) or recurring (e.g. `on every 14` for day-of-month). |
| **Prayer Times** | Daily prayer times (e.g. Aladhan API) with optional adhan audio. |
| **Friday Prayer** | Friday (Jumu'ah) prayer times per mosque (e.g. Sachse Islamic Center, East Plano). |
| **Task Manager** | View scheduled tasks. |
| **Classroom Homework** | Due homework from Google Classroom (OAuth2). |
| **System Logs** | Log viewer; appears at bottom of the window. |

### Utilities Bill Due backends

- **murphytx** – Water (Murphy TX municipal portal).
- **farmerselectric** – Electric (Farmers Electric SmartHub).
- **coserv** – Gas (CoServ SmartHub).
- **manual** – Config-defined entries: `name`, `source`, `due_date` (fixed or `on every N`), optional `amount`, optional `status`.

---

## How to create a plugin

### 1. Add a plugin package

Create a new folder under `dashboard/plugins/` with at least:

- `__init__.py` – exports `register_components(plugin_manager)`.
- A component module (e.g. `my_component.py`) – defines a class that extends `DashboardComponent`.

Example layout:

```
dashboard/plugins/
  my_plugin/
    __init__.py
    my_component.py
```

### 2. Implement `register_components`

In `dashboard/plugins/my_plugin/__init__.py`:

```python
from .my_component import MyPluginComponent

def register_components(plugin_manager):
    plugin_manager.register_component(MyPluginComponent)
```

The plugin manager discovers all packages under `dashboard.plugins` and calls `register_components(plugin_manager)` when that function exists.

### 3. Implement the component

Your component must extend `DashboardComponent` and define:

- **`name`** – Class attribute; must match the key you use in `config.yaml` (e.g. `name = "My Plugin"`).
- **`initialize(self, parent)`** – Create Tk widgets (labels, frames, etc.) under `parent`. Call `super().initialize(parent)` and use `self.frame` as the root for your content. Use `self.create_label()`, `self.get_responsive_padding()`, `self.get_responsive_fonts()` from the base for consistent styling.
- **`update(self)`** – Called periodically; refresh the displayed data if needed.

Optional:

- **`handle_background_result(self, result)`** – If you run background tasks via `app.task_manager.schedule_task()`, the main thread calls this with the result; use it to update the UI safely.
- **`destroy(self)`** – Clean up if the component is removed.

Minimal example (`my_component.py`):

```python
import tkinter as tk
from dashboard.core.component_base import DashboardComponent

class MyPluginComponent(DashboardComponent):
    name = "My Plugin"

    def initialize(self, parent: tk.Frame) -> None:
        super().initialize(parent)
        padding = self.get_responsive_padding()
        self.create_label(self.frame, text="My content", font_size="title").pack(pady=padding["large"])

    def update(self) -> None:
        pass  # Refresh data here if needed
```

### 4. Add config

In `config/config.yaml`, under `components:`, add an entry whose key is exactly your component `name`:

```yaml
components:
  "My Plugin":
    enable: true
    headline: "My Plugin"
    row: 0
    column: 0
    update_interval: 60000
```

- **`enable: true`** – Required for the component to be created.
- **`row`** / **`column`** – Layout position (see existing plugins).
- **`update_interval`** – Milliseconds between `update()` calls (optional; app default if omitted).

The app only instantiates a component when it has config and `enable` is true. After that, the layout manager places it by `row`/`column`.

### 5. Run the dashboard

Start the app (e.g. `python -m dashboard.main` or your usual entry point). The plugin manager will load `dashboard.plugins.my_plugin` and register your component; the app will create it and add it to the layout.

For a minimal reference plugin, see **Hello World** (`dashboard/plugins/hello_world/`).
