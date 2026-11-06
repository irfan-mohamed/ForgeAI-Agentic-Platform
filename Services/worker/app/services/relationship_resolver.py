"""
relationship_resolver.py — Cross-file relationship resolution pass.

After all files in a repository sync have been symbol-extracted, most
`code_relationships` rows with relationship_type=IMPORTS or CALLS have
`target_symbol_id=NULL` because they reference symbols in OTHER files.

This module runs a batch resolution pass over the entire repository:
  1. Build a lookup: (repository_id, symbol_name) → symbol_id.
  2. Load all unresolved relationships via raw SQL.
  3. Match each target_symbol_name against the lookup using two strategies.
  4. Bulk-update target_symbol_id + is_resolved=True for matched rows.

Resolution strategies (in priority order):
  A. File-scoped: symbol_name exists in target_file_path (most precise).
  B. Name-only:   first symbol with that name anywhere in the repo.
  C. Unresolved:  leave target_symbol_id=NULL (is_resolved stays False).

Why a batch pass instead of per-file?
  Per-file extraction can only resolve intra-file calls. The resolver runs
  after ALL files are indexed, so it has the full cross-file symbol map.

Owned by: Worker Service.
"""

from __future__ import annotations

import logging
from collections import defaultdict

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.database import get_db_session

logger = logging.getLogger(__name__)


# ── Public entry point ────────────────────────────────────────────────────────

def resolve_relationships(
    repository_id: int,
    organization_id: int,
    commit_sha: str | None = None,
) -> dict[str, int]:
    """
    Run the cross-file relationship resolution pass for one repository.

    Should be called after all files have been indexed in a sync pass.

    Returns:
        Dict with keys: resolved, unresolved, skipped
    """
    stats = {"resolved": 0, "unresolved": 0, "skipped": 0}

    with get_db_session() as db:
        # ── Step 1: Build complete symbol lookup for this repo ────────────────
        symbol_map = _build_symbol_map(db, repository_id)

        if not symbol_map.by_name:
            logger.info(
                "No symbols found for repository — skipping resolution",
                extra={"repository_id": repository_id},
            )
            return stats

        # ── Step 2: Load all unresolved relationships via raw SQL ─────────────
        rel_filter = "AND commit_sha = :commit_sha" if commit_sha else ""
        params: dict = {"repo_id": repository_id}
        if commit_sha:
            params["commit_sha"] = commit_sha

        rows = db.execute(
            text(f"""
                SELECT id, target_symbol_name, target_file_path
                FROM code_relationships
                WHERE
                    repository_id = :repo_id
                    AND is_resolved = FALSE
                    AND target_symbol_name IS NOT NULL
                    {rel_filter}
            """),
            params,
        ).fetchall()

        logger.info(
            "Starting relationship resolution",
            extra={
                "repository_id": repository_id,
                "unresolved_count": len(rows),
                "symbol_map_size": sum(len(v) for v in symbol_map.by_name.values()),
            },
        )

        # ── Step 3: Resolve each relationship ─────────────────────────────────
        resolved_ids: list[tuple[int, int]] = []

        for row in rows:
            m = row._mapping
            rel_id = m["id"]
            target_name = m["target_symbol_name"]
            target_file = m["target_file_path"]

            # Strategy A: file-scoped match (most precise)
            target_id = _resolve_by_file_and_name(symbol_map, target_name, target_file)
            # Strategy B: name-only match (broader)
            if target_id is None:
                target_id = _resolve_by_name(symbol_map, target_name)

            if target_id is not None:
                resolved_ids.append((rel_id, target_id))
                stats["resolved"] += 1
            else:
                stats["unresolved"] += 1

        # ── Step 4: Bulk-update resolved rows ─────────────────────────────────
        for rel_id, target_id in resolved_ids:
            db.execute(
                text("""
                    UPDATE code_relationships
                    SET target_symbol_id = :tgt_id, is_resolved = TRUE
                    WHERE id = :rel_id
                """),
                {"tgt_id": target_id, "rel_id": rel_id},
            )

        if resolved_ids:
            db.commit()

        logger.info(
            "Relationship resolution complete",
            extra={"repository_id": repository_id, **stats},
        )

    return stats


