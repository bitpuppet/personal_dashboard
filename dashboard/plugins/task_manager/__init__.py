from .task_manager_component import TaskManagerComponent

def register_components(plugin_manager):
    """Register task manager component"""
    plugin_manager.register_component(TaskManagerComponent) 