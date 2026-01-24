from contextvars import ContextVar
from typing import Optional
from contextlib import contextmanager

class DashboardContext:
    """Context-based storage for dashboard app"""
    _app_context: ContextVar = ContextVar('dashboard_app', default=None)

    @classmethod
    def get_app(cls):
        """Get the current app instance"""
        app = cls._app_context.get()
        if app is None:
            raise RuntimeError("No dashboard app context found. Are you running outside the app context?")
        return app

    @classmethod
    @contextmanager
    def app_context(cls, app):
        """Context manager for dashboard app"""
        token = cls._app_context.set(app)
        try:
            yield app
        finally:
            cls._app_context.reset(token)

    @classmethod
    def set_app(cls, app):
        """Set the current app instance"""
        cls._app_context.set(app)

    @classmethod
    def clear_app(cls):
        """Clear the current app instance"""
        cls._app_context.set(None) 