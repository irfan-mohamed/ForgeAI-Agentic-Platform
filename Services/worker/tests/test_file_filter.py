"""
test_file_filter.py — Tests for the file classifier.
"""

import pytest
from app.services.file_filter import classify_file, compute_checksum


class TestClassifyFile:

    def test_python_file_is_indexed(self):
        result = classify_file("src/auth/service.py", size_bytes=1024)
        assert result.should_index is True
        assert result.language == "python"
        assert result.file_type == "code"

    def test_typescript_file_is_indexed(self):
        result = classify_file("src/components/Button.tsx", size_bytes=500)
        assert result.should_index is True
        assert result.language == "typescript"
        assert result.file_type == "code"

    def test_markdown_file_is_indexed(self):
        result = classify_file("docs/README.md", size_bytes=2000)
        assert result.should_index is True
        assert result.language == "markdown"
        assert result.file_type == "docs"

    def test_node_modules_skipped(self):
        result = classify_file("node_modules/lodash/index.js", size_bytes=100)
        assert result.should_index is False
        assert "excluded directory" in result.skip_reason

    def test_venv_skipped(self):
        result = classify_file(".venv/lib/python3.12/site-packages/foo.py")
        assert result.should_index is False

    def test_dist_directory_skipped(self):
        result = classify_file("dist/bundle.js", size_bytes=50000)
        assert result.should_index is False

    def test_png_image_skipped(self):
        result = classify_file("assets/logo.png", size_bytes=10000)
        assert result.should_index is False
        assert ".png" in result.skip_reason

    def test_lock_file_extension_skipped(self):
        result = classify_file("some.lock", size_bytes=500)
        assert result.should_index is False

    def test_package_lock_json_skipped(self):
        result = classify_file("package-lock.json", size_bytes=100000)
        assert result.should_index is False

    def test_env_file_never_indexed(self):
        result = classify_file(".env", size_bytes=200)
        assert result.should_index is False
        assert "secret" in result.skip_reason or "env" in result.skip_reason

    def test_env_example_is_indexed(self):
        # .env.example is safe — it contains example values, not real secrets
        result = classify_file(".env.example", size_bytes=500)
        assert result.should_index is True

    def test_file_too_large_skipped(self):
        # 600 KB — above the 500 KB limit
        result = classify_file("src/big_file.py", size_bytes=600 * 1024)
        assert result.should_index is False
        assert "too large" in result.skip_reason

    def test_yaml_config_indexed(self):
        result = classify_file("config/settings.yaml", size_bytes=1000)
        assert result.should_index is True
        assert result.file_type == "config"

    def test_dockerfile_indexed(self):
        result = classify_file("Dockerfile", size_bytes=500)
        assert result.should_index is True
        assert result.language == "dockerfile"

    def test_sql_file_indexed(self):
        result = classify_file("migrations/001_init.sql", size_bytes=2000)
        assert result.should_index is True
        assert result.language == "sql"

    def test_go_file_indexed(self):
        result = classify_file("internal/auth/handler.go", size_bytes=3000)
        assert result.should_index is True
        assert result.language == "go"

    def test_rust_file_indexed(self):
        result = classify_file("src/main.rs", size_bytes=1000)
        assert result.should_index is True
        assert result.language == "rust"

    def test_pycache_skipped(self):
        result = classify_file("app/__pycache__/service.cpython-312.pyc")
        assert result.should_index is False

    def test_unknown_extension_is_other(self):
        result = classify_file("somefile.xyz", size_bytes=100)
        # Unknown extension — we still index it (other type) unless blocked
        assert result.file_type == "other"


class TestChecksum:

    def test_checksum_is_deterministic(self):
        content = b"hello world"
        assert compute_checksum(content) == compute_checksum(content)

    def test_different_content_different_checksum(self):
        assert compute_checksum(b"hello") != compute_checksum(b"world")

    def test_checksum_length(self):
        # SHA-256 hex digest is 64 characters
        assert len(compute_checksum(b"test")) == 64
