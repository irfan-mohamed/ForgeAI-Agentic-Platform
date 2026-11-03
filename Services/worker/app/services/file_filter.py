"""
file_filter.py — Determines which repository files should be indexed.

Philosophy:
  We want to index files that contain KNOWLEDGE useful to an AI assistant:
    - Source code (functions, classes, logic, structure)
    - Documentation (READMEs, guides, API docs)
    - Configuration (meaningful config, not secrets)

  We want to SKIP files that are:
    - Generated/compiled artifacts (dist/, build/, node_modules/)
    - Binary assets (images, videos, fonts, binaries)
    - Very large files (unlikely to be useful; too costly to embed)
    - Secrets/credentials (we must never embed these)
    - Lock files (package-lock.json, poetry.lock — too noisy)
    - Test snapshots and generated mock data

Design:
  Each file is classified into a FileCategory which determines:
    - Should it be indexed? (is_indexable)
    - What language/type is it? (language, file_type)
    - How should it be chunked? (chunking strategy hint)
"""

import os
import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

# Maximum file size to index (bytes). Files larger than this are skipped.
MAX_FILE_SIZE_BYTES = 500 * 1024  # 500 KB


# ── Skip path patterns ────────────────────────────────────────────────────────

# Directory names that should be entirely skipped.
SKIP_DIRECTORIES: frozenset[str] = frozenset({
    # Dependency directories
    "node_modules", ".venv", "venv", "env", ".env",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "vendor", "bower_components", "jspm_packages",

    # Build / dist output
    "dist", "build", "out", ".next", ".nuxt", ".svelte-kit",
    "target", "bin", "obj", ".gradle", ".mvn",

    # Version control internals
    ".git", ".hg", ".svn",

    # IDE / editor
    ".idea", ".vscode", ".eclipse",

    # Coverage / test artifacts
    "coverage", ".nyc_output", "htmlcov",

    # Docker / K8s generated
    ".terraform", "terraform.tfstate.d",
})


# File extensions that are always skipped (binary, generated, secrets).
SKIP_EXTENSIONS: frozenset[str] = frozenset({
    # Images
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp",
    ".bmp", ".tiff", ".tif", ".heic",

    # Video / audio
    ".mp4", ".mp3", ".wav", ".avi", ".mov", ".mkv", ".webm",

    # Fonts
    ".ttf", ".otf", ".woff", ".woff2", ".eot",

    # Archives / binaries
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
    ".exe", ".dll", ".so", ".dylib", ".bin", ".wasm",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",

    # Database files
    ".db", ".sqlite", ".sqlite3",

    # Compiled code
    ".pyc", ".pyo", ".class", ".jar", ".war",
    ".o", ".obj", ".a", ".lib",

    # Lock files (very large, mostly noise for AI)
    ".lock",                    # e.g. poetry.lock, Cargo.lock
})


# Specific filenames to always skip.
SKIP_FILENAMES: frozenset[str] = frozenset({
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "composer.lock",
    "Gemfile.lock",
    "go.sum",
    ".DS_Store",
    "Thumbs.db",
    ".gitignore",
    ".gitattributes",
    ".editorconfig",
    ".prettierignore",
    ".eslintignore",
    "CODEOWNERS",
})


# ── Language detection ────────────────────────────────────────────────────────

# Maps file extension → (language, file_type)
# file_type is one of: "code", "docs", "config", "data", "other"
EXTENSION_MAP: dict[str, tuple[str, str]] = {
    # Python
    ".py": ("python", "code"),
    ".pyi": ("python", "code"),
    ".ipynb": ("python", "code"),   # Jupyter — handled specially

    # JavaScript / TypeScript
    ".js": ("javascript", "code"),
    ".jsx": ("javascript", "code"),
    ".mjs": ("javascript", "code"),
    ".cjs": ("javascript", "code"),
    ".ts": ("typescript", "code"),
    ".tsx": ("typescript", "code"),

    # Web
    ".html": ("html", "code"),
    ".htm": ("html", "code"),
    ".css": ("css", "code"),
    ".scss": ("scss", "code"),
    ".sass": ("sass", "code"),
    ".vue": ("vue", "code"),
    ".svelte": ("svelte", "code"),

    # Backend languages
    ".java": ("java", "code"),
    ".kt": ("kotlin", "code"),
    ".scala": ("scala", "code"),
    ".go": ("go", "code"),
    ".rs": ("rust", "code"),
    ".rb": ("ruby", "code"),
    ".php": ("php", "code"),
    ".cs": ("csharp", "code"),
    ".cpp": ("cpp", "code"),
    ".cc": ("cpp", "code"),
    ".cxx": ("cpp", "code"),
    ".c": ("c", "code"),
    ".h": ("c", "code"),
    ".hpp": ("cpp", "code"),
    ".swift": ("swift", "code"),
    ".dart": ("dart", "code"),
    ".ex": ("elixir", "code"),
    ".exs": ("elixir", "code"),
    ".erl": ("erlang", "code"),
    ".hrl": ("erlang", "code"),
    ".clj": ("clojure", "code"),
    ".cljs": ("clojurescript", "code"),
    ".hs": ("haskell", "code"),
    ".ml": ("ocaml", "code"),
    ".fs": ("fsharp", "code"),
    ".fsx": ("fsharp", "code"),
    ".r": ("r", "code"),
    ".R": ("r", "code"),
    ".jl": ("julia", "code"),
    ".lua": ("lua", "code"),

    # Shell
    ".sh": ("shell", "code"),
    ".bash": ("shell", "code"),
    ".zsh": ("shell", "code"),
    ".fish": ("shell", "code"),
    ".ps1": ("powershell", "code"),

    # SQL
    ".sql": ("sql", "code"),

    # Infrastructure as Code
    ".tf": ("terraform", "config"),
    ".tfvars": ("terraform", "config"),
    ".bicep": ("bicep", "config"),

    # Config / data formats
    ".json": ("json", "config"),
    ".yaml": ("yaml", "config"),
    ".yml": ("yaml", "config"),
    ".toml": ("toml", "config"),
    ".ini": ("ini", "config"),
    ".cfg": ("ini", "config"),
    ".conf": ("config", "config"),
    ".env.example": ("env", "config"),
    ".env.sample": ("env", "config"),
    ".xml": ("xml", "config"),
    ".proto": ("protobuf", "config"),
    ".graphql": ("graphql", "code"),
    ".gql": ("graphql", "code"),

    # Documentation
    ".md": ("markdown", "docs"),
    ".mdx": ("markdown", "docs"),
    ".rst": ("restructuredtext", "docs"),
    ".txt": ("text", "docs"),
    ".adoc": ("asciidoc", "docs"),

    # Templates
    ".jinja": ("jinja", "code"),
    ".jinja2": ("jinja", "code"),
    ".j2": ("jinja", "code"),
    ".tmpl": ("template", "code"),
    ".tpl": ("template", "code"),
    ".hbs": ("handlebars", "code"),
    ".ejs": ("ejs", "code"),

    # Dockerfile
    ".dockerfile": ("dockerfile", "config"),
}

