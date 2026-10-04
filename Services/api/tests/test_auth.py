"""
Integration tests for POST /api/v1/auth/register and POST /api/v1/auth/login.
"""

import pytest
from fastapi.testclient import TestClient


REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"

VALID_USER = {
    "name": "Alice Smith",
    "email": "alice@example.com",
    "password": "Secure123!",
}


# ── Registration ──────────────────────────────────────────────────────────────

class TestRegister:
    def test_register_success_returns_201(self, client: TestClient):
        response = client.post(REGISTER_URL, json=VALID_USER)
        assert response.status_code == 201

    def test_register_success_body(self, client: TestClient):
        response = client.post(REGISTER_URL, json=VALID_USER)
        body = response.json()
        assert "User Created Successfully" in body["status"]

    def test_register_does_not_return_password(self, client: TestClient):
        """Ensure no credential field leaks from the registration endpoint."""
        response = client.post(REGISTER_URL, json=VALID_USER)
        body = response.json()
        assert "password" not in body
        assert "password_hash" not in body

    def test_register_duplicate_email_returns_400(self, client: TestClient):
        client.post(REGISTER_URL, json=VALID_USER)
        response = client.post(REGISTER_URL, json=VALID_USER)
        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]

    def test_register_invalid_email_returns_422(self, client: TestClient):
        payload = {**VALID_USER, "email": "not-an-email"}
        response = client.post(REGISTER_URL, json=payload)
        assert response.status_code == 422

    def test_register_missing_name_returns_422(self, client: TestClient):
        payload = {"email": "bob@example.com", "password": "Pass1!"}
        response = client.post(REGISTER_URL, json=payload)
        assert response.status_code == 422

    def test_register_missing_password_returns_422(self, client: TestClient):
        payload = {"name": "Bob", "email": "bob@example.com"}
        response = client.post(REGISTER_URL, json=payload)
        assert response.status_code == 422


# ── Login ─────────────────────────────────────────────────────────────────────

class TestLogin:
    @pytest.fixture(autouse=True)
    def _register(self, client: TestClient):
        """Ensure the user exists before each login test."""
        client.post(REGISTER_URL, json=VALID_USER)

    def test_login_success_returns_200(self, client: TestClient):
        response = client.post(
            LOGIN_URL,
            data={"username": VALID_USER["email"], "password": VALID_USER["password"]},
        )
        assert response.status_code == 200

    def test_login_returns_bearer_token(self, client: TestClient):
        response = client.post(
            LOGIN_URL,
            data={"username": VALID_USER["email"], "password": VALID_USER["password"]},
        )
        body = response.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"
        # A JWT has exactly two dots
        assert body["access_token"].count(".") == 2

    def test_login_wrong_password_returns_401(self, client: TestClient):
        response = client.post(
            LOGIN_URL,
            data={"username": VALID_USER["email"], "password": "WrongPassword!"},
        )
        assert response.status_code == 401

    def test_login_nonexistent_user_returns_401(self, client: TestClient):
        response = client.post(
            LOGIN_URL,
            data={"username": "nobody@example.com", "password": "anything"},
        )
        assert response.status_code == 401

    def test_login_empty_credentials_returns_422(self, client: TestClient):
        response = client.post(LOGIN_URL, data={})
        assert response.status_code == 422
