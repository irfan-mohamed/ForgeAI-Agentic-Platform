"""
test_github.py — Integration tests for GitHub integration endpoints.

Tests cover:
  - GitHub connection status (connected / not connected)
  - GitHub callback (saves installation record)
  - List available repositories (mocked GitHub API)
  - Webhook signature validation (valid / invalid)
  - Webhook: installation.deleted → repos revoked
  - Webhook: push → sync queued
  - Webhook: installation_repositories.removed → specific repo revoked
"""

import hashlib
import hmac
import json
from unittest.mock import patch

import pytest

from app.core.config import settings
from tests.conftest import auth_headers, seed_installation, seed_membership, seed_repository

USER_ID = 10
ORG_ID = 10


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sign_payload(body: bytes) -> str:
    """Creates a valid X-Hub-Signature-256 header value."""
    mac = hmac.new(
        settings.GITHUB_WEBHOOK_SECRET.encode(),
        msg=body,
        digestmod=hashlib.sha256,
    )
    return f"sha256={mac.hexdigest()}"


def _webhook_headers(body: bytes, event: str) -> dict:
    """Returns headers for a signed webhook request."""
    return {
        "X-GitHub-Event": event,
        "X-Hub-Signature-256": _sign_payload(body),
        "Content-Type": "application/json",
    }


# ── GitHub Connection Status ──────────────────────────────────────────────────

