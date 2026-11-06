"""
symbol_extractor.py — AST-based code symbol extraction using tree-sitter.

Extracts named symbols (functions, methods, classes, imports, routes) from
source files and builds the relational edge list for code_relationships.

Uses tree-sitter for all supported languages (Python, JavaScript, TypeScript)
so the extraction logic is consistent across the codebase.

Architecture:
    LanguageExtractor          — abstract base
    PythonExtractor            — Python via tree-sitter-python
    JavaScriptExtractor        — JS via tree-sitter-javascript
    TypeScriptExtractor        — TS via tree-sitter-typescript
    extract_symbols()          — public entry point

Grammar nodes referenced below come from:
    Python:     https://github.com/tree-sitter/tree-sitter-python
    JavaScript: https://github.com/tree-sitter/tree-sitter-javascript
    TypeScript: https://github.com/tree-sitter/tree-sitter-typescript

Owned by: Worker Service.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Sequence

logger = logging.getLogger(__name__)

# ── Result dataclasses ────────────────────────────────────────────────────────

@dataclass
class ExtractedSymbol:
    """A single symbol extracted from source code."""
    symbol_name: str
    symbol_type: str          # function|method|class|import|export|route|variable
    start_line: int
    end_line: int
    signature: str | None = None
    docstring: str | None = None
    qualified_name: str | None = None
    is_async: bool = False
    is_exported: bool = False
    parent_name: str | None = None   # enclosing class name, if any


@dataclass
class ExtractedRelationship:
    """A directional relationship between two symbols."""
    source_symbol_name: str
    source_file_path: str
    source_line: int
    target_symbol_name: str
    target_file_path: str | None   # None = external / not yet resolved
    relationship_type: str         # IMPORTS|CALLS|DEFINES|REFERENCES|HANDLES|ROUTES_TO
    confidence: int = 100


@dataclass
class ExtractionResult:
    symbols: list[ExtractedSymbol] = field(default_factory=list)
    relationships: list[ExtractedRelationship] = field(default_factory=list)
    parse_errors: int = 0


# ── Language Grammar Singletons ───────────────────────────────────────────────

_PY_PARSER = None
_JS_PARSER = None
_TS_PARSER = None


def _get_python_parser():
    global _PY_PARSER
    if _PY_PARSER is None:
        try:
            import tree_sitter_python as tspython
            from tree_sitter import Language, Parser
            _PY_PARSER = Parser(Language(tspython.language()))
        except Exception as exc:
            logger.error("Failed to load tree-sitter Python grammar", extra={"error": str(exc)})
            raise
    return _PY_PARSER


def _get_js_parser():
    global _JS_PARSER
    if _JS_PARSER is None:
        try:
            import tree_sitter_javascript as tsjavascript
            from tree_sitter import Language, Parser
            _JS_PARSER = Parser(Language(tsjavascript.language()))
        except Exception as exc:
            logger.error("Failed to load tree-sitter JavaScript grammar", extra={"error": str(exc)})
            raise
    return _JS_PARSER


def _get_ts_parser():
    global _TS_PARSER
    if _TS_PARSER is None:
        try:
            import tree_sitter_typescript as tstypescript
            from tree_sitter import Language, Parser
            # tree-sitter-typescript exposes tsx and typescript grammars
            _TS_PARSER = Parser(Language(tstypescript.language_typescript()))
        except Exception as exc:
            logger.error("Failed to load tree-sitter TypeScript grammar", extra={"error": str(exc)})
            raise
    return _TS_PARSER


# ── Node helpers ──────────────────────────────────────────────────────────────

def _text(node, src_bytes: bytes) -> str:
    """Decode the source slice for a tree-sitter node."""
    return src_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _line(node) -> int:
    """1-indexed start line of a node."""
    return node.start_point[0] + 1


def _end_line(node) -> int:
    """1-indexed end line of a node."""
    return node.end_point[0] + 1


def _first_child_of_type(node, *types: str):
    for child in node.children:
        if child.type in types:
            return child
    return None


def _named_children_of_type(node, *types: str):
    return [c for c in node.named_children if c.type in types]


# ── Python Extractor ──────────────────────────────────────────────────────────

def _extract_python_docstring(body_node, src_bytes: bytes) -> str | None:
    """Returns the first string literal in a block if it's a docstring."""
    if not body_node:
        return None
    for child in body_node.named_children:
        if child.type == "expression_statement":
            expr = _first_child_of_type(child, "string")
            if expr:
                raw = _text(expr, src_bytes).strip("\"' \t\n")
                return raw[:1000] if raw else None
        break  # Only check the very first statement
    return None


