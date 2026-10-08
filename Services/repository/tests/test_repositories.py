"""
test_repositories.py — Integration tests for repository management endpoints.

Tests cover:
  - Connecting a repository (happy path + error cases)
  - Listing connected repositories
  - Getting a single repository
  - Requesting a sync
  - Getting sync status
  - Disconnecting a repository
  - Tenant isolation (user cannot see another org's repos)
"""

from unittest.mock import patch

import pytest

from tests.conftest import auth_headers, seed_installation, seed_membership, seed_repository

USER_ID = 1
ORG_ID = 1
OTHER_ORG_ID = 99
OTHER_USER_ID = 2


# ── Helper: mock GitHub API calls ─────────────────────────────────────────────

MOCK_REPO_META = {
    "id": 123456,
    "name": "test-repo",
    "full_name": "test-org/test-repo",
    "owner": {"login": "test-org"},
    "private": True,
    "default_branch": "main",
    "description": "A test repository",
}


def _mock_github_services():
    """Context manager that stubs out all GitHub API calls."""
    return patch.multiple(
        "app.services.github_service",
        get_installation_access_token=lambda github_installation_id: "fake-token",
        get_repository_metadata=lambda token, repo_id: MOCK_REPO_META,
        list_installation_repositories=lambda token: [],
    )


# ── Connect Repository ────────────────────────────────────────────────────────

class TestConnectRepository:

    def test_connect_success(self, client, db):
        """A member can connect a repository that isn't already connected."""
        seed_membership(db, USER_ID, ORG_ID)
        install = seed_installation(db, org_id=ORG_ID)

        with _mock_github_services():
            response = client.post(
                f"/api/v1/organizations/{ORG_ID}/repositories",
                json={"github_repository_id": "123456"},
                headers=auth_headers(USER_ID),
            )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "test-repo"
        assert data["full_name"] == "test-org/test-repo"
        assert data["status"] == "connecting"
        assert data["organization_id"] == ORG_ID

    def test_connect_duplicate_returns_409(self, client, db):
        """Connecting the same repository twice in the same org raises 409."""
        seed_membership(db, USER_ID, ORG_ID)
        install = seed_installation(db, org_id=ORG_ID)
        seed_repository(db, org_id=ORG_ID, installation_id=install.id)

        with _mock_github_services():
            response = client.post(
                f"/api/v1/organizations/{ORG_ID}/repositories",
                json={"github_repository_id": "123456"},
                headers=auth_headers(USER_ID),
            )

        assert response.status_code == 409

    def test_connect_no_github_installation_returns_404(self, client, db):
        """Connecting a repo without a GitHub installation raises 404."""
        seed_membership(db, USER_ID, ORG_ID)
        # No installation seeded.

        response = client.post(
            f"/api/v1/organizations/{ORG_ID}/repositories",
            json={"github_repository_id": "999"},
            headers=auth_headers(USER_ID),
        )

        assert response.status_code == 404

    def test_connect_non_member_returns_403(self, client, db):
        """A user who is not a member of the org gets 403."""
        # USER_ID has no membership in ORG_ID.
        response = client.post(
            f"/api/v1/organizations/{ORG_ID}/repositories",
            json={"github_repository_id": "123456"},
            headers=auth_headers(USER_ID),
        )
        assert response.status_code == 403

    def test_connect_unauthenticated_returns_401(self, client, db):
        """Request without a token returns 401."""
        response = client.post(
            f"/api/v1/organizations/{ORG_ID}/repositories",
            json={"github_repository_id": "123456"},
        )
        assert response.status_code == 401


# ── List Repositories ─────────────────────────────────────────────────────────

