"""
test_repo_map_builder.py — Tests for the worker's repo map builder service.
"""
from __future__ import annotations

import pytest

from app.models.code_relationship import CodeRelationship
from app.models.code_symbol import CodeSymbol
from app.models.repo_map import RepositoryMap
from app.models.repository_file import RepositoryFile
from app.services.repo_map_builder import (
    build_repo_map,
    generate_repo_map_markdown,
    is_doc_file,
    is_test_file,
)


def test_is_test_file_patterns():
    """Verify test file path matching."""
    assert is_test_file("tests/test_auth.py") is True
    assert is_test_file("app/test_service.py") is True
    assert is_test_file("src/components/button.spec.tsx") is True
    assert is_test_file("__tests__/login.test.js") is True
    assert is_test_file("app/services/auth.py") is False


def test_is_doc_file_patterns():
    """Verify doc file path matching."""
    assert is_doc_file("README.md") is True
    assert is_doc_file("docs/architecture.md") is True
    assert is_doc_file(".github/PULL_REQUEST_TEMPLATE.md") is True
    assert is_doc_file("src/main.py") is False


def test_build_repo_map_aggregates_data(db):
    """Verify build_repo_map creates and persists a RepositoryMap record."""
    org_id = 1
    repo_id = 99

    # Seed files
    f1 = RepositoryFile(
        organization_id=org_id,
        repository_id=repo_id,
        path="app/main.py",
        language="python",
        file_type="code",
        size_bytes=1500,
        content_checksum="chk1",
        is_indexed=True,
        status="indexed",
    )
    db.add(f1)
    db.add(
        RepositoryFile(
            organization_id=org_id,
            repository_id=repo_id,
            path="tests/test_main.py",
            language="python",
            file_type="test",
            size_bytes=800,
            content_checksum="chk2",
            is_indexed=True,
            status="indexed",
        )
    )
    db.add(
        RepositoryFile(
            organization_id=org_id,
            repository_id=repo_id,
            path="README.md",
            language="markdown",
            file_type="doc",
            size_bytes=500,
            content_checksum="chk3",
            is_indexed=False,
            status="skipped",
        )
    )
    db.flush()

    # Seed symbol and route
    sym = CodeSymbol(
        id=1,
        organization_id=org_id,
        repository_id=repo_id,
        repository_file_id=f1.id,
        file_path="app/main.py",
        symbol_name="ping_handler",
        qualified_name="app.main.ping_handler",
        symbol_type="function",
        start_line=10,
        end_line=15,
        language="python",
        signature="def ping_handler() -> dict:",
        is_async=False,
        is_exported=True,
    )
    db.add(sym)
    db.flush()

    route = CodeSymbol(
        id=2,
        organization_id=org_id,
        repository_id=repo_id,
        repository_file_id=f1.id,
        file_path="app/main.py",
        symbol_name="GET /ping",
        qualified_name="app.main.GET /ping",
        symbol_type="route",
        start_line=9,
        end_line=15,
        language="python",
        signature="@app.get('/ping')",
        is_async=False,
        is_exported=True,
    )

    db.add(route)
    db.flush()

    # Route handles relationship
    db.add(
        CodeRelationship(
            id=1,
            organization_id=org_id,
            repository_id=repo_id,
            source_symbol_id=route.id,
            target_symbol_id=sym.id,
            relationship_type="HANDLES",
            source_file_path="app/main.py",
            target_file_path="app/main.py",
            source_line=9,
        )
    )
    db.commit()

    # Run build_repo_map
    map_rec = build_repo_map(
        db=db,
        organization_id=org_id,
        repository_id=repo_id,
        commit_sha="commit-123",
        repo_name="acme/my-service",
    )

    assert map_rec.repository_id == repo_id
    assert map_rec.commit_sha == "commit-123"
    assert len(map_rec.file_tree) == 3
    assert "python" in map_rec.languages
    assert "tests/test_main.py" in map_rec.test_files
    assert "README.md" in map_rec.doc_files
    assert len(map_rec.routes) == 1
    assert map_rec.routes[0]["symbol_name"] == "GET /ping"
    assert map_rec.routes[0]["handler_name"] == "ping_handler"
    assert "acme/my-service" in map_rec.raw_markdown
    assert "GET /ping" in map_rec.raw_markdown