def _extract_python_signature(fn_node, src_bytes: bytes) -> str:
    """Returns the def/async def line up to the colon."""
    lines = src_bytes.decode("utf-8", errors="replace").splitlines()
    start = fn_node.start_point[0]
    # Walk from start until we hit a `:` that closes the def
    sig_lines = []
    for i in range(start, min(start + 20, len(lines))):
        sig_lines.append(lines[i].strip())
        if lines[i].rstrip().endswith(":"):
            break
    return " ".join(sig_lines)


class PythonExtractor:
    """Extracts symbols and relationships from Python source via tree-sitter."""

    def extract(self, content: str, file_path: str) -> ExtractionResult:
        result = ExtractionResult()
        src_bytes = content.encode("utf-8")

        try:
            parser = _get_python_parser()
            tree = parser.parse(src_bytes)
        except Exception as exc:
            logger.warning(
                "tree-sitter parse failed for Python file",
                extra={"file_path": file_path, "error": str(exc)},
            )
            result.parse_errors += 1
            return result

        if tree.root_node.has_error:
            result.parse_errors += 1

        self._walk(tree.root_node, src_bytes, file_path, result, parent_class=None)
        return result

    def _walk(self, node, src_bytes, file_path, result, parent_class):
        for child in node.named_children:
            if child.type == "class_definition":
                self._handle_class(child, src_bytes, file_path, result)
            elif child.type in ("function_definition", "async_function_definition"):
                self._handle_function(child, src_bytes, file_path, result, parent_class)
            elif child.type in ("import_statement", "import_from_statement"):
                self._handle_import(child, src_bytes, file_path, result)
            elif child.type == "decorated_definition":
                self._handle_decorated(child, src_bytes, file_path, result, parent_class)
            else:
                self._walk(child, src_bytes, file_path, result, parent_class)

    def _handle_class(self, node, src_bytes, file_path, result):
        name_node = _first_child_of_type(node, "identifier")
        if not name_node:
            return
        class_name = _text(name_node, src_bytes)
        body = _first_child_of_type(node, "block")
        docstring = _extract_python_docstring(body, src_bytes)

        sym = ExtractedSymbol(
            symbol_name=class_name,
            symbol_type="class",
            start_line=_line(node),
            end_line=_end_line(node),
            signature=f"class {class_name}:",
            docstring=docstring,
            qualified_name=class_name,
        )
        result.symbols.append(sym)

        # Walk class body for methods
        if body:
            self._walk(body, src_bytes, file_path, result, parent_class=class_name)

    def _handle_function(self, node, src_bytes, file_path, result, parent_class, decorators=None):
        name_node = _first_child_of_type(node, "identifier")
        if not name_node:
            return
        fn_name = _text(name_node, src_bytes)
        # In tree-sitter-python 0.25+, all functions use 'function_definition'.
        # The 'async' keyword appears as a direct (non-named) child token.
        is_async = (
            node.type == "async_function_definition"
            or any(
                (not c.is_named and hasattr(c, "text") and c.text == b"async")
                for c in node.children
            )
        )
        body = _first_child_of_type(node, "block")
        docstring = _extract_python_docstring(body, src_bytes)
        signature = _extract_python_signature(node, src_bytes)
        qualified = f"{parent_class}.{fn_name}" if parent_class else fn_name
        sym_type = "method" if parent_class else "function"

        # Detect FastAPI/Flask route decorators
        route_info = self._detect_route(decorators or [], src_bytes)

        sym = ExtractedSymbol(
            symbol_name=fn_name,
            symbol_type=sym_type,
            start_line=_line(node),
            end_line=_end_line(node),
            signature=signature,
            docstring=docstring,
            qualified_name=qualified,
            is_async=is_async,
            parent_name=parent_class,
        )
        result.symbols.append(sym)

        if route_info:
            http_method, path = route_info
            route_sym = ExtractedSymbol(
                symbol_name=f"{http_method} {path}",
                symbol_type="route",
                start_line=_line(node),
                end_line=_line(node),
                signature=f"@router.{http_method.lower()}(\"{path}\")",
                qualified_name=f"route:{http_method}:{path}",
            )
            result.symbols.append(route_sym)
            result.relationships.append(ExtractedRelationship(
                source_symbol_name=route_sym.symbol_name,
                source_file_path=file_path,
                source_line=_line(node),
                target_symbol_name=fn_name,
                target_file_path=file_path,
                relationship_type="HANDLES",
            ))

        # Extract calls inside the function body
        if body:
            self._extract_calls(body, src_bytes, file_path, fn_name, result)

    def _handle_decorated(self, node, src_bytes, file_path, result, parent_class):
        """Handle decorated functions/classes."""
        decorators = _named_children_of_type(node, "decorator")
        inner = _first_child_of_type(node, "function_definition", "async_function_definition")
        if inner:
            self._handle_function(inner, src_bytes, file_path, result, parent_class, decorators)
        else:
            inner_class = _first_child_of_type(node, "class_definition")
            if inner_class:
                self._handle_class(inner_class, src_bytes, file_path, result)

    def _handle_import(self, node, src_bytes, file_path, result):
        """Extract import relationships."""
        raw = _text(node, src_bytes)
        if node.type == "import_from_statement":
            # from X import Y, Z
            # Grab the module part
            module_node = None
            for c in node.named_children:
                if c.type == "dotted_name" or c.type == "relative_import":
                    module_node = c
                    break
            module = _text(module_node, src_bytes) if module_node else "?"
            # Grab imported names
            for c in node.named_children:
                if c.type in ("dotted_name", "aliased_import"):
                    name = _text(c, src_bytes)
                    if c != module_node:
                        result.relationships.append(ExtractedRelationship(
                            source_symbol_name="<module>",
                            source_file_path=file_path,
                            source_line=_line(node),
                            target_symbol_name=name,
                            target_file_path=self._module_to_path(module),
                            relationship_type="IMPORTS",
                            confidence=90,
                        ))
        else:
            # import X
            for c in node.named_children:
                if c.type in ("dotted_name", "aliased_import"):
                    name = _text(c, src_bytes)
                    result.relationships.append(ExtractedRelationship(
                        source_symbol_name="<module>",
                        source_file_path=file_path,
                        source_line=_line(node),
                        target_symbol_name=name,
                        target_file_path=None,
                        relationship_type="IMPORTS",
                        confidence=80,
                    ))

    def _extract_calls(self, node, src_bytes, file_path, caller_name, result):
        """Recursively find function call expressions inside a body."""
        for child in node.named_children:
            if child.type == "call":
                fn_node = child.named_children[0] if child.named_children else None
                if fn_node:
                    called = _text(fn_node, src_bytes)
                    # Filter out builtins and very short names
                    if len(called) > 2 and "." in called or called[0].islower():
                        result.relationships.append(ExtractedRelationship(
                            source_symbol_name=caller_name,
                            source_file_path=file_path,
                            source_line=_line(child),
                            target_symbol_name=called.split(".")[-1],
                            target_file_path=None,
                            relationship_type="CALLS",
                            confidence=75,
                        ))
            self._extract_calls(child, src_bytes, file_path, caller_name, result)

    @staticmethod
    def _detect_route(decorators, src_bytes) -> tuple[str, str] | None:
        """If any decorator looks like @app.get("/path"), return (method, path)."""
        route_re = re.compile(
            r'(?:app|router|blueprint)\.(get|post|put|patch|delete|head|options)'
            r'\s*\(\s*["\']([^"\']+)["\']',
            re.IGNORECASE,
        )
        for dec in decorators:
            dec_text = dec.text.decode("utf-8", errors="replace") if hasattr(dec, "text") else ""
            m = route_re.search(dec_text)
            if m:
                return m.group(1).upper(), m.group(2)
        return None

    @staticmethod
    def _module_to_path(module: str) -> str | None:
        """Convert 'app.services.auth' → 'app/services/auth.py'."""
        if module.startswith("."):
            return None  # Relative — resolved later
        return module.replace(".", "/") + ".py"


