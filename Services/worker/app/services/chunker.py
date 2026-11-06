"""
chunker.py — Intelligent code and document chunker.

Philosophy:
  Naive chunking (split every N characters) destroys semantic meaning.
  We chunk ALONG STRUCTURAL BOUNDARIES so each chunk is a coherent unit:

  For CODE files:
    - Functions, methods, and their docstrings → one chunk each
    - Classes with their class-level docstring → one chunk (header)
    - Class methods → individual chunks tagged with their parent class
    - Top-level imports/constants → one chunk (module context)
    - Standalone code blocks (not in a function/class) → chunks by blank lines

  For DOCUMENTATION files (Markdown, RST):
    - Each section/heading → one chunk
    - Large sections split at paragraph boundaries respecting max tokens

  For CONFIG files (YAML, JSON, TOML):
    - Top-level keys → individual chunks
    - Small configs kept as a single chunk

  For UNKNOWN types:
    - Sliding window with overlap (safe fallback)

Chunking output:
  Each chunk is a CodeChunk dataclass containing:
    - content: the text
    - chunk_type: "function" | "class" | "method" | "module" | "doc_section" | "block"
    - chunk_name: detected name (e.g. "authenticate_user", "UserService.create")
    - start_line / end_line: 1-indexed line numbers
    - token_count: approximate token count

Token counting uses tiktoken for accuracy against OpenAI embedding models.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Iterator

logger = logging.getLogger(__name__)

# Lazy-load tiktoken (it downloads data on first use)
_TOKENIZER = None


def _get_tokenizer():
    global _TOKENIZER
    if _TOKENIZER is None:
        try:
            import tiktoken
            _TOKENIZER = tiktoken.get_encoding("cl100k_base")
        except ImportError:
            logger.warning("tiktoken not available — using character-based token estimate")
    return _TOKENIZER


def _count_tokens(text: str) -> int:
    """Returns token count for text. Falls back to character/4 if tiktoken unavailable."""
    tokenizer = _get_tokenizer()
    if tokenizer:
        return len(tokenizer.encode(text))
    return len(text) // 4


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class CodeChunk:
    """Represents one indexable chunk from a file."""
    content: str
    chunk_type: str             # "function", "class", "method", "module", "doc_section", "block"
    chunk_name: str | None      # Detected name (e.g. "UserService", "authenticate_user")
    chunk_index: int            # Zero-based sequence within the file
    start_line: int             # 1-indexed
    end_line: int               # 1-indexed
    token_count: int = field(default=0, init=False)

    def __post_init__(self):
        self.token_count = _count_tokens(self.content)


# ── Main entry point ──────────────────────────────────────────────────────────

def chunk_file(
    content: str,
    file_path: str,
    language: str | None,
    file_type: str,
    max_tokens: int = 512,
    overlap_tokens: int = 64,
) -> list[CodeChunk]:
    """
    Chunk a file's content into indexable units.

    Dispatches to the appropriate chunker based on language/file_type.
    Falls back to sliding window chunking for unknown types.

    Args:
        content:       Full text content of the file.
        file_path:     Relative path (used for logging/debugging).
        language:      Detected language (e.g. "python", "typescript").
        file_type:     "code", "docs", "config", "other".
        max_tokens:    Maximum tokens per chunk.
        overlap_tokens: Token overlap between consecutive chunks (sliding window fallback).

    Returns:
        Ordered list of CodeChunk objects.
    """
    if not content or not content.strip():
        return []

    try:
        if language == "python":
            chunks = _chunk_python(content, max_tokens)
        elif language in ("javascript", "typescript"):
            chunks = _chunk_js_ts(content, language, max_tokens)
        elif file_type == "docs" or language in ("markdown", "restructuredtext", "text"):
            chunks = _chunk_markdown(content, max_tokens)
        elif file_type == "config":
            chunks = _chunk_config(content, language, max_tokens)
        else:
            # Generic fallback: structural chunking by blank lines, then sliding window
            chunks = _chunk_generic(content, max_tokens, overlap_tokens)

        # Safety: split any chunk that is still over the token limit.
        final: list[CodeChunk] = []
        for chunk in chunks:
            if chunk.token_count > max_tokens:
                final.extend(_split_oversized_chunk(chunk, max_tokens, overlap_tokens))
            else:
                final.append(chunk)

        # Re-index after final split
        for i, chunk in enumerate(final):
            chunk.chunk_index = i

        logger.debug(
            "File chunked",
            extra={"path": file_path, "chunks": len(final), "language": language},
        )
        return final

    except Exception as exc:
        logger.warning(
            "Chunking failed — falling back to sliding window",
            extra={"path": file_path, "language": language, "error": str(exc)},
        )
        return _chunk_generic(content, max_tokens, overlap_tokens)


# ── Python chunker ────────────────────────────────────────────────────────────

def _chunk_python(content: str, max_tokens: int) -> list[CodeChunk]:
    """
    Chunks Python source code along structural boundaries.

    Strategy:
      1. Parse using the `ast` module to find class and function definitions.
      2. Extract each top-level function as its own chunk.
      3. Extract each class as: header chunk + one chunk per method.
      4. Extract module-level docstring + imports as a context chunk.
      5. Extract remaining top-level code (constants, module-level statements).

    Falls back to line-based chunking if AST parsing fails.
    """
    try:
        import ast
        tree = ast.parse(content)
    except SyntaxError:
        logger.debug("Python AST parse failed — using line chunking")
        return _chunk_generic(content, max_tokens, max_tokens // 4)

    lines = content.splitlines(keepends=True)
    chunks: list[CodeChunk] = []
    covered_lines: set[int] = set()

    def get_source(node) -> tuple[str, int, int]:
        """Extracts source text for an AST node."""
        start = node.lineno
        end = node.end_lineno
        src = "".join(lines[start - 1:end])
        return src, start, end

    def mark_covered(start: int, end: int):
        for ln in range(start, end + 1):
            covered_lines.add(ln)

    idx = 0

    # ── Module docstring + imports ────────────────────────────────────────────
    module_doc = ast.get_docstring(tree)
    import_lines = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            import_lines.append(node.lineno)

    if import_lines:
        min_import = min(import_lines)
        max_import = max(import_lines)
        # Include from line 1 up to last import line.
        header_src = "".join(lines[0:max_import])
        if header_src.strip():
            chunks.append(CodeChunk(
                content=header_src,
                chunk_type="module",
                chunk_name="module_header",
                chunk_index=idx,
                start_line=1,
                end_line=max_import,
            ))
            mark_covered(1, max_import)
            idx += 1

    # ── Top-level definitions ─────────────────────────────────────────────────
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
            src, start, end = get_source(node)
            chunks.append(CodeChunk(
                content=src,
                chunk_type="function",
                chunk_name=node.name,
                chunk_index=idx,
                start_line=start,
                end_line=end,
            ))
            mark_covered(start, end)
            idx += 1

        elif isinstance(node, ast.ClassDef):
            class_start = node.lineno
            class_end = node.end_lineno

            # Class header: decorators + class def line + class docstring
            class_header_end = class_start
            if (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)):
                class_header_end = node.body[0].end_lineno

            class_header_src = "".join(lines[class_start - 1:class_header_end])
            chunks.append(CodeChunk(
                content=class_header_src,
                chunk_type="class",
                chunk_name=node.name,
                chunk_index=idx,
                start_line=class_start,
                end_line=class_header_end,
            ))
            mark_covered(class_start, class_header_end)
            idx += 1

            # Each method in the class
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    src, start, end = get_source(child)
                    chunks.append(CodeChunk(
                        content=src,
                        chunk_type="method",
                        chunk_name=f"{node.name}.{child.name}",
                        chunk_index=idx,
                        start_line=start,
                        end_line=end,
                    ))
                    mark_covered(start, end)
                    idx += 1

    # ── Remaining uncovered lines (module-level code, constants) ─────────────
    remaining: list[str] = []
    remaining_start = None
    remaining_end = None
    for i, line in enumerate(lines, start=1):
        if i not in covered_lines and line.strip():
            if remaining_start is None:
                remaining_start = i
            remaining.append(line)
            remaining_end = i

    if remaining:
        chunks.append(CodeChunk(
            content="".join(remaining),
            chunk_type="block",
            chunk_name="module_body",
            chunk_index=idx,
            start_line=remaining_start or 1,
            end_line=remaining_end or 1,
        ))

    return chunks


# ── JavaScript / TypeScript chunker ──────────────────────────────────────────

def _chunk_js_ts(content: str, language: str, max_tokens: int) -> list[CodeChunk]:
    """
    Chunks JS/TS source along function and class boundaries using regex.

    Detects:
      - function declarations:   function foo(...) { ... }
      - arrow functions:         const foo = (...) => { ... }
      - class declarations:      class Foo { ... }
      - export default function: export default function() { ... }
      - async functions:         async function bar(...) { ... }
      - method shorthands:       methodName(...) { ... } (inside classes)

    Uses brace-counting to find the end of each block.
    Falls back to generic chunking if parsing is complex.
    """
    chunks: list[CodeChunk] = []
    lines = content.splitlines()
    idx = 0

    # Patterns for JS/TS structural boundaries
    patterns = [
        # Named function declaration
        (re.compile(r"^(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\("), "function"),
        # Arrow function assigned to const/let
        (re.compile(r"^(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\("), "function"),
        # Class declaration
        (re.compile(r"^(?:export\s+)?(?:abstract\s+)?class\s+(\w+)"), "class"),
        # Default export function
        (re.compile(r"^export\s+default\s+(?:async\s+)?function\s*(\w*)"), "function"),
    ]

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        matched = False

        for pattern, chunk_type in patterns:
            m = pattern.match(line)
            if m:
                name = m.group(1) if m.lastindex else None
                start_line = i + 1  # 1-indexed

                # Find the end of this block by counting braces
                block_lines = [lines[i]]
                depth = lines[i].count("{") - lines[i].count("}")
                j = i + 1
                while j < len(lines) and (depth > 0 or j == i + 1):
                    block_lines.append(lines[j])
                    depth += lines[j].count("{") - lines[j].count("}")
                    j += 1
                    if depth <= 0 and j > i + 1:
                        break

                end_line = j  # 1-indexed
                block_content = "\n".join(block_lines)

                chunks.append(CodeChunk(
                    content=block_content,
                    chunk_type=chunk_type,
                    chunk_name=name,
                    chunk_index=idx,
                    start_line=start_line,
                    end_line=end_line,
                ))
                idx += 1
                i = j
                matched = True
                break

        if not matched:
            i += 1

    if not chunks:
        return _chunk_generic(content, max_tokens, max_tokens // 4)

    return chunks


# ── Markdown / RST chunker ────────────────────────────────────────────────────

def _chunk_markdown(content: str, max_tokens: int) -> list[CodeChunk]:
    """
    Chunks Markdown (and RST) by heading boundaries.

    Each H1/H2/H3 section becomes one chunk.
    Large sections are further split at blank lines.
    """
    lines = content.splitlines(keepends=True)
    chunks: list[CodeChunk] = []
    idx = 0

    # Split at markdown headings (##, ###) or RST underlines
    heading_pattern = re.compile(r"^#{1,3}\s+.+", re.MULTILINE)

    section_starts = [0]
    for m in heading_pattern.finditer(content):
        line_num = content[:m.start()].count("\n")
        section_starts.append(line_num)
    section_starts.append(len(lines))

    for s in range(len(section_starts) - 1):
        start = section_starts[s]
        end = section_starts[s + 1]
        section_lines = lines[start:end]
        section_text = "".join(section_lines).strip()

        if not section_text:
            continue

        # Extract section heading as name
        first_line = section_lines[0].strip() if section_lines else ""
        name = re.sub(r"^#+\s*", "", first_line).strip() or "section"

        chunks.append(CodeChunk(
            content=section_text,
            chunk_type="doc_section",
            chunk_name=name[:100],  # Truncate very long headings
            chunk_index=idx,
            start_line=start + 1,
            end_line=end,
        ))
        idx += 1

    return chunks if chunks else _chunk_generic(content, max_tokens, max_tokens // 4)


# ── Config chunker ────────────────────────────────────────────────────────────

def _chunk_config(content: str, language: str | None, max_tokens: int) -> list[CodeChunk]:
    """
    Chunks config files (YAML, JSON, TOML) by top-level keys.

    If the whole file fits in max_tokens, keep it as one chunk.
    Otherwise split at top-level keys.
    """
    total_tokens = _count_tokens(content)
    if total_tokens <= max_tokens:
        return [CodeChunk(
            content=content,
            chunk_type="block",
            chunk_name="config",
            chunk_index=0,
            start_line=1,
            end_line=content.count("\n") + 1,
        )]

    # Split YAML/TOML at top-level keys (lines not indented)
    lines = content.splitlines(keepends=True)
    chunks: list[CodeChunk] = []
    idx = 0
    current: list[str] = []
    current_start = 1
    current_name = "config"

    for i, line in enumerate(lines, start=1):
        # Detect top-level key: line that starts without whitespace and has a colon
        if current and re.match(r"^[a-zA-Z_\"\'\[\{]", line) and ":" in line.split("#")[0]:
            if current:
                chunks.append(CodeChunk(
                    content="".join(current),
                    chunk_type="block",
                    chunk_name=current_name,
                    chunk_index=idx,
                    start_line=current_start,
                    end_line=i - 1,
                ))
                idx += 1
            current = [line]
            current_start = i
            current_name = line.split(":")[0].strip().strip('"\'')
        else:
            current.append(line)

    if current:
        chunks.append(CodeChunk(
            content="".join(current),
            chunk_type="block",
            chunk_name=current_name,
            chunk_index=idx,
            start_line=current_start,
            end_line=len(lines),
        ))

    return chunks if chunks else _chunk_generic(content, max_tokens, max_tokens // 4)


# ── Generic sliding window chunker ────────────────────────────────────────────

def _chunk_generic(
    content: str,
    max_tokens: int,
    overlap_tokens: int,
) -> list[CodeChunk]:
    """
    Fallback chunker: splits at blank lines, then applies sliding window.

    Tries to break at blank lines first (preserves paragraph/block structure).
    Falls back to hard token-based split if paragraphs are too large.
    """
    lines = content.splitlines(keepends=True)
    chunks: list[CodeChunk] = []
    idx = 0

    # Group into blocks separated by blank lines
    blocks: list[tuple[list[str], int, int]] = []  # (lines, start_1idx, end_1idx)
    current_block: list[str] = []
    current_start = 1
    for i, line in enumerate(lines, start=1):
        if line.strip():
            current_block.append(line)
        else:
            if current_block:
                blocks.append((current_block[:], current_start, i - 1))
                current_block = []
                current_start = i + 1
    if current_block:
        blocks.append((current_block, current_start, len(lines)))

    # Merge small blocks into chunks up to max_tokens
    current_lines: list[str] = []
    current_start_line = 1
    current_end_line = 1
    current_tokens = 0

    for block_lines, blk_start, blk_end in blocks:
        block_text = "".join(block_lines)
        block_tokens = _count_tokens(block_text)

        if current_tokens + block_tokens > max_tokens and current_lines:
            # Flush current accumulator
            text = "".join(current_lines)
            chunks.append(CodeChunk(
                content=text,
                chunk_type="block",
                chunk_name=None,
                chunk_index=idx,
                start_line=current_start_line,
                end_line=current_end_line,
            ))
            idx += 1
            # Start new with overlap — take last `overlap_tokens` worth of content
            overlap_text = _tail_tokens(text, overlap_tokens)
            current_lines = [overlap_text]
            current_tokens = _count_tokens(overlap_text)
            current_start_line = blk_start

        if block_tokens > max_tokens:
            # Block itself is too large — hard split by lines
            sub_chunks = _hard_split(block_lines, blk_start, max_tokens, idx)
            chunks.extend(sub_chunks)
            idx += len(sub_chunks)
            current_lines = []
            current_tokens = 0
            current_start_line = blk_end + 1
        else:
            current_lines.extend(block_lines)
            current_tokens += block_tokens
            current_end_line = blk_end

    if current_lines:
        chunks.append(CodeChunk(
            content="".join(current_lines),
            chunk_type="block",
            chunk_name=None,
            chunk_index=idx,
            start_line=current_start_line,
            end_line=current_end_line,
        ))

    return chunks


def _hard_split(
    lines: list[str],
    start_line: int,
    max_tokens: int,
    start_idx: int,
) -> list[CodeChunk]:
    """Splits a list of lines into chunks of at most max_tokens."""
    chunks: list[CodeChunk] = []
    current: list[str] = []
    current_tokens = 0
    idx = start_idx
    chunk_start = start_line

    for i, line in enumerate(lines):
        lt = _count_tokens(line)
        if lt > max_tokens:
            # Single line exceeds max_tokens — flush current and slice the line
            if current:
                chunks.append(CodeChunk(
                    content="".join(current),
                    chunk_type="block",
                    chunk_name=None,
                    chunk_index=idx,
                    start_line=chunk_start,
                    end_line=start_line + i - 1,
                ))
                idx += 1
                current = []
                current_tokens = 0

            char_step = max(max_tokens * 3, 100)
            for c_start in range(0, len(line), char_step):
                segment = line[c_start:c_start + char_step]
                chunks.append(CodeChunk(
                    content=segment,
                    chunk_type="block",
                    chunk_name=None,
                    chunk_index=idx,
                    start_line=start_line + i,
                    end_line=start_line + i,
                ))
                idx += 1
            chunk_start = start_line + i + 1
            continue

        if current_tokens + lt > max_tokens and current:
            chunks.append(CodeChunk(
                content="".join(current),
                chunk_type="block",
                chunk_name=None,
                chunk_index=idx,
                start_line=chunk_start,
                end_line=start_line + i - 1,
            ))
            idx += 1
            current = [line]
            current_tokens = lt
            chunk_start = start_line + i
        else:
            current.append(line)
            current_tokens += lt

    if current:
        chunks.append(CodeChunk(
            content="".join(current),
            chunk_type="block",
            chunk_name=None,
            chunk_index=idx,
            start_line=chunk_start,
            end_line=start_line + len(lines) - 1,
        ))

    return chunks


def _tail_tokens(text: str, n_tokens: int) -> str:
    """Returns the last n_tokens worth of text (approximate)."""
    tokenizer = _get_tokenizer()
    if tokenizer:
        tokens = tokenizer.encode(text)
        tail = tokens[-n_tokens:]
        return tokenizer.decode(tail)
    # Fallback: chars
    char_count = n_tokens * 4
    return text[-char_count:]


def _split_oversized_chunk(
    chunk: CodeChunk,
    max_tokens: int,
    overlap_tokens: int,
) -> list[CodeChunk]:
    """Splits a single chunk that exceeds max_tokens into smaller sub-chunks."""
    sub = _chunk_generic(chunk.content, max_tokens, overlap_tokens)
    for i, s in enumerate(sub):
        s.chunk_type = chunk.chunk_type
        s.chunk_name = chunk.chunk_name
        # Adjust line numbers relative to original chunk
        offset = chunk.start_line - 1
        s.start_line = s.start_line + offset
        s.end_line = s.end_line + offset
    return sub
