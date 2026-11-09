"""
conftest.py — Test fixtures for the AI service.

Uses an in-memory/file SQLite database for test isolation.
"""
import pytest
from jose import jwt
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from starlette.testclient import TestClient

from app.core.config import settings
from app.db.base import Base
from app.db.database import get_db
from app.main import app

# ── Test SQLite engine ────────────────────────────────────────────────────────
TEST_DB_URL = "sqlite:///./test_ai.db"
test_engine = create_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False, "timeout": 20},
)
TestSessionLocal = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)


def create_all_test_tables():
    Base.metadata.create_all(bind=test_engine)

    with test_engine.connect() as conn:
        # Create external tables owned by API and Repository services
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS memberships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                organization_id INTEGER NOT NULL,
                role TEXT NOT NULL DEFAULT 'member',
                status TEXT NOT NULL DEFAULT 'active',
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS repositories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL,
                github_installation_id INTEGER,
                github_repository_id TEXT NOT NULL,
                name TEXT NOT NULL,
                full_name TEXT NOT NULL,
                owner TEXT NOT NULL,
                description TEXT,
                visibility TEXT DEFAULT 'public',
                default_branch TEXT DEFAULT 'main',
                status TEXT NOT NULL DEFAULT 'connecting',
                last_synced_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS repository_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL,
                repository_id INTEGER NOT NULL,
                path TEXT NOT NULL,
                language TEXT,
                file_type TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                content_checksum TEXT,
                commit_sha TEXT,
                is_indexed BOOLEAN NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'discovered',
                chunk_count INTEGER NOT NULL DEFAULT 0,
                skip_reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.commit()


def drop_all_test_tables():
    Base.metadata.drop_all(bind=test_engine)
    with test_engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS memberships"))
        conn.execute(text("DROP TABLE IF EXISTS repositories"))
        conn.execute(text("DROP TABLE IF EXISTS repository_files"))
        conn.commit()


@pytest.fixture(autouse=True)
def setup_database():
    drop_all_test_tables()
    create_all_test_tables()
    yield
    drop_all_test_tables()


@pytest.fixture
def db():
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db):
    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    c = TestClient(app, raise_server_exceptions=True)
    yield c
    app.dependency_overrides.clear()


def make_auth_token(user_id: int) -> str:
    payload = {"sub": str(user_id)}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def auth_headers(user_id: int) -> dict:
    return {"Authorization": f"Bearer {make_auth_token(user_id)}"}
