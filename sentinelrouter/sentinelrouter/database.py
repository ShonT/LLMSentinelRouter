"""
Database connection and session management.
"""

import logging
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session as SQLAlchemySession

from .config import get_settings

logger = logging.getLogger(__name__)

# Module-level singletons for engine and session factory
_engine = None
_SessionLocal = None


def _init_engine_and_session():
    """Initialize the engine and session factory singletons if not already created."""
    global _engine, _SessionLocal
    if _engine is None:
        settings = get_settings()
        logger.info("Creating database engine (singleton)")
        _engine = create_engine(
            settings.database_url,
            echo=False,  # Set to True for SQL logging
            connect_args={"check_same_thread": False}
            if "sqlite" in settings.database_url
            else {},
        )
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
        logger.info("Database engine and session factory initialized")


# Lazy initialization of engine to avoid validation errors during imports
def get_engine():
    """Return the database engine, initializing if necessary."""
    _init_engine_and_session()
    return _engine


# Lazy initialization of SessionLocal
def get_session_local():
    """Return the sessionmaker, initializing if necessary."""
    _init_engine_and_session()
    return _SessionLocal


def init_db() -> None:
    """
    Initialize the database by creating all tables.
    """
    from .models import Base

    logger.info("Initializing database...")
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created.")


def drop_db() -> None:
    """
    Drop all tables (for testing).
    """
    from .models import Base

    logger.warning("Dropping all database tables!")
    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    logger.info("All tables dropped.")


@contextmanager
def get_db() -> SQLAlchemySession:
    """
    Context manager for database sessions.

    Usage:
        with get_db() as db:
            db.add(...)
            db.commit()
    """
    db = get_session_local()()
    try:
        yield db
        db.commit()
    except Exception as e:
        db.rollback()
        logger.exception("Database session rollback due to exception: %s", e)
        raise
    finally:
        db.close()


def get_db_session() -> SQLAlchemySession:
    """
    Return a database session (without automatic commit/rollback).
    Caller must manage commit/rollback and close.
    """
    return get_session_local()()
