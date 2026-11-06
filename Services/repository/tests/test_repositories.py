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


# ── Reconnect Repository ──────────────────────────────────────────────────────

class TestReconnectRepository:

    def test_reconnect_disconnected_repository_success(self, client, db):
        """Reconnecting a previously disconnected repository reactivates it instead of failing."""
        seed_membership(db, USER_ID, ORG_ID)
        install = seed_installation(db, org_id=ORG_ID)

        # 1. First connection
        with _mock_github_services():
            res1 = client.post(
                f"/api/v1/organizations/{ORG_ID}/repositories",
                json={"github_repository_id": "123456"},
                headers=auth_headers(USER_ID),
            )
        assert res1.status_code == 201
        repo_id = res1.json()["id"]

        # 2. Disconnect
        res_del = client.delete(
            f"/api/v1/repositories/{repo_id}",
            headers=auth_headers(USER_ID),
        )
        assert res_del.status_code == 204

        # Verify it is disconnected in DB
        from app.models.repository import Repository, RepositoryStatus
        repo_in_db = db.get(Repository, repo_id)
        assert repo_in_db.status == RepositoryStatus.DISCONNECTED.value

        # 3. Reconnect the same repository
        with _mock_github_services():
            res2 = client.post(
                f"/api/v1/organizations/{ORG_ID}/repositories",
                json={"github_repository_id": "123456"},
                headers=auth_headers(USER_ID),
            )
        assert res2.status_code == 201
        data = res2.json()
        assert data["id"] == repo_id, "Must reactivate the existing repository record"
        assert data["status"] == "connecting"

        # Verify database has exactly 1 repository record for this repo
        all_repos = (
            db.query(Repository)
            .filter(
                Repository.organization_id == ORG_ID,
                Repository.github_repository_id == "123456",
            )
            .all()
        )
        assert len(all_repos) == 1, "Must not create duplicate repository records"

    def test_reconnect_with_different_installation(self, client, db):
        """Reconnecting through a different/new GitHub installation updates the installation ID."""
        seed_membership(db, USER_ID, ORG_ID)
        install1 = seed_installation(db, org_id=ORG_ID, github_installation_id=1111)

        # 1. Connect
        with _mock_github_services():
            res1 = client.post(
                f"/api/v1/organizations/{ORG_ID}/repositories",
                json={"github_repository_id": "123456"},
                headers=auth_headers(USER_ID),
            )
        assert res1.status_code == 201
        repo_id = res1.json()["id"]

        # 2. Disconnect
        client.delete(f"/api/v1/repositories/{repo_id}", headers=auth_headers(USER_ID))

        # 3. Revoke install1 and seed active install2
        from app.models.github_installation import GitHubInstallation, InstallationStatus
        inst1_record = db.get(GitHubInstallation, install1.id)
        inst1_record.status = InstallationStatus.REVOKED.value
        db.commit()

        install2 = seed_installation(db, org_id=ORG_ID, github_installation_id=2222)

        # 4. Reconnect
        with _mock_github_services():
            res2 = client.post(
                f"/api/v1/organizations/{ORG_ID}/repositories",
                json={"github_repository_id": "123456"},
                headers=auth_headers(USER_ID),
            )
        assert res2.status_code == 201
        from app.models.repository import Repository
        repo_in_db = db.get(Repository, repo_id)
        assert repo_in_db.github_installation_id == install2.id, "GitHub installation ID must be updated"

    def test_reconnect_preserves_historical_records_and_avoids_duplicate_syncs(self, client, db):
        """Historical sync records are preserved and no duplicate queued sync records are created."""
        from app.models.repository import Repository, RepositoryStatus
        from app.models.repository_sync import RepositorySync, SyncStatus

        seed_membership(db, USER_ID, ORG_ID)
        install = seed_installation(db, org_id=ORG_ID)

        # 1. First connection
        with _mock_github_services():
            res1 = client.post(
                f"/api/v1/organizations/{ORG_ID}/repositories",
                json={"github_repository_id": "123456"},
                headers=auth_headers(USER_ID),
            )
        repo_id = res1.json()["id"]

        # Simulate first sync completed
        sync1 = db.query(RepositorySync).filter(RepositorySync.repository_id == repo_id).first()
        sync1.status = SyncStatus.COMPLETED.value
        repo = db.get(Repository, repo_id)
        repo.status = RepositoryStatus.READY.value
        db.commit()

        # 2. Disconnect
        client.delete(f"/api/v1/repositories/{repo_id}", headers=auth_headers(USER_ID))

        # 3. Reconnect
        with _mock_github_services():
            res2 = client.post(
                f"/api/v1/organizations/{ORG_ID}/repositories",
                json={"github_repository_id": "123456"},
                headers=auth_headers(USER_ID),
            )
        assert res2.status_code == 201

        # 4. Verify sync records
        all_syncs = (
            db.query(RepositorySync)
            .filter(RepositorySync.repository_id == repo_id)
            .order_by(RepositorySync.id.asc())
            .all()
        )
        assert len(all_syncs) == 2, f"Expected 2 sync records (1 historical, 1 new), got {len(all_syncs)}"
        assert all_syncs[0].status == SyncStatus.COMPLETED.value, "Historical completed sync must be preserved"
        assert all_syncs[1].status == SyncStatus.QUEUED.value, "New sync must be queued"

    def test_concurrent_connections_handled(self):
        """Concurrent connection requests are serialized and only one succeeds while other raises 409."""
        import threading
        from app.services.repository_service import RepositoryService
        from fastapi import HTTPException
        from app.models.repository import Repository
        from tests.conftest import TestSessionLocal

        init_session = TestSessionLocal()
        seed_membership(init_session, USER_ID, ORG_ID)
        seed_installation(init_session, org_id=ORG_ID)
        init_session.close()

        results = []
        def attempt_connect(t_id):
            session = TestSessionLocal()
            try:
                with _mock_github_services():
                    r = RepositoryService.connect_repository(ORG_ID, "concurrent-repo-test", session)
                    results.append(("success", t_id, r.id))
            except HTTPException as exc:
                results.append(("conflict", t_id, exc.status_code))
            except Exception as exc:
                results.append(("error", t_id, str(exc)))
            finally:
                session.close()

        threads = [threading.Thread(target=attempt_connect, args=(i,)) for i in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        successes = [r for r in results if r[0] == "success"]
        conflicts = [r for r in results if r[0] == "conflict"]
        assert len(successes) == 1, f"Expected exactly 1 success, got results: {results}"
        assert len(conflicts) == 1, f"Expected exactly 1 conflict, got results: {results}"
        assert conflicts[0][2] == 409

        # Ensure database row count is 1
        verify_session = TestSessionLocal()
        count = verify_session.query(Repository).filter(Repository.github_repository_id == "concurrent-repo-test").count()
        verify_session.close()
        assert count == 1


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
