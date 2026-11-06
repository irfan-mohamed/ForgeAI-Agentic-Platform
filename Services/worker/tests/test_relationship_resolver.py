"""
test_relationship_resolver.py — Unit tests for the cross-file relationship resolver.

All tests are fully offline — no Kafka, no Qdrant, no GitHub.

Test strategy:
    - Unit tests for _SymbolMap helpers (TestResolveByFileAndName, TestResolveByName)
      use pure in-memory Python objects — zero DB interaction.
    - DB tests (TestBuildSymbolMap, TestResolveRelationshipsIntegration)
      use raw SQLite INSERT statements so BigInteger PK autoincrement is not
      an issue (SQLite needs INTEGER affinity for rowid autoincrement).
    - Integration tests mock get_db_session so the resolver uses our test
      SQLite session transparently.
"""

from __future__ import annotations

import pytest
from contextlib import contextmanager
from unittest.mock import patch

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
import app.models  # noqa: F401 — registers all models

from app.services.relationship_resolver import (
    _build_symbol_map,
    _resolve_by_file_and_name,
    _resolve_by_name,
    _SymbolMap,
    get_resolution_stats,
    resolve_relationships,
)


# ── SQLite fixture ────────────────────────────────────────────────────────────

# Manually create tables using Integer PK for SQLite compatibility
# (BigInteger doesn't get autoincrement in SQLite without INTEGER affinity)
_CREATE_SYMBOLS = """
CREATE TABLE IF NOT EXISTS code_symbols (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    organization_id  INTEGER NOT NULL,
    repository_id    INTEGER NOT NULL,
    repository_file_id INTEGER NOT NULL DEFAULT 1,
    commit_sha  TEXT,
    file_path   TEXT NOT NULL,
    symbol_name TEXT NOT NULL,
    qualified_name TEXT,
    symbol_type TEXT NOT NULL DEFAULT 'function',
    language    TEXT,
    start_line  INTEGER,
    end_line    INTEGER,
    signature   TEXT,
    docstring   TEXT,
    is_exported INTEGER NOT NULL DEFAULT 0,
    is_async    INTEGER NOT NULL DEFAULT 0,
    parent_symbol_id INTEGER,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
)
"""

_CREATE_RELATIONSHIPS = """
CREATE TABLE IF NOT EXISTS code_relationships (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    organization_id  INTEGER NOT NULL,
    repository_id    INTEGER NOT NULL,
    commit_sha  TEXT,
    source_symbol_id INTEGER,
    source_file_path TEXT NOT NULL,
    source_line INTEGER,
    target_symbol_id INTEGER,
    target_file_path TEXT,
    target_symbol_name TEXT,
    relationship_type TEXT NOT NULL,
    confidence  INTEGER NOT NULL DEFAULT 100,
    is_resolved INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
)
"""


@pytest.fixture
def engine():
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    with eng.connect() as conn:
        conn.execute(text(_CREATE_SYMBOLS))
        conn.execute(text(_CREATE_RELATIONSHIPS))
        conn.commit()
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine) -> Session:
    SessionFactory = sessionmaker(bind=engine)
    session = SessionFactory()
    yield session
    session.close()


# ── Raw insert helpers ────────────────────────────────────────────────────────

def _insert_symbol(
    db: Session,
    *,
    org_id: int = 1,
    repo_id: int = 10,
    file_path: str = "app/auth.py",
    symbol_name: str = "login",
    symbol_type: str = "function",
    qualified_name: str | None = None,
    language: str = "python",
) -> int:
    """Insert a symbol row using raw SQL and return its auto-generated id."""
    result = db.execute(
        text("""
            INSERT INTO code_symbols
                (organization_id, repository_id, file_path, symbol_name,
                 symbol_type, qualified_name, language, start_line, end_line)
            VALUES
                (:org, :repo, :path, :name, :stype, :qname, :lang, 1, 10)
        """),
        {
            "org": org_id,
            "repo": repo_id,
            "path": file_path,
            "name": symbol_name,
            "stype": symbol_type,
            "qname": qualified_name or symbol_name,
            "lang": language,
        },
    )
    db.commit()
    return result.lastrowid


def _insert_relationship(
    db: Session,
    *,
    org_id: int = 1,
    repo_id: int = 10,
    source_symbol_id: int | None = None,
    source_file: str = "app/routes.py",
    source_line: int = 5,
    target_name: str = "login",
    target_file: str | None = None,
    target_symbol_id: int | None = None,
    rel_type: str = "CALLS",
    is_resolved: bool = False,
) -> int:
    result = db.execute(
        text("""
            INSERT INTO code_relationships
                (organization_id, repository_id, source_symbol_id, source_file_path,
                 source_line, target_symbol_name, target_file_path,
                 target_symbol_id, relationship_type, confidence, is_resolved)
            VALUES
                (:org, :repo, :src_id, :src_file, :src_line,
                 :tgt_name, :tgt_file, :tgt_sym_id, :rel_type, 75, :resolved)
        """),
        {
            "org": org_id,
            "repo": repo_id,
            "src_id": source_symbol_id,
            "src_file": source_file,
            "src_line": source_line,
            "tgt_name": target_name,
            "tgt_file": target_file,
            "tgt_sym_id": target_symbol_id,
            "rel_type": rel_type,
            "resolved": 1 if is_resolved else 0,
        },
    )
    db.commit()
    return result.lastrowid


