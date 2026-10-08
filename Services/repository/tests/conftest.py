"""
conftest.py — Shared pytest fixtures for the Repository Service test suite.

Strategy:
  - Override DATABASE_URL with SQLite (in-memory) so tests never touch PostgreSQL.
  - Override GITHUB_APP_PRIVATE_KEY / GITHUB_APP_ID so security.py doesn't fail.
  - Use TestClient (synchronous) — same pattern as the api service.
  - Each test function gets a fresh DB session via function-scoped fixtures.
  - The memberships table is created and seeded here (simulating the api service's
    tables being present in the shared database).

Important: import `app.core.config` BEFORE importing `app.main` so the Settings
override takes effect before the engine is created.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# ── Override settings BEFORE importing the app ────────────────────────────────
from app.core.config import settings

settings.DATABASE_URL = "sqlite:///./test_repo.db"
settings.SECRET_KEY = "test-secret-key-for-repository-service"
settings.ALGORITHM = "HS256"
settings.GITHUB_APP_ID = "12345"
settings.GITHUB_APP_NAME = "forgeai-test"
settings.GITHUB_APP_PRIVATE_KEY = ""   # Not needed unless testing JWT generation
settings.GITHUB_WEBHOOK_SECRET = "test-webhook-secret"
settings.KAFKA_ENABLED = False

# ── Now import the app (settings already patched) ─────────────────────────────
from app.main import app
from app.db.base import Base
from app.db.database import get_db

# ── Test engine (SQLite in-memory via file for cross-session compatibility) ───
TEST_DB_URL = "sqlite:///./test_repo.db"
test_engine = create_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
)
TestSessionLocal = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)


def create_all_tables():
    """Creates all repository service tables AND the memberships table (api service)."""
    Base.metadata.create_all(bind=test_engine)

    # Create the memberships table that belongs to the api service.
    # In production this table is created by the api service; here we create it
    # manually so dependency.py can read it.
    with test_engine.connect() as conn:
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
        conn.commit()


def drop_all_tables():
    Base.metadata.drop_all(bind=test_engine)
    with test_engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS memberships"))
        conn.commit()


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    """Creates all tables once per test session."""
    create_all_tables()
    yield
    drop_all_tables()


@pytest.fixture
def db():
    """Provides a clean DB session for each test, rolled back after the test."""
    connection = test_engine.connect()
    transaction = connection.begin()
    session = TestSessionLocal(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db):
    """
    Provides a TestClient with the DB dependency overridden to use the test session.
    """
    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


# ── Auth token helper ─────────────────────────────────────────────────────────

def make_token(user_id: int) -> str:
    """Creates a test JWT token with the given user_id as the 'sub' claim."""
    from jose import jwt
    import time
    payload = {
        "sub": str(user_id),
        "exp": int(time.time()) + 3600,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def auth_headers(user_id: int) -> dict:
    """Returns Authorization headers for the given user."""
    return {"Authorization": f"Bearer {make_token(user_id)}"}


# ── Seed helpers ──────────────────────────────────────────────────────────────

def seed_membership(db, user_id: int, org_id: int, role: str = "owner") -> None:
    """Inserts a membership row so org membership checks pass."""
    db.execute(
        text(
            "INSERT OR IGNORE INTO memberships (user_id, organization_id, role, status) "
            "VALUES (:user_id, :org_id, :role, 'active')"
        ),
        {"user_id": user_id, "org_id": org_id, "role": role},
    )
    db.commit()


def seed_installation(db, org_id: int = 1, github_installation_id: int = 99999) -> "GitHubInstallation":
    """Creates a GitHubInstallation record for testing."""
    from app.models.github_installation import GitHubInstallation, InstallationStatus
    installation = GitHubInstallation(
        organization_id=org_id,
        github_installation_id=github_installation_id,
        github_account_id=111,
        github_account_login="test-org",
        account_type="Organization",
        status=InstallationStatus.ACTIVE.value,
    )
    db.add(installation)
    db.commit()
    db.refresh(installation)
    return installation


def seed_repository(db, org_id: int = 1, installation_id: int = 1) -> "Repository":
    """Creates a Repository record for testing."""
    from app.models.repository import Repository, RepositoryStatus
    repo = Repository(
        organization_id=org_id,
        github_installation_id=installation_id,
        github_repository_id="123456",
        name="test-repo",
        full_name="test-org/test-repo",
        owner="test-org",
        visibility="private",
        default_branch="main",
        status=RepositoryStatus.READY.value,
    )
    db.add(repo)
    db.commit()
    db.refresh(repo)
    return repo
