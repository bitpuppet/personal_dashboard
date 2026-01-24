import tkinter as tk
from dashboard.core.component_base import DashboardComponent

class HelloWorldComponent(DashboardComponent):
    name = "Hello World"
    
    def initialize(self, parent: tk.Frame) -> None:
        super().initialize(parent)
        padding = self.get_responsive_padding()
        self.label = self.create_label(
            self.frame,
            text="Hello, World!",
            font_size='title'
        )
        self.label.pack(pady=padding['large'])
        
    def update(self) -> None:
        pass  # Nothing to update in this simple component 