def _get_relationship(db: Session, rel_id: int) -> dict:
    row = db.execute(
        text("SELECT * FROM code_relationships WHERE id = :id"),
        {"id": rel_id},
    ).fetchone()
    return dict(row._mapping) if row else {}


# ── _build_symbol_map tests ───────────────────────────────────────────────────

class TestBuildSymbolMap:
    def test_populates_by_name(self, db: Session):
        sym_id = _insert_symbol(db, symbol_name="authenticate")
        sym_map = _build_symbol_map(db, repo_id=10)
        assert "authenticate" in sym_map.by_name
        assert sym_id in sym_map.by_name["authenticate"]

    def test_populates_by_file_and_name(self, db: Session):
        _insert_symbol(db, file_path="app/auth.py", symbol_name="verify_token")
        sym_map = _build_symbol_map(db, repo_id=10)
        assert ("app/auth.py", "verify_token") in sym_map.by_file_and_name

    def test_populates_by_qualified_name(self, db: Session):
        sym_id = _insert_symbol(
            db, symbol_name="login", qualified_name="UserService.login", file_path="service.py"
        )
        sym_map = _build_symbol_map(db, repo_id=10)
        assert "UserService.login" in sym_map.by_qualified_name
        assert sym_map.by_qualified_name["UserService.login"] == sym_id

    def test_empty_repo_returns_empty_map(self, db: Session):
        sym_map = _build_symbol_map(db, repo_id=9999)
        assert len(sym_map.by_name) == 0

    def test_multiple_symbols_same_name(self, db: Session):
        _insert_symbol(db, symbol_name="validate", file_path="a.py")
        _insert_symbol(db, symbol_name="validate", file_path="b.py")
        sym_map = _build_symbol_map(db, repo_id=10)
        assert len(sym_map.by_name["validate"]) == 2

    def test_correct_repo_isolation(self, db: Session):
        _insert_symbol(db, symbol_name="secret", repo_id=99)
        sym_map = _build_symbol_map(db, repo_id=10)
        assert "secret" not in sym_map.by_name


# ── _resolve_by_file_and_name tests ──────────────────────────────────────────

class TestResolveByFileAndName:
    def setup_method(self):
        self.sym_map = _SymbolMap()
        self.sym_map.by_file_and_name = {
            ("app/auth.py", "login"): 42,
            ("app/user.py", "get_user"): 99,
        }

    def test_exact_match(self):
        result = _resolve_by_file_and_name(self.sym_map, "login", "app/auth.py")
        assert result == 42

    def test_no_match_wrong_file(self):
        result = _resolve_by_file_and_name(self.sym_map, "login", "app/routes.py")
        assert result is None

    def test_no_match_wrong_name(self):
        result = _resolve_by_file_and_name(self.sym_map, "logout", "app/auth.py")
        assert result is None

    def test_none_target_name(self):
        result = _resolve_by_file_and_name(self.sym_map, None, "app/auth.py")
        assert result is None

    def test_none_target_file(self):
        result = _resolve_by_file_and_name(self.sym_map, "login", None)
        assert result is None

    def test_ts_extension_fallback(self):
        """JS/TS imports often omit the file extension."""
        self.sym_map.by_file_and_name[("src/auth.ts", "AuthService")] = 77
        result = _resolve_by_file_and_name(self.sym_map, "AuthService", "src/auth")
        assert result == 77

    def test_js_extension_fallback(self):
        self.sym_map.by_file_and_name[("src/utils.js", "formatDate")] = 88
        result = _resolve_by_file_and_name(self.sym_map, "formatDate", "src/utils")
        assert result == 88

    def test_index_ts_fallback(self):
        """Barrel imports: import ... from './auth' → ./auth/index.ts"""
        self.sym_map.by_file_and_name[("src/auth/index.ts", "AuthService")] = 55
        result = _resolve_by_file_and_name(self.sym_map, "AuthService", "src/auth")
        assert result == 55


# ── _resolve_by_name tests ────────────────────────────────────────────────────

