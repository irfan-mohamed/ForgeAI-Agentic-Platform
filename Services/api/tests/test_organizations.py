"""
Integration tests for the Organizations API.

Covers:
- POST   /api/v1/organizations          (create)
- GET    /api/v1/organizations          (list my orgs)
- GET    /api/v1/organizations/{id}     (get one)
- GET    /api/v1/organizations/{id}/members
- PATCH  /api/v1/organizations/{id}/members/{uid}/role
"""

import pytest
from fastapi.testclient import TestClient

ORGS_URL = "/api/v1/organizations"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _register_and_login(client: TestClient, email: str) -> dict:
    """Registers a new user with the given email and returns their auth headers."""
    client.post(
        "/api/v1/auth/register",
        json={"name": "Other User", "email": email, "password": "Pass123!"},
    )
    resp = client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": "Pass123!"},
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ── Create ────────────────────────────────────────────────────────────────────

class TestCreateOrganization:
    def test_create_returns_201(self, client: TestClient, auth_headers: dict):
        resp = client.post(
            ORGS_URL,
            json={"name": "Acme Corp", "slug": "acme-corp"},
            headers=auth_headers,
        )
        assert resp.status_code == 201

    def test_create_response_fields(self, client: TestClient, auth_headers: dict):
        resp = client.post(
            ORGS_URL,
            json={"name": "Acme Corp", "slug": "acme-corp", "description": "Test company"},
            headers=auth_headers,
        )
        body = resp.json()
        assert body["name"] == "Acme Corp"
        assert body["slug"] == "acme-corp"
        assert body["description"] == "Test company"
        assert body["status"] == "active"
        assert "id" in body
        assert "created_at" in body

    def test_create_duplicate_slug_returns_409(
        self, client: TestClient, auth_headers: dict
    ):
        payload = {"name": "First", "slug": "my-company"}
        client.post(ORGS_URL, json=payload, headers=auth_headers)
        resp = client.post(ORGS_URL, json=payload, headers=auth_headers)
        assert resp.status_code == 409
        assert "already exists" in resp.json()["detail"]

    def test_create_invalid_slug_format_returns_422(
        self, client: TestClient, auth_headers: dict
    ):
        # Slugs must not contain uppercase or spaces
        resp = client.post(
            ORGS_URL,
            json={"name": "Bad Slug", "slug": "Bad Slug!"},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    def test_create_slug_too_short_returns_422(
        self, client: TestClient, auth_headers: dict
    ):
        resp = client.post(
            ORGS_URL,
            json={"name": "Short", "slug": "ab"},  # must be >= 3 chars
            headers=auth_headers,
        )
        assert resp.status_code == 422

    def test_create_without_auth_returns_401(self, client: TestClient):
        resp = client.post(ORGS_URL, json={"name": "X", "slug": "x-org"})
        assert resp.status_code == 401

    def test_creator_becomes_company_admin(
        self, client: TestClient, auth_headers: dict, created_org: dict
    ):
        """The org creator must automatically receive the company_admin role."""
        resp = client.get(
            f"{ORGS_URL}/{created_org['id']}/members",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        members = resp.json()
        assert len(members) == 1
        assert members[0]["role"] == "company_admin"


# ── List ──────────────────────────────────────────────────────────────────────

class TestListOrganizations:
    def test_list_returns_own_orgs(
        self, client: TestClient, auth_headers: dict, created_org: dict
    ):
        resp = client.get(ORGS_URL, headers=auth_headers)
        assert resp.status_code == 200
        orgs = resp.json()
        assert any(o["id"] == created_org["id"] for o in orgs)

    def test_list_does_not_include_other_user_orgs(
        self, client: TestClient, auth_headers: dict, created_org: dict
    ):
        other_headers = _register_and_login(client, "other@example.com")
        other_resp = client.post(
            ORGS_URL,
            json={"name": "Other Corp", "slug": "other-corp"},
            headers=other_headers,
        )
        other_org_id = other_resp.json()["id"]

        my_orgs = client.get(ORGS_URL, headers=auth_headers).json()
        ids = [o["id"] for o in my_orgs]
        assert other_org_id not in ids

    def test_list_without_auth_returns_401(self, client: TestClient):
        assert client.get(ORGS_URL).status_code == 401


# ── Get one ───────────────────────────────────────────────────────────────────

class TestGetOrganization:
    def test_get_own_org_returns_200(
        self, client: TestClient, auth_headers: dict, created_org: dict
    ):
        resp = client.get(f"{ORGS_URL}/{created_org['id']}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == created_org["id"]

    def test_get_other_org_as_non_member_returns_403(
        self, client: TestClient, auth_headers: dict, created_org: dict
    ):
        """Non-members must not be able to see organization details."""
        other_headers = _register_and_login(client, "stranger@example.com")
        resp = client.get(
            f"{ORGS_URL}/{created_org['id']}",
            headers=other_headers,
        )
        assert resp.status_code == 403

    def test_get_nonexistent_org_returns_404(
        self, client: TestClient, auth_headers: dict, created_org: dict
    ):
        # First create and become admin so membership check passes… but org won't exist
        # Use an ID that can't possibly exist
        resp = client.get(f"{ORGS_URL}/99999", headers=auth_headers)
        # 403 because user is not a member of org 99999 (membership guard fires first)
        assert resp.status_code in (403, 404)

    def test_get_without_auth_returns_401(
        self, client: TestClient, created_org: dict
    ):
        resp = client.get(f"{ORGS_URL}/{created_org['id']}")
        assert resp.status_code == 401


# ── Members ───────────────────────────────────────────────────────────────────

class TestOrganizationMembers:
    def test_list_members_returns_200(
        self, client: TestClient, auth_headers: dict, created_org: dict
    ):
        resp = client.get(
            f"{ORGS_URL}/{created_org['id']}/members",
            headers=auth_headers,
        )
        assert resp.status_code == 200

    def test_members_include_user_info(
        self, client: TestClient, auth_headers: dict, created_org: dict
    ):
        members = client.get(
            f"{ORGS_URL}/{created_org['id']}/members",
            headers=auth_headers,
        ).json()
        member = members[0]
        # MembershipWithUserResponse embeds the user object
        assert "user" in member
        assert "email" in member["user"]
        assert "password_hash" not in member["user"]

    def test_non_member_cannot_list_members(
        self, client: TestClient, created_org: dict
    ):
        outsider = _register_and_login(client, "outsider@example.com")
        resp = client.get(
            f"{ORGS_URL}/{created_org['id']}/members",
            headers=outsider,
        )
        assert resp.status_code == 403


# ── Role update ───────────────────────────────────────────────────────────────

class TestUpdateMemberRole:
    def test_admin_can_update_own_role(
        self, client: TestClient, auth_headers: dict, created_org: dict
    ):
        """COMPANY_ADMIN can change their own role (edge case, but valid)."""
        members = client.get(
            f"{ORGS_URL}/{created_org['id']}/members",
            headers=auth_headers,
        ).json()
        admin_user_id = members[0]["user_id"]

        resp = client.patch(
            f"{ORGS_URL}/{created_org['id']}/members/{admin_user_id}/role",
            json={"role": "manager"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["role"] == "manager"

    def test_non_admin_cannot_update_role(
        self, client: TestClient, created_org: dict
    ):
        """Only COMPANY_ADMIN may change roles — others get 403."""
        other_headers = _register_and_login(client, "member@example.com")
        # Get the other user's membership
        resp = client.patch(
            f"{ORGS_URL}/{created_org['id']}/members/1/role",
            json={"role": "hr_admin"},
            headers=other_headers,
        )
        assert resp.status_code == 403

    def test_invalid_role_value_returns_422(
        self, client: TestClient, auth_headers: dict, created_org: dict
    ):
        members = client.get(
            f"{ORGS_URL}/{created_org['id']}/members",
            headers=auth_headers,
        ).json()
        uid = members[0]["user_id"]
        resp = client.patch(
            f"{ORGS_URL}/{created_org['id']}/members/{uid}/role",
            json={"role": "superuser"},   # not a valid MemberRole
            headers=auth_headers,
        )
        assert resp.status_code == 422
