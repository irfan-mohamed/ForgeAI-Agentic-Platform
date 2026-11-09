"""
test_repo_map.py — Integration tests for repository map retrieval endpoint.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from app.models.repo_map import RepositoryMap
from app.models.repository import Repository, RepositoryStatus
from tests.conftest import auth_headers, seed_membership, seed_repository

USER_ID = 10
ORG_ID = 10


def test_get_repo_map_persisted(client, db):
    """Returns stored repository map when present."""
    seed_membership(db, USER_ID, ORG_ID)
    repo = seed_repository(db, org_id=ORG_ID)

    # Seed a RepositoryMap
    map_rec = RepositoryMap(
        organization_id=ORG_ID,
        repository_id=repo.id,
        commit_sha="abc1234",
        file_tree=[{"path": "app/main.py", "size": 1024, "language": "python", "type": "code"}],
        languages={"python": {"files": 1, "bytes": 1024}},
        symbols_summary=[{"name": "app", "type": "variable", "file_path": "app/main.py"}],
        imports=[],
        routes=[{"symbol_name": "GET /ping", "file_path": "app/main.py"}],
        test_files=["tests/test_main.py"],
        doc_files=["README.md"],
        raw_markdown="# Repository Map: Test\n- GET /ping",
    )
    db.add(map_rec)
    db.commit()

    resp = client.get(
        f"/api/v1/internal/organizations/{ORG_ID}/repositories/{repo.id}/repo-map",
        headers=auth_headers(USER_ID),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["repository_id"] == repo.id
    assert data["commit_sha"] == "abc1234"
    assert "GET /ping" in data["raw_markdown"]
    assert len(data["file_tree"]) == 1
    assert data["languages"]["python"]["files"] == 1


def test_get_repo_map_fallback_when_empty(client, db):
    """Returns fallback structure when repository map has not been explicitly created."""
    seed_membership(db, USER_ID, ORG_ID)
    repo = seed_repository(db, org_id=ORG_ID)

    resp = client.get(
        f"/api/v1/internal/organizations/{ORG_ID}/repositories/{repo.id}/repo-map",
        headers=auth_headers(USER_ID),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["repository_id"] == repo.id
    assert data["file_tree"] == []
    assert "Repository Map" in data["raw_markdown"]


def test_get_repo_map_non_member_forbidden(client, db):
    """Non-members cannot access the repo map."""
    repo = seed_repository(db, org_id=ORG_ID)

    resp = client.get(
        f"/api/v1/internal/organizations/{ORG_ID}/repositories/{repo.id}/repo-map",
        headers=auth_headers(999),  # Other user
    )
    assert resp.status_code == 403