# ── JavaScript/TypeScript Extractor ───────────────────────────────────────────

class JSExtractor:
    """Extracts symbols from JavaScript source via tree-sitter."""

    _EXPORT_TYPES = {"export_statement", "export_default_statement"}
    _FN_TYPES = {
        "function_declaration",
        "generator_function_declaration",
        "arrow_function",
        "function",
        "generator_function",
    }
    _CLASS_TYPES = {"class_declaration", "class"}
    _METHOD_TYPES = {"method_definition"}
    _IMPORT_TYPES = {"import_statement"}

    def __init__(self, language: str = "javascript"):
        self.language = language

    def _get_parser(self):
        if self.language == "typescript":
            return _get_ts_parser()
        return _get_js_parser()

    def extract(self, content: str, file_path: str) -> ExtractionResult:
        result = ExtractionResult()
        src_bytes = content.encode("utf-8")

        try:
            parser = self._get_parser()
            tree = parser.parse(src_bytes)
        except Exception as exc:
            logger.warning(
                "tree-sitter parse failed",
                extra={"file_path": file_path, "language": self.language, "error": str(exc)},
            )
            result.parse_errors += 1
            return result

        if tree.root_node.has_error:
            result.parse_errors += 1

        self._walk(tree.root_node, src_bytes, file_path, result, parent_class=None, is_exported=False)
        return result

    def _walk(self, node, src_bytes, file_path, result, parent_class, is_exported):
        for child in node.named_children:
            if child.type in self._EXPORT_TYPES:
                self._handle_export(child, src_bytes, file_path, result)
            elif child.type in self._FN_TYPES:
                self._handle_function(child, src_bytes, file_path, result, parent_class, is_exported)
            elif child.type in self._CLASS_TYPES:
                self._handle_class(child, src_bytes, file_path, result)
            elif child.type in self._IMPORT_TYPES:
                self._handle_import(child, src_bytes, file_path, result)
            elif child.type == "lexical_declaration":
                self._handle_lexical_decl(child, src_bytes, file_path, result, is_exported)
            else:
                self._walk(child, src_bytes, file_path, result, parent_class, is_exported)

    def _handle_export(self, node, src_bytes, file_path, result):
        """Handle export statement — mark the inner declaration as exported."""
        for child in node.named_children:
            if child.type in self._FN_TYPES:
                self._handle_function(child, src_bytes, file_path, result, None, is_exported=True)
            elif child.type in self._CLASS_TYPES:
                self._handle_class(child, src_bytes, file_path, result, is_exported=True)
            elif child.type == "lexical_declaration":
                self._handle_lexical_decl(child, src_bytes, file_path, result, is_exported=True)
            else:
                self._walk(child, src_bytes, file_path, result, None, is_exported=True)

    def _handle_function(self, node, src_bytes, file_path, result, parent_class, is_exported):
        name_node = _first_child_of_type(node, "identifier")
        fn_name = _text(name_node, src_bytes) if name_node else "<anonymous>"
        if fn_name == "<anonymous>":
            return
        is_async = any(c.type == "async" or (hasattr(c, "text") and c.text == b"async")
                       for c in node.children)
        sym_type = "method" if parent_class else "function"
        qualified = f"{parent_class}.{fn_name}" if parent_class else fn_name

        body_lines = src_bytes.decode("utf-8", errors="replace").splitlines()
        sig_line = body_lines[node.start_point[0]].strip() if node.start_point[0] < len(body_lines) else ""

        sym = ExtractedSymbol(
            symbol_name=fn_name,
            symbol_type=sym_type,
            start_line=_line(node),
            end_line=_end_line(node),
            signature=sig_line,
            qualified_name=qualified,
            is_async=is_async,
            is_exported=is_exported,
            parent_name=parent_class,
        )
        result.symbols.append(sym)

        # Detect React Router / Express route patterns inside function body
        body = _first_child_of_type(node, "statement_block")
        if body:
            self._extract_route_calls(body, src_bytes, file_path, fn_name, result)

    def _handle_class(self, node, src_bytes, file_path, result, is_exported=False):
        name_node = _first_child_of_type(node, "identifier", "type_identifier")
        if not name_node:
            return
        class_name = _text(name_node, src_bytes)
        body = _first_child_of_type(node, "class_body")

        sym = ExtractedSymbol(
            symbol_name=class_name,
            symbol_type="class",
            start_line=_line(node),
            end_line=_end_line(node),
            signature=f"class {class_name}",
            qualified_name=class_name,
            is_exported=is_exported,
        )
        result.symbols.append(sym)

        # Walk methods
        if body:
            for child in body.named_children:
                if child.type in self._METHOD_TYPES:
                    self._handle_method(child, src_bytes, file_path, result, class_name)

    def _handle_method(self, node, src_bytes, file_path, result, class_name):
        name_node = _first_child_of_type(node, "property_identifier", "computed_property_name")
        if not name_node:
            return
        method_name = _text(name_node, src_bytes)
        is_async = any(
            (hasattr(c, "text") and c.text == b"async") or c.type == "async"
            for c in node.children
        )
        lines = src_bytes.decode("utf-8", errors="replace").splitlines()
        sig = lines[node.start_point[0]].strip() if node.start_point[0] < len(lines) else ""

        sym = ExtractedSymbol(
            symbol_name=method_name,
            symbol_type="method",
            start_line=_line(node),
            end_line=_end_line(node),
            signature=sig,
            qualified_name=f"{class_name}.{method_name}",
            is_async=is_async,
            parent_name=class_name,
        )
        result.symbols.append(sym)

    def _handle_lexical_decl(self, node, src_bytes, file_path, result, is_exported):
        """Handle const/let declarations that may contain arrow functions."""
        for child in node.named_children:
            if child.type == "variable_declarator":
                id_node = _first_child_of_type(child, "identifier")
                val_node = _first_child_of_type(child, "arrow_function", "function")
                if id_node and val_node:
                    fn_name = _text(id_node, src_bytes)
                    is_async = any(
                        (hasattr(c, "text") and c.text == b"async")
                        for c in val_node.children
                    )
                    lines = src_bytes.decode("utf-8", errors="replace").splitlines()
                    sig = lines[child.start_point[0]].strip() if child.start_point[0] < len(lines) else ""
                    sym = ExtractedSymbol(
                        symbol_name=fn_name,
                        symbol_type="function",
                        start_line=_line(child),
                        end_line=_end_line(child),
                        signature=sig,
                        qualified_name=fn_name,
                        is_async=is_async,
                        is_exported=is_exported,
                    )
                    result.symbols.append(sym)

    def _handle_import(self, node, src_bytes, file_path, result):
        """Extract import relationships from ES module imports."""
        # Find source (the module path string)
        source_node = None
        for child in node.named_children:
            if child.type == "string":
                source_node = child
                break

        if not source_node:
            return

        module_path = _text(source_node, src_bytes).strip("'\"")

        # Find imported names
        for child in node.named_children:
            if child.type == "import_clause":
                for sub in child.named_children:
                    if sub.type == "identifier":
                        result.relationships.append(ExtractedRelationship(
                            source_symbol_name="<module>",
                            source_file_path=file_path,
                            source_line=_line(node),
                            target_symbol_name=_text(sub, src_bytes),
                            target_file_path=self._resolve_import_path(file_path, module_path),
                            relationship_type="IMPORTS",
                            confidence=90,
                        ))
                    elif sub.type == "named_imports":
                        for spec in sub.named_children:
                            if spec.type == "import_specifier":
                                name_n = _first_child_of_type(spec, "identifier")
                                if name_n:
                                    result.relationships.append(ExtractedRelationship(
                                        source_symbol_name="<module>",
                                        source_file_path=file_path,
                                        source_line=_line(node),
                                        target_symbol_name=_text(name_n, src_bytes),
                                        target_file_path=self._resolve_import_path(file_path, module_path),
                                        relationship_type="IMPORTS",
                                        confidence=90,
                                    ))

    def _extract_route_calls(self, body, src_bytes, file_path, fn_name, result):
        """Detect Express-style router.get/post/... calls inside function bodies."""
        route_re = re.compile(
            r'(?:router|app|server)\.(get|post|put|patch|delete)\s*\(\s*["\']([^"\']+)["\']',
            re.IGNORECASE,
        )
        body_text = _text(body, src_bytes)
        for m in route_re.finditer(body_text):
            http_method, path = m.group(1).upper(), m.group(2)
            route_sym_name = f"{http_method} {path}"
            result.symbols.append(ExtractedSymbol(
                symbol_name=route_sym_name,
                symbol_type="route",
                start_line=_line(body),
                end_line=_line(body),
                signature=f'router.{http_method.lower()}("{path}", ...)',
                qualified_name=f"route:{http_method}:{path}",
            ))
            result.relationships.append(ExtractedRelationship(
                source_symbol_name=route_sym_name,
                source_file_path=file_path,
                source_line=_line(body),
                target_symbol_name=fn_name,
                target_file_path=file_path,
                relationship_type="HANDLES",
            ))

    @staticmethod
    def _resolve_import_path(source_file: str, import_path: str) -> str | None:
        """Resolve a relative JS import path to a file path."""
        if not import_path.startswith("."):
            return None  # External package — not resolvable here
        import posixpath
        base = posixpath.dirname(source_file)
        resolved = posixpath.normpath(posixpath.join(base, import_path))
        # Try common extensions
        for ext in (".ts", ".tsx", ".js", ".jsx", "/index.ts", "/index.js"):
            candidate = resolved + ext
            # Return raw path — file existence is verified in resolution pass
        return resolved  # Without extension — resolver adds it


