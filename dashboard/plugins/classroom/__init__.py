from .classroom_component import ClassroomHomeworkComponent

def register_components(plugin_manager):
    """Register Classroom Homework component"""
    plugin_manager.register_component(ClassroomHomeworkComponent)
