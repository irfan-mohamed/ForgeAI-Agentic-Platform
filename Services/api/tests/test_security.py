"""
Unit tests for app.core.security

These tests exercise the pure functions in the security module with no DB
or HTTP layer involved.
"""

import pytest
import time
from datetime import timedelta

from app.core.security import (
    get_password_hash,
    verify_password,
    create_access_token,
    decode_access_token,
)


class TestPasswordHashing:
    def test_hash_returns_string(self):
        hashed = get_password_hash("MyPassword1!")
        assert isinstance(hashed, str)

    def test_hash_is_not_plaintext(self):
        plain = "secret123"
        hashed = get_password_hash(plain)
        assert hashed != plain

    def test_different_calls_produce_different_hashes(self):
        """bcrypt embeds a random salt — same password yields different hashes."""
        h1 = get_password_hash("same_password")
        h2 = get_password_hash("same_password")
        assert h1 != h2

    def test_verify_correct_password(self):
        plain = "CorrectPassword99"
        hashed = get_password_hash(plain)
        assert verify_password(plain, hashed) is True

    def test_verify_wrong_password(self):
        hashed = get_password_hash("CorrectPassword99")
        assert verify_password("WrongPassword", hashed) is False

    def test_verify_empty_password_fails(self):
        hashed = get_password_hash("realpassword")
        assert verify_password("", hashed) is False


class TestJWT:
    def test_create_token_returns_string(self):
        token = create_access_token(subject="42")
        assert isinstance(token, str)
        assert len(token) > 20

    def test_decode_returns_subject(self):
        token = create_access_token(subject="99")
        subject = decode_access_token(token)
        assert subject == "99"

    def test_decode_integer_subject(self):
        """Subject is coerced to str; decoding must return the string form."""
        token = create_access_token(subject=7)
        assert decode_access_token(token) == "7"

    def test_expired_token_raises(self):
        token = create_access_token(
            subject="1",
            expires_delta=timedelta(seconds=-1),  # already expired
        )
        with pytest.raises(ValueError, match="couldn't validate credentials"):
            decode_access_token(token)

    def test_tampered_token_raises(self):
        token = create_access_token(subject="5")
        bad_token = token[:-4] + "XXXX"   # corrupt signature
        with pytest.raises(ValueError):
            decode_access_token(bad_token)

    def test_random_string_raises(self):
        with pytest.raises(ValueError):
            decode_access_token("not.a.jwt")