# Special filenames with no extension
FILENAME_LANGUAGE_MAP: dict[str, tuple[str, str]] = {
    "dockerfile": ("dockerfile", "config"),
    "makefile": ("makefile", "config"),
    "jenkinsfile": ("groovy", "config"),
    "vagrantfile": ("ruby", "config"),
    "procfile": ("procfile", "config"),
    "rakefile": ("ruby", "config"),
    "gemfile": ("ruby", "config"),
    "brewfile": ("ruby", "config"),
    "cmakelists.txt": ("cmake", "config"),
    ".env.example": ("env", "config"),
    ".env.sample": ("env", "config"),
    "readme": ("markdown", "docs"),
    "readme.md": ("markdown", "docs"),
    "readme.rst": ("restructuredtext", "docs"),
    "changelog": ("markdown", "docs"),
    "changelog.md": ("markdown", "docs"),
    "license": ("text", "docs"),
    "license.md": ("text", "docs"),
    "contributing.md": ("markdown", "docs"),
    "authors": ("text", "docs"),
    "authors.md": ("markdown", "docs"),
}


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class FileClassification:
    path: str
    should_index: bool
    language: str | None
    file_type: str              # "code", "docs", "config", "data", "other"
    skip_reason: str | None = None  # Set when should_index=False


# ── Main classifier ───────────────────────────────────────────────────────────

def classify_file(path: str, size_bytes: int = 0) -> FileClassification:
    """
    Determines whether a file should be indexed and how to classify it.

    Args:
        path: File path relative to repository root (e.g. "src/auth/service.py")
        size_bytes: File size in bytes (0 if unknown)

    Returns:
        FileClassification with should_index=True/False and classification info.
    """
    parts = Path(path).parts
    name = Path(path).name
    ext = Path(path).suffix.lower()
    stem_lower = Path(path).stem.lower()
    name_lower = name.lower()

    # ── Check: skip directory? ────────────────────────────────────────────────
    for part in parts[:-1]:   # All parts except the filename itself
        if part.lower() in SKIP_DIRECTORIES:
            return FileClassification(
                path=path,
                should_index=False,
                language=None,
                file_type="other",
                skip_reason=f"in excluded directory: {part}",
            )

    # ── Check: skip extension? ────────────────────────────────────────────────
    if ext in SKIP_EXTENSIONS:
        return FileClassification(
            path=path,
            should_index=False,
            language=None,
            file_type="other",
            skip_reason=f"excluded extension: {ext}",
        )

    # ── Check: skip filename? ─────────────────────────────────────────────────
    if name_lower in SKIP_FILENAMES:
        return FileClassification(
            path=path,
            should_index=False,
            language=None,
            file_type="other",
            skip_reason=f"excluded filename: {name}",
        )

    # ── Check: file too large? ────────────────────────────────────────────────
    if size_bytes > MAX_FILE_SIZE_BYTES:
        return FileClassification(
            path=path,
            should_index=False,
            language=None,
            file_type="other",
            skip_reason=f"file too large: {size_bytes} bytes (max {MAX_FILE_SIZE_BYTES})",
        )

    # ── Check: secret/env file? ───────────────────────────────────────────────
    # .env files (actual env files, not .env.example) must never be indexed.
    if name_lower == ".env" or (name_lower.startswith(".env.") and "example" not in name_lower and "sample" not in name_lower):
        return FileClassification(
            path=path,
            should_index=False,
            language=None,
            file_type="other",
            skip_reason="env/secret file — never indexed",
        )

    # ── Detect language ───────────────────────────────────────────────────────
    language, file_type = _detect_language(name, name_lower, ext)

    return FileClassification(
        path=path,
        should_index=True,
        language=language,
        file_type=file_type,
    )


def _detect_language(name: str, name_lower: str, ext: str) -> tuple[str | None, str]:
    """Returns (language, file_type) for a file."""
    # Extension-based detection (most common case)
    if ext and ext in EXTENSION_MAP:
        return EXTENSION_MAP[ext]

    # Filename-based detection (files without extensions)
    if name_lower in FILENAME_LANGUAGE_MAP:
        return FILENAME_LANGUAGE_MAP[name_lower]

    # No match
    return None, "other"


def compute_checksum(content: bytes) -> str:
    """Returns SHA-256 hex digest of file content bytes."""
    return hashlib.sha256(content).hexdigest()
