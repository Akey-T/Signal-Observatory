"""Database engine creation, validation, and session helpers."""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker


class DatabaseUnavailableError(RuntimeError):
    """Raised after all database connection attempts fail."""


def create_database_engine(database_url: str, *, echo: bool = False) -> Engine:
    """Create a pre-ping engine with safe SQLite test defaults."""

    connect_args: dict[str, object] = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(
        database_url,
        echo=echo,
        pool_pre_ping=True,
        connect_args=connect_args,
    )


def database_is_ready(engine: Engine) -> bool:
    """Return whether a trivial query can be executed."""

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return False
    return True


def wait_for_database(engine: Engine, *, attempts: int, delay_seconds: float) -> None:
    """Retry database connectivity with a bounded delay."""

    last_error: SQLAlchemyError | None = None
    for attempt in range(1, attempts + 1):
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return
        except SQLAlchemyError as error:
            last_error = error
            if attempt < attempts:
                time.sleep(delay_seconds)
    raise DatabaseUnavailableError(
        f"database unavailable after {attempts} attempts"
    ) from last_error


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    """Commit a unit of work, rolling it back on any exception."""

    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