class TestResolveByName:
    def setup_method(self):
        self.sym_map = _SymbolMap()
        self.sym_map.by_name = {
            "login": [10],
            "get_user": [20, 30],
        }
        self.sym_map.by_qualified_name = {
            "UserService.login": 10,
        }

    def test_simple_name_match(self):
        assert _resolve_by_name(self.sym_map, "login") == 10

    def test_qualified_name_match(self):
        assert _resolve_by_name(self.sym_map, "UserService.login") == 10

    def test_ambiguous_returns_first(self):
        assert _resolve_by_name(self.sym_map, "get_user") == 20

    def test_dotted_name_last_segment(self):
        assert _resolve_by_name(self.sym_map, "auth.login") == 10

    def test_no_match(self):
        assert _resolve_by_name(self.sym_map, "nonexistent_xyz") is None

    def test_none_input(self):
        assert _resolve_by_name(self.sym_map, None) is None

    def test_empty_string(self):
        assert _resolve_by_name(self.sym_map, "") is None


# ── Integration: full resolve_relationships pass ──────────────────────────────

class TestResolveRelationshipsIntegration:
    """Tests the full resolver pipeline with mocked DB session."""

    def _make_mock_session(self, db: Session):
        @contextmanager
        def mock_get_db():
            yield db
        return mock_get_db

    def test_resolves_call_within_repo(self, db: Session):
        """A CALLS relationship targeting an existing symbol gets resolved."""
        login_sym_id = _insert_symbol(db, symbol_name="login", file_path="app/auth.py", repo_id=10)
        rel_id = _insert_relationship(
            db, target_name="login", target_file="app/auth.py", rel_type="CALLS", is_resolved=False
        )

        with patch(
            "app.services.relationship_resolver.get_db_session",
            self._make_mock_session(db),
        ):
            stats = resolve_relationships(repository_id=10, organization_id=1)

        row = _get_relationship(db, rel_id)
        assert row["is_resolved"] == 1
        assert row["target_symbol_id"] == login_sym_id
        assert stats["resolved"] >= 1

    def test_skips_already_resolved(self, db: Session):
        """is_resolved=True rows are not re-processed."""
        sym_id = _insert_symbol(db, symbol_name="existing", file_path="x.py", repo_id=10)
        rel_id = _insert_relationship(
            db,
            target_name="existing",
            target_symbol_id=sym_id,
            rel_type="CALLS",
            is_resolved=True,
        )

        with patch(
            "app.services.relationship_resolver.get_db_session",
            self._make_mock_session(db),
        ):
            stats = resolve_relationships(repository_id=10, organization_id=1)

        row = _get_relationship(db, rel_id)
        # Row was already resolved — should remain so
        assert row["is_resolved"] == 1
        assert row["target_symbol_id"] == sym_id

    def test_unresolvable_stays_unresolved(self, db: Session):
        """Calls to non-existent symbols stay unresolved.

        We insert a dummy symbol so the resolver enters its resolution loop
        (it skips entirely if no symbols exist in the repo at all).
        """
        # Ensure at least one symbol exists so the loop runs
        _insert_symbol(db, symbol_name="dummy_symbol", file_path="dummy.py", repo_id=10)
        rel_id = _insert_relationship(
            db,
            target_name="no_such_function_xyz_abc",
            rel_type="CALLS",
            is_resolved=False,
        )

        with patch(
            "app.services.relationship_resolver.get_db_session",
            self._make_mock_session(db),
        ):
            stats = resolve_relationships(repository_id=10, organization_id=1)

        row = _get_relationship(db, rel_id)
        assert row["is_resolved"] == 0
        assert row["target_symbol_id"] is None
        assert stats["unresolved"] >= 1

    def test_resolves_by_name_when_file_unmatched(self, db: Session):
        """Name-only resolution used when file path doesn't match exactly."""
        sym_id = _insert_symbol(db, symbol_name="verify_token", file_path="app/tokens.py", repo_id=10)
        rel_id = _insert_relationship(
            db,
            target_name="verify_token",
            target_file="app/WRONG_PATH.py",  # Wrong path → falls back to name-only
            rel_type="CALLS",
            is_resolved=False,
        )

        with patch(
            "app.services.relationship_resolver.get_db_session",
            self._make_mock_session(db),
        ):
            stats = resolve_relationships(repository_id=10, organization_id=1)

        row = _get_relationship(db, rel_id)
        assert row["is_resolved"] == 1
        assert row["target_symbol_id"] == sym_id

    def test_get_resolution_stats(self, db: Session):
        """get_resolution_stats returns correct breakdown."""
        sym_id = _insert_symbol(db, symbol_name="handler", file_path="api.py", repo_id=10)
        _insert_relationship(
            db,
            target_name="handler",
            target_symbol_id=sym_id,
            rel_type="HANDLES",
            is_resolved=True,
        )
        _insert_relationship(
            db,
            target_name="missing_fn",
            rel_type="CALLS",
            is_resolved=False,
        )

        with patch(
            "app.services.relationship_resolver.get_db_session",
            self._make_mock_session(db),
        ):
            stats = get_resolution_stats(repository_id=10)

        assert stats["total"] >= 2
        assert stats["resolved"] >= 1
        assert stats["unresolved"] >= 1
        assert stats["resolved"] + stats["unresolved"] == stats["total"]
