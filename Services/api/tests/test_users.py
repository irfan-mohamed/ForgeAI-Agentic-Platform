"""
Integration tests for GET /api/v1/users/me
"""

import pytest
from fastapi.testclient import TestClient

ME_URL = "/api/v1/users/me"


class TestGetMe:
    def test_me_returns_200_with_valid_token(
        self, client: TestClient, auth_headers: dict
    ):
        response = client.get(ME_URL, headers=auth_headers)
        assert response.status_code == 200

    def test_me_returns_correct_fields(
        self, client: TestClient, auth_headers: dict, registered_user: dict
    ):
        response = client.get(ME_URL, headers=auth_headers)
        body = response.json()
        assert body["email"] == registered_user["email"]
        assert body["name"] == registered_user["name"]
        assert "id" in body
        assert "status" in body
        assert "created_at" in body
        assert "updated_at" in body

    def test_me_does_not_return_password_hash(
        self, client: TestClient, auth_headers: dict
    ):
        """Critical security check: password_hash must never be returned."""
        response = client.get(ME_URL, headers=auth_headers)
        body = response.json()
        assert "password_hash" not in body
        assert "password" not in body

    def test_me_without_token_returns_401(self, client: TestClient):
        response = client.get(ME_URL)
        assert response.status_code == 401

    def test_me_with_malformed_token_returns_401(self, client: TestClient):
        response = client.get(ME_URL, headers={"Authorization": "Bearer not.a.real.token"})
        assert response.status_code == 401

    def test_me_with_expired_token_returns_401(self, client: TestClient, registered_user: dict):
        """Tokens with negative expiry should be rejected."""
        from app.core.security import create_access_token
        from datetime import timedelta

        # We know the first user in a fresh DB gets id=1
        expired_token = create_access_token(subject=1, expires_delta=timedelta(seconds=-1))
        response = client.get(ME_URL, headers={"Authorization": f"Bearer {expired_token}"})
        assert response.status_code == 401
