"""Engine and session factory for SkillsBank SQLite database."""

from __future__ import annotations

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


def create_engine_from_url(
    url: str = "sqlite:///skillsbank.db",
    echo: bool = False,
) -> Engine:
    """Create a SQLAlchemy engine with SQLite pragmas for performance."""
    engine = create_engine(url, echo=echo)

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

    return engine


def get_session(engine: Engine) -> Session:
    """Create a configured session bound to the given engine."""
    factory = sessionmaker(bind=engine)
    return factory()
