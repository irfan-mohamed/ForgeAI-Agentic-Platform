"""
test_symbol_extractor.py — Unit tests for tree-sitter symbol extraction.

Tests are fully offline — no DB, no Qdrant, no Kafka.
They test the extraction logic directly on in-memory source code strings.

Key test: test_misnamed_function_body_captured — verifies that a function
whose identifier has no relation to its behavior (e.g. 'irfan' implementing
user login) has its full signature and body captured for semantic indexing.
"""

import pytest

# ── Import guards for environments without tree-sitter installed ──────────────
pytest.importorskip("tree_sitter", reason="tree-sitter not installed")
pytest.importorskip("tree_sitter_python", reason="tree-sitter-python not installed")


from app.services.symbol_extractor import (
    PythonExtractor,
    JSExtractor,
    TSExtractor,
    extract_symbols,
    is_supported,
    SUPPORTED_LANGUAGES,
    ExtractionResult,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

PYTHON_AUTH_MODULE = '''\
"""Authentication utilities."""
import hashlib
from app.db import get_db
from app.models.user import User
from app.services.tokens import generate_access_token


def irfan(email: str, password: str) -> User:
    """
    Authenticates a user by email and password.
    Returns an access token on success.
    """
    db = get_db()
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise ValueError("User not found")
    verify_password(password, user.password_hash)
    return generate_access_token(user)


def verify_password(plain: str, hashed: str) -> bool:
    """Compares a plain password against a stored hash."""
    return hashlib.sha256(plain.encode()).hexdigest() == hashed


class UserService:
    """Service layer for user management."""

    def __init__(self, db):
        self.db = db

    async def get_user(self, user_id: int) -> User:
        """Fetches a user by ID."""
        return self.db.get(User, user_id)

    def update_password(self, user_id: int, new_password: str) -> None:
        """Updates a user password."""
        user = self.db.get(User, user_id)
        user.password_hash = hashlib.sha256(new_password.encode()).hexdigest()
        self.db.commit()
'''

FASTAPI_ROUTES_MODULE = '''\
from fastapi import APIRouter, Depends

router = APIRouter()


@router.post("/users/login")
async def login_endpoint(body: LoginRequest):
    """Login endpoint."""
    return await irfan(body.email, body.password)


@router.get("/users/me")
def get_current_user(user=Depends(get_current_user)):
    return user
'''

JS_MODULE = '''\
import { getUser } from './user';
import axios from 'axios';

export async function fetchUserProfile(userId) {
    const user = await getUser(userId);
    return user;
}

export class AuthService {
    constructor(apiUrl) {
        this.apiUrl = apiUrl;
    }

    async login(email, password) {
        const response = await axios.post(`${this.apiUrl}/auth/login`, {
            email, password
        });
        return response.data;
    }
}

const handleLogout = () => {
    localStorage.clear();
    window.location.href = '/login';
};
'''


# ── Python extraction tests ───────────────────────────────────────────────────

class TestPythonExtractor:
    def setup_method(self):
        self.extractor = PythonExtractor()

    def test_extracts_top_level_function(self):
        result = self.extractor.extract(PYTHON_AUTH_MODULE, "auth.py")
        names = [s.symbol_name for s in result.symbols]
        assert "irfan" in names, f"Expected 'irfan' in {names}"
        assert "verify_password" in names

    def test_misnamed_function_body_captured(self):
        """
        Core Phase 1 test: a function named 'irfan' that implements user login
        must be extracted with its full signature and docstring so the embedding
        pipeline can index its BEHAVIOR, not just its name.

        A semantic search for "user login" or "authenticate user" must
        be able to find this function via the embedded content.
        """
        result = self.extractor.extract(PYTHON_AUTH_MODULE, "auth.py")
        irfan_sym = next((s for s in result.symbols if s.symbol_name == "irfan"), None)

        assert irfan_sym is not None, "Function 'irfan' was not extracted"
        assert irfan_sym.symbol_type == "function"
        assert irfan_sym.start_line > 0
        assert irfan_sym.end_line > irfan_sym.start_line

        # The signature must contain enough behavioral signal for embedding
        assert irfan_sym.signature is not None
        assert "email" in irfan_sym.signature or "password" in irfan_sym.signature, (
            f"Signature should contain params for semantic indexing: {irfan_sym.signature!r}"
        )

        # Docstring is the richest behavioral signal — must be extracted
        assert irfan_sym.docstring is not None, (
            "Docstring must be captured for semantic discovery of misnamed functions"
        )
        assert "authenticat" in irfan_sym.docstring.lower() or "login" in irfan_sym.docstring.lower(), (
            f"Docstring should contain behavioral description: {irfan_sym.docstring!r}"
        )

    def test_extracts_class_with_methods(self):
        result = self.extractor.extract(PYTHON_AUTH_MODULE, "auth.py")
        class_sym = next((s for s in result.symbols if s.symbol_name == "UserService"), None)
        assert class_sym is not None
        assert class_sym.symbol_type == "class"

        method_names = [s.symbol_name for s in result.symbols if s.parent_name == "UserService"]
        assert "get_user" in method_names
        assert "update_password" in method_names

    def test_async_method_flagged(self):
        result = self.extractor.extract(PYTHON_AUTH_MODULE, "auth.py")
        get_user = next(
            (s for s in result.symbols if s.symbol_name == "get_user"),
            None,
        )
        assert get_user is not None
        assert get_user.is_async is True

    def test_sync_function_not_flagged_async(self):
        result = self.extractor.extract(PYTHON_AUTH_MODULE, "auth.py")
        verify = next(s for s in result.symbols if s.symbol_name == "verify_password")
        assert verify.is_async is False

    def test_import_relationships_extracted(self):
        result = self.extractor.extract(PYTHON_AUTH_MODULE, "auth.py")
        rel_types = [r.relationship_type for r in result.relationships]
        assert "IMPORTS" in rel_types, "Import relationships must be extracted"

    def test_extracts_fastapi_route_decorator(self):
        result = self.extractor.extract(FASTAPI_ROUTES_MODULE, "routes.py")
        route_syms = [s for s in result.symbols if s.symbol_type == "route"]
        assert len(route_syms) >= 1, f"Expected route symbols, got: {[s.symbol_name for s in result.symbols]}"

        route_names = [s.symbol_name for s in route_syms]
        # At least one route should contain the path
        assert any("/users" in name for name in route_names), (
            f"Expected route with /users path, got: {route_names}"
        )

    def test_handles_relationship_for_route(self):
        result = self.extractor.extract(FASTAPI_ROUTES_MODULE, "routes.py")
        handles_rels = [r for r in result.relationships if r.relationship_type == "HANDLES"]
        assert len(handles_rels) >= 1, "Route-to-handler HANDLES relationships must be extracted"

    def test_parse_error_does_not_raise(self):
        """Malformed Python should return partial results, not raise."""
        broken = "def foo(:\n    pass\n\ndef bar():\n    return 1\n"
        result = self.extractor.extract(broken, "broken.py")
        # Should not raise; may have parse_errors > 0
        assert isinstance(result, ExtractionResult)

    def test_empty_file(self):
        result = self.extractor.extract("", "empty.py")
        assert result.symbols == []
        assert result.relationships == []

    def test_qualified_name_for_method(self):
        result = self.extractor.extract(PYTHON_AUTH_MODULE, "auth.py")
        update_pw = next(
            (s for s in result.symbols if s.symbol_name == "update_password"),
            None,
        )
        assert update_pw is not None
        assert update_pw.qualified_name == "UserService.update_password"


# ── JavaScript extraction tests ───────────────────────────────────────────────

class TestJSExtractor:
    def setup_method(self):
        pytest.importorskip("tree_sitter_javascript")
        self.extractor = JSExtractor("javascript")

    def test_extracts_named_async_function(self):
        result = self.extractor.extract(JS_MODULE, "auth.js")
        names = [s.symbol_name for s in result.symbols]
        assert "fetchUserProfile" in names

    def test_marks_async_function(self):
        result = self.extractor.extract(JS_MODULE, "auth.js")
        fn = next((s for s in result.symbols if s.symbol_name == "fetchUserProfile"), None)
        assert fn is not None
        assert fn.is_async is True

    def test_marks_exported_function(self):
        result = self.extractor.extract(JS_MODULE, "auth.js")
        fn = next((s for s in result.symbols if s.symbol_name == "fetchUserProfile"), None)
        assert fn is not None
        assert fn.is_exported is True

    def test_extracts_class(self):
        result = self.extractor.extract(JS_MODULE, "auth.js")
        class_sym = next((s for s in result.symbols if s.symbol_name == "AuthService"), None)
        assert class_sym is not None
        assert class_sym.symbol_type == "class"

    def test_extracts_class_methods(self):
        result = self.extractor.extract(JS_MODULE, "auth.js")
        method_names = [s.symbol_name for s in result.symbols if s.symbol_type == "method"]
        assert "login" in method_names

    def test_extracts_const_arrow_function(self):
        result = self.extractor.extract(JS_MODULE, "auth.js")
        names = [s.symbol_name for s in result.symbols]
        assert "handleLogout" in names

    def test_extracts_import_relationships(self):
        result = self.extractor.extract(JS_MODULE, "auth.js")
        import_rels = [r for r in result.relationships if r.relationship_type == "IMPORTS"]
        assert len(import_rels) >= 1

    def test_resolves_relative_import_path(self):
        result = self.extractor.extract(JS_MODULE, "src/services/auth.js")
        # import { getUser } from './user' → should resolve to a path under src/services/
        import_rels = [r for r in result.relationships if r.relationship_type == "IMPORTS"]
        relative_imports = [r for r in import_rels if r.target_file_path is not None]
        assert any("user" in (r.target_file_path or "") for r in relative_imports)


# ── TypeScript extraction tests ───────────────────────────────────────────────

class TestTSExtractor:
    def setup_method(self):
        pytest.importorskip("tree_sitter_typescript")
        self.extractor = TSExtractor()

    def test_extracts_typescript_class(self):
        ts_content = '''\
export class UserRepository {
    constructor(private db: Database) {}

    async findById(id: number): Promise<User | null> {
        return this.db.query("SELECT * FROM users WHERE id = $1", [id]);
    }

    async create(email: string, passwordHash: string): Promise<User> {
        return this.db.query(
            "INSERT INTO users (email, password_hash) VALUES ($1, $2) RETURNING *",
            [email, passwordHash]
        );
    }
}
'''
        result = self.extractor.extract(ts_content, "user.repository.ts")
        class_sym = next((s for s in result.symbols if s.symbol_name == "UserRepository"), None)
        assert class_sym is not None
        assert class_sym.is_exported is True

    def test_extracts_interface_as_class(self):
        """TypeScript interfaces are often class-like; extractor should handle gracefully."""
        ts_content = '''\
interface LoginRequest {
    email: string;
    password: string;
}

async function authenticate(req: LoginRequest): Promise<string> {
    return verifyCredentials(req.email, req.password);
}
'''
        result = self.extractor.extract(ts_content, "auth.ts")
        # At minimum, the function should be extracted
        names = [s.symbol_name for s in result.symbols]
        assert "authenticate" in names


# ── Public API tests ──────────────────────────────────────────────────────────

class TestExtractSymbols:
    def test_dispatches_to_python_extractor(self):
        result = extract_symbols(
            content=PYTHON_AUTH_MODULE,
            file_path="auth.py",
            language="python",
        )
        assert len(result.symbols) > 0

    def test_unsupported_language_returns_empty(self):
        result = extract_symbols(
            content="fn main() { println!(\"hello\"); }",
            file_path="main.rs",
            language="rust",
        )
        assert result.symbols == []
        assert result.relationships == []
        assert result.parse_errors == 0

    def test_is_supported_python(self):
        assert is_supported("python") is True

    def test_is_supported_javascript(self):
        assert is_supported("javascript") is True

    def test_is_supported_typescript(self):
        assert is_supported("typescript") is True

    def test_is_supported_none(self):
        assert is_supported(None) is False

    def test_is_supported_rust(self):
        assert is_supported("rust") is False

    def test_supported_languages_constant(self):
        assert "python" in SUPPORTED_LANGUAGES
        assert "javascript" in SUPPORTED_LANGUAGES
        assert "typescript" in SUPPORTED_LANGUAGES
