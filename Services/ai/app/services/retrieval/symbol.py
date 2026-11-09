"""
symbol.py — SymbolRetriever backed by code_symbols and code_relationships graph.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text

from app.db.database import db_session
from app.services.retrieval.base import RetrievalResult, Retriever

logger = logging.getLogger(__name__)


class SymbolRetriever(Retriever):
    """
    Direct graph retrieval over code_symbols and code_relationships.
    Finds exact definitions, callers, callees, and routes.
    """

    def search(
        self,
        query: str,
        org_id: int,
        repository_id: int,
        top_k: int = 8,
        **kwargs: Any,
    ) -> list[RetrievalResult]:
        clean_name = query.strip().split(".")[-1].strip("()`'\"")
        results: list[RetrievalResult] = []

        try:
            with db_session() as db:
                # 1. Exact or prefix symbol match
                rows = db.execute(
                    text("""
                        SELECT
                            id, symbol_name, qualified_name, symbol_type, file_path,
                            start_line, end_line, language, signature, docstring
                        FROM code_symbols
                        WHERE
                            organization_id = :org_id
                            AND repository_id = :repo_id
                            AND (
                                LOWER(symbol_name) = LOWER(:clean_name)
                                OR LOWER(qualified_name) = LOWER(:clean_name)
                                OR symbol_name LIKE :like_name
                            )
                        ORDER BY
                            CASE WHEN LOWER(symbol_name) = LOWER(:clean_name) THEN 0
                                 WHEN symbol_name LIKE :prefix_name THEN 1
                                 ELSE 2 END,
                            start_line ASC
                        LIMIT :limit
                    """),
                    {
                        "org_id": org_id,
                        "repo_id": repository_id,
                        "clean_name": clean_name,
                        "like_name": f"%{clean_name}%",
                        "prefix_name": f"{clean_name}%",
                        "limit": top_k,
                    },
                ).fetchall()

                for row in rows:
                    m = row._mapping
                    content_parts = []
                    if m.get("signature"):
                        content_parts.append(m["signature"])
                    if m.get("docstring"):
                        content_parts.append(f'"""{m["docstring"]}"""')
                    content = "\n".join(content_parts) or m.get("symbol_name", "")

                    results.append(
                        RetrievalResult(
                            chunk_id=f"sym:{m['id']}",
                            file_path=m.get("file_path", ""),
                            content=content,
                            start_line=m.get("start_line", 0) or 0,
                            end_line=m.get("end_line", 0) or 0,
                            language=m.get("language") or "",
                            chunk_type=m.get("symbol_type") or "symbol",
                            score=1.0 if m.get("symbol_name", "").lower() == clean_name.lower() else 0.8,
                            sources=["symbol"],
                            symbol_name=m.get("symbol_name"),
                            symbol_type=m.get("symbol_type"),
                            signature=m.get("signature"),
                        )
                    )

        except Exception as exc:
            logger.warning("SymbolRetriever query failed", extra={"error": str(exc)})

        return results[:top_k]
