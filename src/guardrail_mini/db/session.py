"""Synchronous SQLAlchemy engine and session factory helpers."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def create_database_engine(database_url: str) -> Engine:
    """Create a pre-ping engine, including SQLite's thread option for tests."""

    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, pool_pre_ping=True, connect_args=connect_args)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Return sessions that expire cleanly after transactions complete."""

    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    """Yield a session and always close it, rolling back failed work."""

    with factory() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
