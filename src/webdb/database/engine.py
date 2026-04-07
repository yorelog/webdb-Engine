"""Database engine initialisation and session factory."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from webdb.config.settings import get_settings
from webdb.database.models import Base


def _configure_sqlite(engine: Engine) -> None:
    """Enable WAL mode and foreign-key enforcement for SQLite connections."""

    @event.listens_for(engine, "connect")
    def _set_pragma(dbapi_conn, _connection_record):  # noqa: ANN001
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


_engine: Engine | None = None
_SessionFactory: sessionmaker | None = None


def get_engine(db_url: str | None = None) -> Engine:
    """Return (and cache) the SQLAlchemy engine."""
    global _engine
    if _engine is None:
        url = db_url or get_settings().db_url
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        _engine = create_engine(url, connect_args=connect_args, echo=False)
        if url.startswith("sqlite"):
            _configure_sqlite(_engine)
    return _engine


def get_session_factory(db_url: str | None = None) -> sessionmaker:
    """Return (and cache) the session factory."""
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=get_engine(db_url), autocommit=False, autoflush=False)
    return _SessionFactory


def init_db(db_url: str | None = None) -> None:
    """Create all tables (idempotent)."""
    Base.metadata.create_all(get_engine(db_url))


@contextmanager
def get_session(db_url: str | None = None) -> Generator[Session, None, None]:
    """Context manager that yields a transactional Session."""
    factory = get_session_factory(db_url)
    session: Session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
