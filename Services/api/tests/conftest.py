"""
Shared pytest fixtures for FlowForge API tests.

Key design decisions
────────────────────
1. DATABASE_URL is overridden via os.environ BEFORE any app module is imported,
   so pydantic-settings / SQLAlchemy both pick up SQLite for the entire test run.
   No real PostgreSQL is required in CI.

2. We use a temporary SQLite FILE (not :memory:) so that all connections — the
   app's own engine created at import time, and the test engine — share the
   same database without needing StaticPool tricks.

3. Tables are created fresh for every test (function scope) and dropped in
   teardown, giving full isolation with no shared state between tests.

4. `get_db` is overridden in the client fixture so every request uses the same
   session as the fixture, making test assertions consistent.
"""
import os

# ── Must be set BEFORE any app import so Settings() reads the right values ───
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_temp.db")
os.environ.setdefault("SECRET_KEY", "test-only-secret-key-not-for-production")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.db.base import Base
from app.db.database import get_db
from app.main import app

# ── Test engine — points at the same file as DATABASE_URL above ───────────────
TEST_ENGINE = create_engine(
    "sqlite:///./test_temp.db",
    connect_args={"check_same_thread": False},
)
TestingSessionLocal = sessionmaker(
    bind=TEST_ENGINE,
    autoflush=False,
    autocommit=False,
)


# ── Table lifecycle ────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True, scope="function")
def _tables():
    """
    Create all tables before every test and drop them afterwards.
    autouse=True means every test gets a clean schema automatically.
    """
    Base.metadata.create_all(bind=TEST_ENGINE)
    yield
    Base.metadata.drop_all(bind=TEST_ENGINE)


# ── Session ───────────────────────────────────────────────────────────────────

@pytest.fixture(scope="function")
def db(_tables) -> Session:
    """Provides a SQLite session that is guaranteed to see the tables."""
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


# ── HTTP client ───────────────────────────────────────────────────────────────

@pytest.fixture(scope="function")
def client(db: Session) -> TestClient:
    """
    TestClient with the get_db dependency overridden to use our SQLite session.

    Using `with TestClient(app) as c` triggers the FastAPI lifespan, which
    calls create_all on the app's SQLite engine (same file → no-op since
    tables already exist from the `db` fixture).
    """

    def override_get_db():
        try:
            yield db
        finally:
            pass  # session lifetime is managed by the `db` fixture

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


# ── Convenience fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def registered_user(client: TestClient) -> dict:
    """Registers a default test user and returns the payload used."""
    payload = {
        "name": "Test User",
        "email": "test@example.com",
        "password": "Password123!",
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201, response.text
    return payload


@pytest.fixture
def auth_headers(client: TestClient, registered_user: dict) -> dict:
    """Returns Bearer auth headers for the default test user."""
    response = client.post(
        "/api/v1/auth/login",
        data={
            "username": registered_user["email"],
            "password": registered_user["password"],
        },
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def created_org(client: TestClient, auth_headers: dict) -> dict:
    """Creates a test organization and returns the response JSON."""
    payload = {
        "name": "Test Corp",
        "slug": "test-corp",
        "description": "Integration test org",
    }
    response = client.post(
        "/api/v1/organizations", json=payload, headers=auth_headers
    )
    assert response.status_code == 201, response.text
    return response.json()