# ── Symbol map ────────────────────────────────────────────────────────────────

class _SymbolMap:
    """In-memory index of all symbols in a repository."""
    __slots__ = ("by_name", "by_file_and_name", "by_qualified_name")

    def __init__(self):
        # symbol_name → [symbol_id, ...]  (multiple symbols can share a name)
        self.by_name: dict[str, list[int]] = defaultdict(list)
        # (file_path, symbol_name) → symbol_id  (unique per file)
        self.by_file_and_name: dict[tuple[str, str], int] = {}
        # qualified_name → symbol_id
        self.by_qualified_name: dict[str, int] = {}


def _build_symbol_map(db: Session, repo_id: int) -> _SymbolMap:
    """Builds the full in-memory symbol index for one repository."""
    rows = db.execute(
        text("""
            SELECT id, symbol_name, qualified_name, file_path
            FROM code_symbols
            WHERE repository_id = :repo_id
        """),
        {"repo_id": repo_id},
    ).fetchall()

    sym_map = _SymbolMap()
    for row in rows:
        m = row._mapping
        sym_id = m["id"]
        sym_name = m["symbol_name"]
        file_path = m["file_path"]
        qualified = m["qualified_name"]

        sym_map.by_name[sym_name].append(sym_id)
        sym_map.by_file_and_name[(file_path, sym_name)] = sym_id
        if qualified:
            sym_map.by_qualified_name[qualified] = sym_id

    return sym_map


def _resolve_by_file_and_name(
    sym_map: _SymbolMap,
    target_name: str | None,
    target_file: str | None,
) -> int | None:
    """Returns the symbol_id if we have an exact (file, name) match.

    Also tries common JS/TS extension variants for extension-less import paths.
    """
    if not target_name or not target_file:
        return None

    # Try exact file path
    result = sym_map.by_file_and_name.get((target_file, target_name))
    if result:
        return result

    # JS/TS: imports often omit the extension ("./auth" → "auth.ts")
    for ext in (".ts", ".tsx", ".js", ".jsx"):
        candidate = sym_map.by_file_and_name.get((target_file + ext, target_name))
        if candidate:
            return candidate

    # Barrel imports: "./auth" → "./auth/index.ts"
    for ext in ("/index.ts", "/index.js", "/index.tsx"):
        candidate = sym_map.by_file_and_name.get((target_file + ext, target_name))
        if candidate:
            return candidate

    return None


def _resolve_by_name(sym_map: _SymbolMap, target_name: str | None) -> int | None:
    """Returns the symbol_id for a name-only match.

    Tries qualified name first, then simple name, then last dotted segment.
    If multiple symbols share the same name, returns the first.
    """
    if not target_name:
        return None

    # Try qualified name (e.g. "UserService.login")
    result = sym_map.by_qualified_name.get(target_name)
    if result:
        return result

    # Try simple name
    matches = sym_map.by_name.get(target_name)
    if matches:
        return matches[0]

    # Try last dotted segment ("auth.login" → "login")
    if "." in target_name:
        simple = target_name.split(".")[-1]
        matches = sym_map.by_name.get(simple)
        if matches:
            return matches[0]

    return None


# ── Relationship statistics ───────────────────────────────────────────────────

def get_resolution_stats(repository_id: int) -> dict[str, int]:
    """Returns current resolution statistics for a repository."""
    with get_db_session() as db:
        rows = db.execute(
            text("""
                SELECT
                    relationship_type,
                    is_resolved,
                    COUNT(*) AS cnt
                FROM code_relationships
                WHERE repository_id = :repo_id
                GROUP BY relationship_type, is_resolved
                ORDER BY relationship_type, is_resolved
            """),
            {"repo_id": repository_id},
        ).fetchall()

    result: dict[str, int] = {"total": 0, "resolved": 0, "unresolved": 0}
    for row in rows:
        m = row._mapping
        count = m["cnt"]
        result["total"] += count
        if m["is_resolved"]:
            result["resolved"] += count
        else:
            result["unresolved"] += count

    return result