class TestListRepositories:

    def test_list_returns_org_repos(self, client, db):
        """Returns only repos that belong to the user's organization."""
        seed_membership(db, USER_ID, ORG_ID)
        install = seed_installation(db, org_id=ORG_ID)
        seed_repository(db, org_id=ORG_ID, installation_id=install.id)

        response = client.get(
            f"/api/v1/organizations/{ORG_ID}/repositories",
            headers=auth_headers(USER_ID),
        )

        assert response.status_code == 200
        data = response.json()
        assert "repositories" in data
        assert len(data["repositories"]) == 1
        assert data["repositories"][0]["organization_id"] == ORG_ID

    def test_list_does_not_return_other_org_repos(self, client, db):
        """User can only see repos from their own org — not from other orgs."""
        # User belongs to ORG_ID only.
        seed_membership(db, USER_ID, ORG_ID)
        # Seed a repo in a DIFFERENT org.
        install_other = seed_installation(db, org_id=OTHER_ORG_ID, github_installation_id=77777)
        seed_repository(db, org_id=OTHER_ORG_ID, installation_id=install_other.id)

        response = client.get(
            f"/api/v1/organizations/{ORG_ID}/repositories",
            headers=auth_headers(USER_ID),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["repositories"] == []  # User's org has no repos.

    def test_list_non_member_returns_403(self, client, db):
        response = client.get(
            f"/api/v1/organizations/{ORG_ID}/repositories",
            headers=auth_headers(USER_ID),
        )
        assert response.status_code == 403


# ── Get Repository ────────────────────────────────────────────────────────────

class TestGetRepository:

    def test_get_repository_success(self, client, db):
        """Member can fetch their organization's repository by ID."""
        seed_membership(db, USER_ID, ORG_ID)
        install = seed_installation(db, org_id=ORG_ID)
        repo = seed_repository(db, org_id=ORG_ID, installation_id=install.id)

        response = client.get(
            f"/api/v1/repositories/{repo.id}",
            headers=auth_headers(USER_ID),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == repo.id
        assert data["name"] == "test-repo"

    def test_get_repository_wrong_org_returns_404(self, client, db):
        """A user cannot see a repository that belongs to a different org."""
        # USER_ID belongs to ORG_ID, but the repo is in OTHER_ORG_ID.
        seed_membership(db, USER_ID, ORG_ID)
        install_other = seed_installation(db, org_id=OTHER_ORG_ID, github_installation_id=55555)
        repo = seed_repository(db, org_id=OTHER_ORG_ID, installation_id=install_other.id)

        response = client.get(
            f"/api/v1/repositories/{repo.id}",
            headers=auth_headers(USER_ID),
        )

        assert response.status_code == 404

    def test_get_nonexistent_repository_returns_404(self, client, db):
        seed_membership(db, USER_ID, ORG_ID)

        response = client.get(
            "/api/v1/repositories/99999",
            headers=auth_headers(USER_ID),
        )

        assert response.status_code == 404


# ── Sync ──────────────────────────────────────────────────────────────────────

class TestRequestSync:

    def test_request_sync_success(self, client, db):
        """A member can trigger a manual sync for a READY repository."""
        seed_membership(db, USER_ID, ORG_ID)
        install = seed_installation(db, org_id=ORG_ID)
        repo = seed_repository(db, org_id=ORG_ID, installation_id=install.id)

        response = client.post(
            f"/api/v1/repositories/{repo.id}/sync",
            headers=auth_headers(USER_ID),
        )

        assert response.status_code == 202
        data = response.json()
        assert data["repository_id"] == repo.id
        assert data["status"] == "queued"
        assert data["trigger"] == "manual"

    def test_request_sync_duplicate_returns_409(self, client, db):
        """Requesting sync when one is already queued returns 409."""
        seed_membership(db, USER_ID, ORG_ID)
        install = seed_installation(db, org_id=ORG_ID)
        repo = seed_repository(db, org_id=ORG_ID, installation_id=install.id)

        # First sync request.
        client.post(f"/api/v1/repositories/{repo.id}/sync", headers=auth_headers(USER_ID))

        # Second sync request while first is still queued.
        response = client.post(
            f"/api/v1/repositories/{repo.id}/sync",
            headers=auth_headers(USER_ID),
        )

        assert response.status_code == 409


class TestGetSyncStatus:

    def test_get_sync_status_success(self, client, db):
        """Returns the latest sync record with progress details."""
        seed_membership(db, USER_ID, ORG_ID)
        install = seed_installation(db, org_id=ORG_ID)
        repo = seed_repository(db, org_id=ORG_ID, installation_id=install.id)

        # Create a sync by requesting one.
        client.post(f"/api/v1/repositories/{repo.id}/sync", headers=auth_headers(USER_ID))

        response = client.get(
            f"/api/v1/repositories/{repo.id}/sync/status",
            headers=auth_headers(USER_ID),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["repository_id"] == repo.id
        assert "progress" in data
        assert "files_discovered" in data["progress"]

    def test_get_sync_status_no_sync_returns_404(self, client, db):
        """Repo with no syncs returns 404 on status endpoint."""
        seed_membership(db, USER_ID, ORG_ID)
        install = seed_installation(db, org_id=ORG_ID)
        repo = seed_repository(db, org_id=ORG_ID, installation_id=install.id)

        response = client.get(
            f"/api/v1/repositories/{repo.id}/sync/status",
            headers=auth_headers(USER_ID),
        )

        assert response.status_code == 404


# ── Disconnect Repository ─────────────────────────────────────────────────────

class TestDisconnectRepository:

    def test_disconnect_success(self, client, db):
        """A member can disconnect a repository — returns 204."""
        seed_membership(db, USER_ID, ORG_ID)
        install = seed_installation(db, org_id=ORG_ID)
        repo = seed_repository(db, org_id=ORG_ID, installation_id=install.id)

        response = client.delete(
            f"/api/v1/repositories/{repo.id}",
            headers=auth_headers(USER_ID),
        )

        assert response.status_code == 204

    def test_disconnect_hides_repo_from_list(self, client, db):
        """After disconnect, repo no longer appears in the list."""
        seed_membership(db, USER_ID, ORG_ID)
        install = seed_installation(db, org_id=ORG_ID)
        repo = seed_repository(db, org_id=ORG_ID, installation_id=install.id)

        # Disconnect.
        client.delete(f"/api/v1/repositories/{repo.id}", headers=auth_headers(USER_ID))

        # Verify it's gone from the list.
        list_response = client.get(
            f"/api/v1/organizations/{ORG_ID}/repositories",
            headers=auth_headers(USER_ID),
        )
        repos = list_response.json()["repositories"]
        assert all(r["id"] != repo.id for r in repos)

    def test_disconnect_wrong_org_returns_404(self, client, db):
        """Cannot disconnect a repository that belongs to a different org."""
        seed_membership(db, USER_ID, ORG_ID)
        install_other = seed_installation(db, org_id=OTHER_ORG_ID, github_installation_id=44444)
        repo = seed_repository(db, org_id=OTHER_ORG_ID, installation_id=install_other.id)

        response = client.delete(
            f"/api/v1/repositories/{repo.id}",
            headers=auth_headers(USER_ID),
        )

        assert response.status_code == 404
