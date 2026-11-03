"""
conftest.py — Shared pytest fixtures for Worker Service tests.

Uses an in-memory SQLite database so tests don't require a running PostgreSQL.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
import app.models  # noqa: F401 — registers all models


@pytest.fixture(scope="session")
def engine():
    """In-memory SQLite engine for tests."""
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=eng)
    return eng


@pytest.fixture
def db(engine):
    """Database session that rolls back after each test."""
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
