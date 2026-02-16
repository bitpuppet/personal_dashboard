"""
SQLAlchemy engine, session, and base. DB path from config or default.
"""
import logging
from pathlib import Path
from contextlib import contextmanager
from typing import Generator, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base, Session

logger = logging.getLogger(__name__)

Base = declarative_base()

_engine = None
_SessionLocal = None


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Context manager for a single DB session. Commits on success, rolls back on error."""
    if _SessionLocal is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_engine():
    return _engine


def init_db(config_data: Optional[dict] = None, db_url: Optional[str] = None) -> None:
    """
    Initialize database engine and create tables.
    config_data: app config dict; used for database.path if db_url not given.
    db_url: optional SQLAlchemy URL override.
    """
    global _engine, _SessionLocal

    if _engine is not None:
        logger.debug("Database already initialized")
        return

    if db_url is None and config_data:
        db_config = config_data.get("database", {})
        path = db_config.get("path")
        if path:
            path = Path(path).expanduser().resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            db_url = f"sqlite:///{path}"
        if not db_url:
            base = Path.home() / ".personal_dashboard"
            base.mkdir(parents=True, exist_ok=True)
            db_url = f"sqlite:///{base / 'dashboard.db'}"

    if not db_url:
        base = Path.home() / ".personal_dashboard"
        base.mkdir(parents=True, exist_ok=True)
        db_url = f"sqlite:///{base / 'dashboard.db'}"

    _engine = create_engine(db_url, echo=False, future=True)

    # Import all model modules so tables are registered with Base
    from dashboard.core import models as _core_models  # noqa: F401
    try:
        from dashboard.plugins.utilities_bill_due import models as _  # noqa: F401
    except ImportError:
        pass
    try:
        from dashboard.plugins.prayer import models as _  # noqa: F401
    except ImportError:
        pass
    try:
        from dashboard.plugins.classroom import models as _  # noqa: F401
    except ImportError:
        pass
    try:
        from dashboard.plugins.friday_prayer import models as _  # noqa: F401
    except ImportError:
        pass
    try:
        from dashboard.plugins.weather import models as _  # noqa: F401
    except ImportError:
        pass

    Base.metadata.create_all(_engine)
    _SessionLocal = sessionmaker(bind=_engine, autocommit=False, autoflush=False, expire_on_commit=False)
    logger.info(f"Database initialized: {db_url.split('?')[0]}")
