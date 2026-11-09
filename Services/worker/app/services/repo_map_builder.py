"""
repo_map_builder.py — Aggregates file tree, symbols, routes, imports, and docs into a stored repo map.

Runs during Worker sync Phase 8 so the repository becomes chat-ready before
the slower dense vector embedding phase completes.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import get_db_session
from app.models.code_relationship import CodeRelationship
from app.models.code_symbol import CodeSymbol
from app.models.repo_map import RepositoryMap
from app.models.repository_file import RepositoryFile

logger = logging.getLogger(__name__)

_TEST_FILE_PATTERN = re.compile(
    r"(?:^|/)(?:tests?/|__tests__/|test_[^/]+\.py$|[^/]+_test\.py$|[^/]+\.(?:test|spec)\.[a-zA-Z0-9]+$)",
    re.IGNORECASE,
)
_DOC_FILE_PATTERN = re.compile(
    r"(?:^|/)(?:README.*|docs?/.*|\.github/.*\.md$|.*\.md$)",
    re.IGNORECASE,
)


def is_test_file(path: str) -> bool:
    return bool(_TEST_FILE_PATTERN.search(path.replace("\\", "/")))


def is_doc_file(path: str) -> bool:
    return bool(_DOC_FILE_PATTERN.search(path.replace("\\", "/")))


def generate_repo_map_markdown(
    repo_name: str,
    commit_sha: str | None,
    languages: dict[str, Any],
    routes: list[dict[str, Any]],
    symbols_summary: list[dict[str, Any]],
    imports: list[dict[str, Any]],
    test_files: list[str],
    doc_files: list[str],
    total_files: int,
) -> str:
    """Renders a concise, human-and-LLM readable markdown representation."""
    lines: list[str] = [
        f"# Repository Map: {repo_name or 'Repository'}",
        f"**Commit**: `{commit_sha or 'HEAD'}` | **Total Files**: {total_files}",
        "",
        "## Languages",
    ]

    if languages:
        for lang, stats in sorted(
            languages.items(),
            key=lambda x: x[1].get("files", 0) if isinstance(x[1], dict) else x[1],
            reverse=True,
        ):
            if isinstance(stats, dict):
                count = stats.get("files", 0)
                lines.append(f"- **{lang}**: {count} files")
            else:
                lines.append(f"- **{lang}**: {stats} files")
    else:
        lines.append("- (No categorized language files)")

    lines.append("")
    lines.append("## HTTP Routes & Endpoints")
    if routes:
        for r in routes[:25]:
            handler = f" → `{r.get('handler_name')}`" if r.get("handler_name") else ""
            lines.append(f"- `{r.get('symbol_name')}` in `{r.get('file_path')}`{handler}")
        if len(routes) > 25:
            lines.append(f"- ... and {len(routes) - 25} more routes")
    else:
        lines.append("- None detected")

    lines.append("")
    lines.append("## Core Components & Key Symbols")
    if symbols_summary:
        by_file: dict[str, list[str]] = {}
        for s in symbols_summary[:60]:
            fp = s.get("file_path", "")
            sig = s.get("signature") or s.get("name")
            stype = s.get("type", "symbol")
            by_file.setdefault(fp, []).append(f"{stype} `{sig}`")

        for fp, sym_list in list(by_file.items())[:20]:
            lines.append(f"- `{fp}`: {', '.join(sym_list[:5])}")
        if len(by_file) > 20:
            lines.append(f"- ... and {len(by_file) - 20} more files with symbols")
    else:
        lines.append("- (No code symbols extracted)")

    lines.append("")
    lines.append("## Test Suite")
    if test_files:
        for tf in test_files[:20]:
            lines.append(f"- `{tf}`")
        if len(test_files) > 20:
            lines.append(f"- ... and {len(test_files) - 20} more test files")
    else:
        lines.append("- (No test files detected)")

    lines.append("")
    lines.append("## Documentation")
    if doc_files:
        for df in doc_files[:15]:
            lines.append(f"- `{df}`")
    else:
        lines.append("- (No docs detected)")

    return "\n".join(lines)


def build_repo_map(
    db: Session,
    organization_id: int,
    repository_id: int,
    commit_sha: str | None = None,
    repo_name: str = "",
) -> RepositoryMap:
    """
    Scans the database tables for this repo and constructs/persists the RepositoryMap.
    """
    logger.info(
        "Building repository map",
        extra={"org_id": organization_id, "repo_id": repository_id},
    )

    # 1. Files & Languages
    files = (
        db.query(RepositoryFile)
        .filter(
            RepositoryFile.organization_id == organization_id,
            RepositoryFile.repository_id == repository_id,
        )
        .order_by(RepositoryFile.path)
        .all()
    )

    file_tree: list[dict[str, Any]] = []
    languages: dict[str, dict[str, int]] = {}
    test_files: list[str] = []
    doc_files: list[str] = []

    for f in files:
        file_tree.append(
            {
                "path": f.path,
                "size": f.size_bytes,
                "language": f.language,
                "type": f.file_type,
                "indexed": f.is_indexed,
            }
        )
        if f.language:
            lang_stat = languages.setdefault(f.language, {"files": 0, "bytes": 0})
            lang_stat["files"] += 1
            lang_stat["bytes"] += f.size_bytes or 0

        if is_test_file(f.path):
            test_files.append(f.path)
        if is_doc_file(f.path):
            doc_files.append(f.path)

    # 2. Key Symbols
    symbols = (
        db.query(CodeSymbol)
        .filter(
            CodeSymbol.organization_id == organization_id,
            CodeSymbol.repository_id == repository_id,
            CodeSymbol.symbol_type.in_(["class", "function", "interface", "struct", "route"]),
        )
        .order_by(CodeSymbol.file_path, CodeSymbol.start_line)
        .limit(200)
        .all()
    )

    symbols_summary: list[dict[str, Any]] = [
        {
            "id": s.id,
            "name": s.symbol_name,
            "qualified_name": s.qualified_name,
            "type": s.symbol_type,
            "file_path": s.file_path,
            "start_line": s.start_line,
            "signature": s.signature,
            "is_async": s.is_async,
            "is_exported": s.is_exported,
        }
        for s in symbols
    ]

    # 3. HTTP Routes
    route_symbols = (
        db.query(CodeSymbol)
        .filter(
            CodeSymbol.organization_id == organization_id,
            CodeSymbol.repository_id == repository_id,
            CodeSymbol.symbol_type == "route",
        )
        .order_by(CodeSymbol.file_path, CodeSymbol.start_line)
        .all()
    )

    routes: list[dict[str, Any]] = []
    for r in route_symbols:
        # Check for HANDLES edge to resolve handler name
        rel = (
            db.query(CodeRelationship)
            .filter(
                CodeRelationship.organization_id == organization_id,
                CodeRelationship.repository_id == repository_id,
                CodeRelationship.source_symbol_id == r.id,
                CodeRelationship.relationship_type == "HANDLES",
            )
            .first()
        )
        handler_name = None
        if rel and rel.target_symbol_id:
            target = db.get(CodeSymbol, rel.target_symbol_id)
            if target:
                handler_name = target.symbol_name

        routes.append(
            {
                "symbol_name": r.symbol_name,
                "file_path": r.file_path,
                "start_line": r.start_line,
                "signature": r.signature,
                "handler_name": handler_name,
            }
        )

    # 4. Imports & Dependency graph
    import_rels = (
        db.query(CodeRelationship)
        .filter(
            CodeRelationship.organization_id == organization_id,
            CodeRelationship.repository_id == repository_id,
            CodeRelationship.relationship_type == "IMPORTS",
        )
        .limit(300)
        .all()
    )

    imports: list[dict[str, Any]] = [
        {
            "source_file": rel.source_file_path,
            "target_file": rel.target_file_path,
            "line": rel.source_line,
        }
        for rel in import_rels
        if rel.source_file_path and rel.target_file_path
    ]

    # 5. Raw Markdown rendering
    raw_markdown = generate_repo_map_markdown(
        repo_name=repo_name,
        commit_sha=commit_sha,
        languages=languages,
        routes=routes,
        symbols_summary=symbols_summary,
        imports=imports,
        test_files=test_files,
        doc_files=doc_files,
        total_files=len(files),
    )

    # 6. Upsert into repository_maps
    existing = (
        db.query(RepositoryMap)
        .filter(
            RepositoryMap.organization_id == organization_id,
            RepositoryMap.repository_id == repository_id,
        )
        .first()
    )

    now = datetime.now(timezone.utc)
    if existing:
        existing.commit_sha = commit_sha
        existing.file_tree = file_tree
        existing.languages = languages
        existing.symbols_summary = symbols_summary
        existing.imports = imports
        existing.routes = routes
        existing.test_files = test_files
        existing.doc_files = doc_files
        existing.raw_markdown = raw_markdown
        existing.updated_at = now
        map_record = existing
    else:
        map_record = RepositoryMap(
            organization_id=organization_id,
            repository_id=repository_id,
            commit_sha=commit_sha,
            file_tree=file_tree,
            languages=languages,
            symbols_summary=symbols_summary,
            imports=imports,
            routes=routes,
            test_files=test_files,
            doc_files=doc_files,
            raw_markdown=raw_markdown,
            created_at=now,
            updated_at=now,
        )
        db.add(map_record)

    db.commit()
    db.refresh(map_record)

    logger.info(
        "Repository map generated and stored",
        extra={
            "org_id": organization_id,
            "repo_id": repository_id,
            "files": len(files),
            "symbols": len(symbols_summary),
            "routes": len(routes),
        },
    )
    return map_record