class TSExtractor(JSExtractor):
    """TypeScript extractor — same logic as JS, different parser."""
    def __init__(self):
        super().__init__(language="typescript")


# ── Public API ────────────────────────────────────────────────────────────────

# Language → extractor mapping
_EXTRACTORS: dict[str, LanguageExtractor | None] = {}

def _get_extractor(language: str):
    global _EXTRACTORS
    if language not in _EXTRACTORS:
        if language == "python":
            _EXTRACTORS[language] = PythonExtractor()
        elif language == "javascript":
            _EXTRACTORS[language] = JSExtractor("javascript")
        elif language == "typescript":
            _EXTRACTORS[language] = TSExtractor()
        else:
            _EXTRACTORS[language] = None
    return _EXTRACTORS[language]


def extract_symbols(
    content: str,
    file_path: str,
    language: str,
) -> ExtractionResult:
    """
    Extract code symbols and relationships from a source file.

    Args:
        content:   The full decoded text content of the file.
        file_path: The file path relative to repository root.
        language:  Detected language string (e.g. "python", "typescript").

    Returns:
        ExtractionResult with lists of ExtractedSymbol and ExtractedRelationship.
        Returns an empty result (no error raised) for unsupported languages.
    """
    extractor = _get_extractor(language)
    if extractor is None:
        logger.debug(
            "No symbol extractor for language — skipping",
            extra={"language": language, "file_path": file_path},
        )
        return ExtractionResult()

    try:
        result = extractor.extract(content, file_path)
        logger.debug(
            "Symbol extraction complete",
            extra={
                "file_path": file_path,
                "language": language,
                "symbols": len(result.symbols),
                "relationships": len(result.relationships),
                "parse_errors": result.parse_errors,
            },
        )
        return result
    except Exception as exc:
        logger.warning(
            "Symbol extraction failed",
            extra={"file_path": file_path, "language": language, "error": str(exc)},
        )
        return ExtractionResult(parse_errors=1)


# ── Supported languages ────────────────────────────────────────────────────────

SUPPORTED_LANGUAGES = frozenset({"python", "javascript", "typescript"})


def is_supported(language: str | None) -> bool:
    """Returns True if symbol extraction supports this language."""
    return bool(language) and language in SUPPORTED_LANGUAGES
