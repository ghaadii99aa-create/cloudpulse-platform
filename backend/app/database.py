from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

# PostgreSQL advisory lock keys. Several API replicas share one database, so writes that read-then-insert are serialized.
_STARTUP_LOCK = 7231001
_DATA_LOCK = 7231002


def lock_data_writes(db: Session) -> None:
    """Serialize simulation and alert writes across replicas until this transaction ends. No-op outside PostgreSQL."""
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _DATA_LOCK})


class Base(DeclarativeBase):
    pass


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        kwargs = {"connect_args": {"check_same_thread": False}}
        if ":memory:" in url or url == "sqlite://":
            kwargs["poolclass"] = StaticPool
        return create_engine(url, **kwargs)
    return create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5)


class Database:
    """Owns the engine and session factory so tests can swap the URL per app instance."""

    def __init__(self, url: str):
        self.engine = make_engine(url)
        self.session_factory = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)

    def create_all(self) -> None:
        from . import models  # noqa: F401  (registers tables)
        Base.metadata.create_all(self.engine)

    @contextmanager
    def startup_lock(self) -> Iterator[None]:
        """Let one replica at a time create tables and seed data. No-op outside PostgreSQL."""
        if self.engine.dialect.name != "postgresql":
            yield
            return
        with self.engine.connect() as conn:
            conn.execute(text("SELECT pg_advisory_lock(:key)"), {"key": _STARTUP_LOCK})
            conn.commit()
            try:
                yield
            finally:
                conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": _STARTUP_LOCK})
                conn.commit()

    def session(self) -> Iterator[Session]:
        db = self.session_factory()
        try:
            yield db
        finally:
            db.close()