class TestGitHubConnectionStatus:

    def test_not_connected(self, client, db):
        """Returns connected=false when no installation exists."""
        seed_membership(db, USER_ID, ORG_ID)

        response = client.get(
            f"/api/v1/organizations/{ORG_ID}/github",
            headers=auth_headers(USER_ID),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is False
        assert data["account"] is None

    def test_connected_returns_account_info(self, client, db):
        """Returns connected=true with account info when installation exists."""
        seed_membership(db, USER_ID, ORG_ID)
        seed_installation(db, org_id=ORG_ID, github_installation_id=88888)

        response = client.get(
            f"/api/v1/organizations/{ORG_ID}/github",
            headers=auth_headers(USER_ID),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is True
        assert data["account"]["login"] == "test-org"
        assert data["account"]["account_type"] == "Organization"

    def test_non_member_returns_403(self, client, db):
        """Non-members cannot see GitHub connection status."""
        response = client.get(
            f"/api/v1/organizations/{ORG_ID}/github",
            headers=auth_headers(USER_ID),
        )
        assert response.status_code == 403


# ── GitHub Callback ───────────────────────────────────────────────────────────

class TestGitHubCallback:

    def test_callback_creates_installation(self, client, db):
        """
        A valid callback saves the GitHub installation and redirects.
        We patch github_service.get_installation_info to return mock data.
        """
        from app.api.routes.github import _make_state_token

        # Build a valid state token for org 10, user 10.
        state = _make_state_token(org_id=ORG_ID, user_id=USER_ID)

        mock_install_info = {
            "id": 12345,
            "account": {
                "id": 999,
                "login": "new-org",
                "type": "Organization",
            },
        }

        with patch(
            "app.api.routes.github.github_service.get_installation_info",
            return_value=mock_install_info,
        ):
            response = client.get(
                f"/api/v1/github/callback?installation_id=12345&setup_action=install&state={state}",
                follow_redirects=False,
            )

        # Should redirect to the frontend.
        assert response.status_code == 302
        assert "status=connected" in response.headers["location"]

        # Verify installation was saved.
        from app.models.github_installation import GitHubInstallation
        installation = (
            db.query(GitHubInstallation)
            .filter(GitHubInstallation.organization_id == ORG_ID)
            .first()
        )
        assert installation is not None
        assert installation.github_installation_id == 12345
        assert installation.github_account_login == "new-org"

    def test_callback_invalid_state_returns_400(self, client, db):
        """A tampered state token returns 400."""
        response = client.get(
            "/api/v1/github/callback?installation_id=12345&setup_action=install&state=invalid-state",
        )
        assert response.status_code == 400


# ── List Available Repositories ───────────────────────────────────────────────

class TestListAvailableRepositories:

    def test_list_available_repos_success(self, client, db):
        """Returns repos from GitHub when installation exists."""
        from app.schemas.github import GitHubAvailableRepo

        seed_membership(db, USER_ID, ORG_ID)
        seed_installation(db, org_id=ORG_ID, github_installation_id=77777)

        mock_repos = [
            GitHubAvailableRepo(
                github_repository_id="111",
                name="backend",
                full_name="test-org/backend",
                owner="test-org",
                visibility="private",
                default_branch="main",
            ),
        ]

        with patch.multiple(
            "app.services.github_service",
            get_installation_access_token=lambda x: "fake-token",
            list_installation_repositories=lambda x: mock_repos,
        ):
            response = client.get(
                f"/api/v1/organizations/{ORG_ID}/github/repositories",
                headers=auth_headers(USER_ID),
            )

        assert response.status_code == 200
        data = response.json()
        assert len(data["repositories"]) == 1
        assert data["repositories"][0]["name"] == "backend"

    def test_list_available_repos_no_installation_returns_404(self, client, db):
        """Returns 404 when no GitHub installation exists."""
        seed_membership(db, USER_ID, ORG_ID)

        response = client.get(
            f"/api/v1/organizations/{ORG_ID}/github/repositories",
            headers=auth_headers(USER_ID),
        )

        assert response.status_code == 404


# ── Webhook ───────────────────────────────────────────────────────────────────

class TestWebhookSignature:

    def test_invalid_signature_returns_401(self, client, db):
        """Webhook with wrong signature is rejected."""
        body = json.dumps({"action": "deleted"}).encode()
        response = client.post(
            "/api/v1/github/webhook",
            content=body,
            headers={
                "X-GitHub-Event": "installation",
                "X-Hub-Signature-256": "sha256=invalidsignature",
                "Content-Type": "application/json",
            },
        )
        assert response.status_code == 401

    def test_missing_signature_returns_401(self, client, db):
        """Webhook with no signature header is rejected."""
        body = json.dumps({"action": "deleted"}).encode()
        response = client.post(
            "/api/v1/github/webhook",
            content=body,
            headers={
                "X-GitHub-Event": "installation",
                "Content-Type": "application/json",
            },
        )
        assert response.status_code == 401

    def test_valid_signature_accepted(self, client, db):
        """Webhook with valid HMAC signature is accepted (returns 200)."""
        body = json.dumps({
            "action": "created",
            "installation": {"id": 99999},
        }).encode()
        headers = _webhook_headers(body, "installation")

        response = client.post(
            "/api/v1/github/webhook",
            content=body,
            headers=headers,
        )

        # "created" action is not handled but signature is valid — returns 200.
        assert response.status_code == 200


class TestWebhookInstallationDeleted:

    def test_installation_deleted_revokes_all_repos(self, client, db):
        """
        When a GitHub installation is deleted, all connected repos are revoked.
        """
        INSTALLATION_ID = 66666
        install = seed_installation(db, org_id=ORG_ID, github_installation_id=INSTALLATION_ID)
        repo = seed_repository(db, org_id=ORG_ID, installation_id=install.id)

        body = json.dumps({
            "action": "deleted",
            "installation": {"id": INSTALLATION_ID},
        }).encode()
        headers = _webhook_headers(body, "installation")

        response = client.post(
            "/api/v1/github/webhook",
            content=body,
            headers=headers,
        )

        assert response.status_code == 200

        # Verify repo status changed to access_revoked.
        db.refresh(repo)
        assert repo.status == "access_revoked"


class TestWebhookPush:

    def test_push_event_creates_sync(self, client, db):
        """A push webhook for a connected READY repo creates a new sync record."""
        INSTALLATION_ID = 55555
        install = seed_installation(db, org_id=ORG_ID, github_installation_id=INSTALLATION_ID)
        repo = seed_repository(db, org_id=ORG_ID, installation_id=install.id)
        # seed_repository sets status=READY

        body = json.dumps({
            "installation": {"id": INSTALLATION_ID},
            "repository": {"id": int(repo.github_repository_id)},
            "after": "abc123def456",
        }).encode()
        headers = _webhook_headers(body, "push")

        response = client.post(
            "/api/v1/github/webhook",
            content=body,
            headers=headers,
        )

        assert response.status_code == 200

        # Verify a sync record was created.
        from app.models.repository_sync import RepositorySync, SyncTrigger
        sync = (
            db.query(RepositorySync)
            .filter(
                RepositorySync.repository_id == repo.id,
                RepositorySync.trigger == SyncTrigger.WEBHOOK_PUSH.value,
            )
            .first()
        )
        assert sync is not None
        assert sync.commit_sha == "abc123def456"


class TestWebhookReposRemoved:

    def test_repos_removed_revokes_specific_repos(self, client, db):
        """installation_repositories.removed revokes only specified repos."""
        INSTALLATION_ID = 44444
        install = seed_installation(db, org_id=ORG_ID, github_installation_id=INSTALLATION_ID)
        repo = seed_repository(db, org_id=ORG_ID, installation_id=install.id)
        # repo.github_repository_id == "123456"

        body = json.dumps({
            "action": "removed",
            "installation": {"id": INSTALLATION_ID},
            "repositories_removed": [{"id": 123456, "name": "test-repo"}],
        }).encode()
        headers = _webhook_headers(body, "installation_repositories")

        response = client.post(
            "/api/v1/github/webhook",
            content=body,
            headers=headers,
        )

        assert response.status_code == 200
        db.refresh(repo)
        assert repo.status == "access_revoked"
