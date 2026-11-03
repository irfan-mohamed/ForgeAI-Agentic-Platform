"""
Tests for the pull request endpoints.

GitHub is never called: the github_service functions are monkeypatched.
"""
from app.services import github_service
from tests.conftest import (
    auth_headers,
    seed_installation,
    seed_membership,
    seed_repository,
)

RAW_PR = {
    "number": 7,
    "title": "Add retry logic",
    "state": "closed",
    "merged_at": "2026-10-01T10:00:00Z",
    "draft": False,
    "user": {"login": "dev"},
    "head": {"ref": "feat/retry", "sha": "abc123"},
    "base": {"ref": "main"},
    "html_url": "https://github.com/test-org/test-repo/pull/7",
    "created_at": "2026-09-30T10:00:00Z",
    "updated_at": "2026-10-01T10:00:00Z",
    "body": "Adds retries.",
    "additions": 12,
    "deletions": 3,
    "changed_files": 2,
}

RAW_FILES = [
    {"filename": "src/pay.py", "status": "modified", "additions": 10, "deletions": 3, "patch": "@@ -1 +1 @@"},
    {"filename": "logo.png", "status": "added", "additions": 0, "deletions": 0},
]


def _setup(db, user_id=1, org_id=1):
    seed_membership(db, user_id, org_id)
    installation = seed_installation(db, org_id=org_id)
    return seed_repository(db, org_id=org_id, installation_id=installation.id)


def _patch_github(monkeypatch):
    monkeypatch.setattr(github_service, "get_installation_access_token", lambda _id: "token")
    monkeypatch.setattr(github_service, "list_pull_requests", lambda *a, **k: [RAW_PR])
    monkeypatch.setattr(github_service, "get_pull_request", lambda *a, **k: RAW_PR)
    monkeypatch.setattr(
        github_service, "list_pull_request_files", lambda *a, **k: (RAW_FILES, False)
    )


def test_list_pull_requests(client, db, monkeypatch):
    repo = _setup(db)
    _patch_github(monkeypatch)

    response = client.get(
        f"/api/v1/repositories/{repo.id}/pull-requests", headers=auth_headers(1)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["page"] == 1
    pr = body["pull_requests"][0]
    assert pr["number"] == 7
    assert pr["state"] == "merged"  # merged_at wins over GitHub's "closed"
    assert pr["author"] == "dev"
    assert pr["source_branch"] == "feat/retry"
    assert pr["target_branch"] == "main"


def test_get_pull_request_includes_files(client, db, monkeypatch):
    repo = _setup(db)
    _patch_github(monkeypatch)

    response = client.get(
        f"/api/v1/repositories/{repo.id}/pull-requests/7", headers=auth_headers(1)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["number"] == 7
    assert body["body"] == "Adds retries."
    assert body["changed_files"] == 2
    assert body["files_truncated"] is False
    assert body["files"][0]["patch"] == "@@ -1 +1 @@"
    assert body["files"][1]["patch"] is None


def test_non_member_gets_404(client, db, monkeypatch):
    repo = _setup(db, user_id=1, org_id=1)
    _patch_github(monkeypatch)

    # User 2 belongs to a different organization only.
    seed_membership(db, 2, 99)

    response = client.get(
        f"/api/v1/repositories/{repo.id}/pull-requests", headers=auth_headers(2)
    )

    assert response.status_code == 404


def test_unknown_pull_request_returns_404(client, db, monkeypatch):
    repo = _setup(db)
    monkeypatch.setattr(github_service, "get_installation_access_token", lambda _id: "token")

    def _missing(*_args, **_kwargs):
        raise github_service.GitHubNotFoundError("missing")

    monkeypatch.setattr(github_service, "get_pull_request", _missing)

    response = client.get(
        f"/api/v1/repositories/{repo.id}/pull-requests/999", headers=auth_headers(1)
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Pull request not found."


def test_github_failure_returns_502(client, db, monkeypatch):
    repo = _setup(db)
    monkeypatch.setattr(github_service, "get_installation_access_token", lambda _id: "token")

    def _boom(*_args, **_kwargs):
        raise RuntimeError("GitHub is down")

    monkeypatch.setattr(github_service, "list_pull_requests", _boom)

    response = client.get(
        f"/api/v1/repositories/{repo.id}/pull-requests", headers=auth_headers(1)
    )

    assert response.status_code == 502


def test_requires_authentication(client):
    response = client.get("/api/v1/repositories/1/pull-requests")

    assert response.status_code == 401
