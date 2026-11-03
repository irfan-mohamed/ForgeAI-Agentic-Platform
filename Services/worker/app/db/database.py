from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager

from app.core.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,     # Check connections before using them
    pool_size=5,            # Worker only needs a small pool
    max_overflow=10,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


@contextmanager
def get_db_session() -> Session:
    """
    Context manager for a database session.

    Usage:
        with get_db_session() as db:
            db.query(...)

    The Worker uses this pattern instead of FastAPI's Depends.
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
