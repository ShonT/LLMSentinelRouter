"""
Database connection and session management.
"""

import logging
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session as SQLAlchemySession

from .config import settings
from .models import Base

logger = logging.getLogger(__name__)

# Create engine
engine = create_engine(
    settings.database_url,
    echo=False,  # Set to True for SQL logging
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """
    Initialize the database by creating all tables.
    """
    logger.info("Initializing database...")
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created.")


def drop_db() -> None:
    """
    Drop all tables (for testing).
    """
    logger.warning("Dropping all database tables!")
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
    db = SessionLocal()
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
    return SessionLocal()