"""
test_chunker.py — Tests for the structural code chunker.
"""

import pytest
from app.services.chunker import chunk_file, CodeChunk


PYTHON_SAMPLE = '''"""Module docstring."""

import os
import sys
from pathlib import Path


CONSTANT = "hello"


def authenticate_user(username: str, password: str) -> bool:
    """Authenticates a user by username and password.
    
    Args:
        username: The user's login name.
        password: The user's password.
    
    Returns:
        True if authentication succeeds, False otherwise.
    """
    if not username or not password:
        return False
    # Check credentials
    return username == "admin" and password == "secret"


def hash_password(password: str) -> str:
    """Hashes a password using bcrypt."""
    import hashlib
    return hashlib.sha256(password.encode()).hexdigest()


class UserService:
    """Service class for user management."""

    def __init__(self, db):
        """Initialize with a database connection."""
        self.db = db

    def create_user(self, username: str, email: str) -> dict:
        """Creates a new user record."""
        return {"username": username, "email": email}

    def get_user(self, user_id: int) -> dict | None:
        """Returns a user by ID, or None if not found."""
        return self.db.get(user_id)

    def delete_user(self, user_id: int) -> bool:
        """Soft-deletes a user. Returns True on success."""
        user = self.db.get(user_id)
        if not user:
            return False
        user["deleted"] = True
        return True
'''


MARKDOWN_SAMPLE = """# ForgeAI Repository Service

A service that manages GitHub App installations and repository connections.

## Installation

To install the service, run:

```bash
pip install -r requirements.txt
```

## Configuration

Set the following environment variables:

- `GITHUB_APP_ID` — Your GitHub App ID
- `GITHUB_APP_PRIVATE_KEY` — Your App's RSA private key

## API Reference

### GET /organizations/{org_id}/github

Returns the GitHub connection status for an organization.

### POST /organizations/{org_id}/repositories

Connects a new GitHub repository to the organization.
"""


class TestPythonChunker:

    def test_returns_chunks(self):
        chunks = chunk_file(PYTHON_SAMPLE, "auth/service.py", "python", "code")
        assert len(chunks) > 0

    def test_all_chunks_have_content(self):
        chunks = chunk_file(PYTHON_SAMPLE, "auth/service.py", "python", "code")
        for chunk in chunks:
            assert chunk.content.strip()

    def test_function_chunks_detected(self):
        chunks = chunk_file(PYTHON_SAMPLE, "auth/service.py", "python", "code")
        function_names = {c.chunk_name for c in chunks if c.chunk_type == "function"}
        assert "authenticate_user" in function_names
        assert "hash_password" in function_names

    def test_class_chunk_detected(self):
        chunks = chunk_file(PYTHON_SAMPLE, "auth/service.py", "python", "code")
        class_chunks = [c for c in chunks if c.chunk_type == "class"]
        assert any(c.chunk_name == "UserService" for c in class_chunks)

    def test_method_chunks_detected(self):
        chunks = chunk_file(PYTHON_SAMPLE, "auth/service.py", "python", "code")
        method_chunks = [c for c in chunks if c.chunk_type == "method"]
        method_names = {c.chunk_name for c in method_chunks}
        assert "UserService.create_user" in method_names
        assert "UserService.get_user" in method_names
        assert "UserService.delete_user" in method_names

    def test_chunks_have_line_numbers(self):
        chunks = chunk_file(PYTHON_SAMPLE, "auth/service.py", "python", "code")
        for chunk in chunks:
            assert chunk.start_line >= 1
            assert chunk.end_line >= chunk.start_line

    def test_chunks_have_token_count(self):
        chunks = chunk_file(PYTHON_SAMPLE, "auth/service.py", "python", "code")
        for chunk in chunks:
            assert chunk.token_count > 0

    def test_chunks_have_sequential_index(self):
        chunks = chunk_file(PYTHON_SAMPLE, "auth/service.py", "python", "code")
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i

    def test_empty_file_returns_no_chunks(self):
        chunks = chunk_file("", "empty.py", "python", "code")
        assert chunks == []

    def test_whitespace_only_returns_no_chunks(self):
        chunks = chunk_file("   \n\n\t\n", "whitespace.py", "python", "code")
        assert chunks == []

    def test_invalid_python_falls_back_to_generic(self):
        bad_python = "def broken(\n    missing closing paren\n    return True\n"
        # Should not raise — falls back to generic chunking
        chunks = chunk_file(bad_python, "broken.py", "python", "code")
        assert isinstance(chunks, list)


class TestMarkdownChunker:

    def test_returns_chunks(self):
        chunks = chunk_file(MARKDOWN_SAMPLE, "README.md", "markdown", "docs")
        assert len(chunks) > 0

    def test_sections_detected(self):
        chunks = chunk_file(MARKDOWN_SAMPLE, "README.md", "markdown", "docs")
        names = [c.chunk_name for c in chunks]
        # Should detect section headings
        assert any("Installation" in (n or "") for n in names)
        assert any("Configuration" in (n or "") for n in names)

    def test_chunk_types_are_doc_section(self):
        chunks = chunk_file(MARKDOWN_SAMPLE, "README.md", "markdown", "docs")
        for chunk in chunks:
            assert chunk.chunk_type == "doc_section"


class TestGenericChunker:

    def test_plain_text_chunked(self):
        text = "\n\n".join([f"Paragraph {i}. " * 20 for i in range(10)])
        chunks = chunk_file(text, "notes.txt", "text", "docs")
        assert len(chunks) > 0

    def test_max_tokens_respected(self):
        # Generate a very long file
        long_text = "A" * 50000
        chunks = chunk_file(long_text, "large.txt", None, "other", max_tokens=200)
        for chunk in chunks:
            # Each chunk should be roughly at most max_tokens
            # (some slack for the sliding window implementation)
            assert chunk.token_count <= 400  # 2x tolerance

    def test_config_yaml_chunked(self):
        yaml_content = """database:
  host: localhost
  port: 5432
  name: forgeai

redis:
  host: localhost
  port: 6379

kafka:
  bootstrap_servers: localhost:9092
  topics:
    - repository.events
    - repository.sync
"""
        chunks = chunk_file(yaml_content, "config.yaml", "yaml", "config")
        assert len(chunks) > 0
