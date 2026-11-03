"""
sync_service.py — The core orchestrator for repository synchronization.

This is the brain of the Worker Service. It coordinates:
  1. Marking sync as RUNNING in PostgreSQL
  2. Getting an installation access token from GitHub
  3. Cloning or updating the repository locally
  4. Discovering all files in the clone
  5. Classifying files (index? skip? language?)
  6. Change detection (checksum comparison to skip unchanged files)
  7. Chunking each indexable file intelligently by structure
  8. Generating embeddings in batches
  9. Upserting vectors into Qdrant
  10. Recording knowledge metadata in PostgreSQL
  11. Cleaning up the local clone
  12. Marking sync as COMPLETED and repository as READY

On any failure:
  - The sync is marked FAILED with the error message.
  - The repository status is set to FAILED.
  - The local clone is cleaned up.

This class runs SYNCHRONOUSLY inside asyncio.to_thread() because
Git operations and file I/O are blocking.
"""

import hashlib
import logging
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import get_db_session
from app.models.mirrors import (
    Repository, RepositorySync, GitHubInstallation,
    SyncStatus, RepositoryStatus,
)
from app.models.repository_file import RepositoryFile, FileStatus
from app.models.repository_knowledge import RepositoryKnowledge
from app.models.code_symbol import CodeSymbol
from app.models.code_relationship import CodeRelationship
from app.services import github_service
from app.services.file_filter import classify_file, compute_checksum, MAX_FILE_SIZE_BYTES
from app.services.chunker import chunk_file, CodeChunk
from app.services import embedder
from app.services import vector_store
from app.services import symbol_extractor
from app.services import relationship_resolver

logger = logging.getLogger(__name__)

# How many chunks to embed and upsert in one batch
EMBED_BATCH_SIZE = 50


class SyncService:
    """
    Executes a full repository synchronization job.

    One instance per sync job. Stateless between runs.
    """

    def run_sync(
        self,
        organization_id: int,
        repository_id: int,
        sync_id: int,
    ) -> None:
        """
        Main entry point for a sync job.

        Orchestrates all sync phases. On any failure, marks the sync and
        repository as FAILED and cleans up the clone directory.
        """
        clone_dir: str | None = None

        try:
            # ── Ensure Qdrant collection is ready with matching dimensions ────
            try:
                vector_store.ensure_collection_exists()
            except Exception as exc:
                logger.warning(
                    "Qdrant collection verification warning",
                    extra={"sync_id": sync_id, "error": str(exc)},
                )

            # ── Phase 1: Mark sync as RUNNING ─────────────────────────────────
            with get_db_session() as db:
                sync, repo, installation = self._load_and_start(
                    db, sync_id, repository_id, organization_id
                )
                github_installation_id = installation.github_installation_id
                full_name = repo.full_name
                default_branch = repo.default_branch
                owner = repo.owner

            logger.info(
                "Sync job started",
                extra={
                    "sync_id": sync_id,
                    "repo_id": repository_id,
                    "full_name": full_name,
                },
            )

            # ── Phase 2: Get GitHub installation token ─────────────────────────
            token = github_service.get_installation_access_token(github_installation_id)

            # ── Phase 3: Get latest commit SHA ─────────────────────────────────
            try:
                commit_sha = github_service.get_latest_commit_sha(
                    token, owner, full_name.split("/")[1], default_branch
                )
            except Exception as exc:
                logger.warning(
                    "Could not fetch commit SHA — proceeding without it",
                    extra={"error": str(exc)},
                )
                commit_sha = None

            # Update sync record with commit SHA
            with get_db_session() as db:
                sync_record = db.get(RepositorySync, sync_id)
                if sync_record:
                    sync_record.commit_sha = commit_sha
                    db.commit()

            # ── Phase 4: Clone repository ──────────────────────────────────────
            clone_url = github_service.build_clone_url(token, full_name)
            clone_dir = self._clone_repository(clone_url, full_name, default_branch)

            # ── Phase 5: Discover files ────────────────────────────────────────
            all_files = self._discover_files(clone_dir)
            total_discovered = len(all_files)

            logger.info(
                "Files discovered in repository",
                extra={
                    "sync_id": sync_id,
                    "repo_id": repository_id,
                    "files_discovered": total_discovered,
                },
            )

            # Update progress: files_discovered
            with get_db_session() as db:
                sync_record = db.get(RepositorySync, sync_id)
                if sync_record:
                    sync_record.files_discovered = total_discovered
                    db.commit()

            # ── Phase 6: Mark repository as SYNCING ────────────────────────────
            with get_db_session() as db:
                repo_record = db.get(Repository, repository_id)
                if repo_record:
                    repo_record.status = RepositoryStatus.SYNCING.value
                    repo_record.updated_at = datetime.now(timezone.utc)
                    db.commit()

            # ── Phase 7: Process files ─────────────────────────────────────────
            files_processed = 0
            files_failed = 0

            for file_path, file_abs_path in all_files:
                try:
                    processed = self._process_file(
                        db_organization_id=organization_id,
                        repository_id=repository_id,
                        file_path=file_path,
                        file_abs_path=file_abs_path,
                        commit_sha=commit_sha,
                    )
                    if processed:
                        files_processed += 1
                except Exception as exc:
                    logger.warning(
                        "File processing failed — skipping",
                        extra={
                            "file_path": file_path,
                            "error": str(exc),
                        },
                    )
                    files_failed += 1
                    self._mark_file_failed(
                        organization_id=organization_id,
                        repository_id=repository_id,
                        file_path=file_path,
                        error=str(exc),
                    )

                # Update progress counters periodically (every 10 files)
                if (files_processed + files_failed) % 10 == 0:
                    self._update_progress(
                        sync_id=sync_id,
                        files_discovered=total_discovered,
                        files_processed=files_processed,
                        files_failed=files_failed,
                    )

            # ── Phase 8: Mark repository as INDEXING ───────────────────────────
            with get_db_session() as db:
                repo_record = db.get(Repository, repository_id)
                if repo_record:
                    repo_record.status = RepositoryStatus.INDEXING.value
                    repo_record.updated_at = datetime.now(timezone.utc)
                    db.commit()

            # ── Phase 8.5: Cross-file relationship resolution ──────────────────
            # All files have been symbol-extracted — now resolve cross-file
            # IMPORTS and CALLS to their actual target symbol IDs.
            logger.info(
                "Running cross-file relationship resolution",
                extra={"sync_id": sync_id, "repo_id": repository_id},
            )
            try:
                rel_stats = relationship_resolver.resolve_relationships(
                    repository_id=repository_id,
                    organization_id=organization_id,
                    commit_sha=commit_sha,
                )
                logger.info(
                    "Relationship resolution complete",
                    extra={"sync_id": sync_id, "repo_id": repository_id, **rel_stats},
                )
            except Exception as exc:
                # Non-fatal — repo is still usable without resolved relationships
                logger.warning(
                    "Relationship resolution failed (non-fatal)",
                    extra={"sync_id": sync_id, "error": str(exc)},
                )

            # ── Phase 9: Mark sync COMPLETED, repo READY ───────────────────────
            with get_db_session() as db:
                sync_record = db.get(RepositorySync, sync_id)
                if sync_record:
                    sync_record.status = SyncStatus.COMPLETED.value
                    sync_record.completed_at = datetime.now(timezone.utc)
                    sync_record.files_discovered = total_discovered
                    sync_record.files_processed = files_processed
                    sync_record.files_failed = files_failed
                    db.commit()

                repo_record = db.get(Repository, repository_id)
                if repo_record:
                    repo_record.status = RepositoryStatus.READY.value
                    repo_record.last_synced_at = datetime.now(timezone.utc)
                    repo_record.updated_at = datetime.now(timezone.utc)
                    db.commit()

            logger.info(
                "Sync completed successfully",
                extra={
                    "sync_id": sync_id,
                    "repo_id": repository_id,
                    "files_processed": files_processed,
                    "files_failed": files_failed,
                },
            )

        except Exception as exc:
            logger.exception(
                "Sync job failed",
                extra={"sync_id": sync_id, "repo_id": repository_id, "error": str(exc)},
            )
            self._mark_failed(
                sync_id=sync_id,
                repository_id=repository_id,
                error_message=str(exc),
            )

        finally:
            # Always clean up the clone directory
            if clone_dir and os.path.exists(clone_dir):
                try:
                    shutil.rmtree(clone_dir)
                    logger.debug("Clone directory cleaned up", extra={"path": clone_dir})
                except Exception as exc:
                    logger.warning(
                        "Failed to clean up clone directory",
                        extra={"path": clone_dir, "error": str(exc)},
                    )

    # ── Phase helpers ─────────────────────────────────────────────────────────

    def _load_and_start(
        self,
        db: Session,
        sync_id: int,
        repository_id: int,
        organization_id: int,
    ) -> tuple[RepositorySync, Repository, GitHubInstallation]:
        """
        Loads the sync/repo/installation records and marks the sync as RUNNING.
        Raises RuntimeError if any record is missing or sync is already running.
        """
        sync = db.get(RepositorySync, sync_id)
        if not sync:
            raise RuntimeError(f"RepositorySync {sync_id} not found")

        if sync.status == SyncStatus.RUNNING.value:
            raise RuntimeError(f"Sync {sync_id} is already RUNNING — duplicate event")

        repo = db.get(Repository, repository_id)
        if not repo:
            raise RuntimeError(f"Repository {repository_id} not found")

        installation = (
            db.query(GitHubInstallation)
            .filter(GitHubInstallation.id == repo.github_installation_id)
            .first()
        )
        if not installation:
            raise RuntimeError(
                f"GitHubInstallation not found for repository {repository_id}"
            )

        # Mark sync as RUNNING
        sync.status = SyncStatus.RUNNING.value
        sync.started_at = datetime.now(timezone.utc)
        db.commit()

        return sync, repo, installation

    def _clone_repository(
        self,
        clone_url: str,
        full_name: str,
        branch: str,
    ) -> str:
        """
        Clones the repository to a temporary directory.

        Uses shallow clone (--depth 1) to minimize download size.
        Only clones the default branch.

        Returns the path to the cloned repository directory.
        """
        import git as gitpython

        # Create a unique temp directory for this clone
        base_dir = settings.CLONE_BASE_DIR
        os.makedirs(base_dir, exist_ok=True)

        # Sanitize full_name for use as a directory name
        safe_name = full_name.replace("/", "_").replace(".", "_")
        clone_dir = os.path.join(base_dir, f"{safe_name}_{id(self)}")

        logger.info(
            "Cloning repository",
            extra={"full_name": full_name, "branch": branch, "dest": clone_dir},
        )

        gitpython.Repo.clone_from(
            clone_url,
            clone_dir,
            branch=branch,
            depth=1,            # Shallow clone — only latest commit
            single_branch=True, # Only the specified branch
        )

        logger.info(
            "Repository cloned successfully",
            extra={"full_name": full_name, "clone_dir": clone_dir},
        )
        return clone_dir

    def _discover_files(self, clone_dir: str) -> list[tuple[str, str]]:
        """
        Walks the cloned directory and returns all files.

        Returns a list of (relative_path, absolute_path) tuples.
        """
        files: list[tuple[str, str]] = []
        clone_path = Path(clone_dir)

        for abs_path in clone_path.rglob("*"):
            if abs_path.is_file():
                relative_path = str(abs_path.relative_to(clone_path))
                # Normalize path separator to forward slash
                relative_path = relative_path.replace("\\", "/")
                files.append((relative_path, str(abs_path)))

        return files

    def _process_file(
        self,
        db_organization_id: int,
        repository_id: int,
        file_path: str,
        file_abs_path: str,
        commit_sha: str | None,
    ) -> bool:
        """
        Processes a single file through the full pipeline:
          classify → change detect → chunk → embed → store

        Returns True if the file was indexed, False if it was skipped.
        """
        # ── Step 1: Get file size ─────────────────────────────────────────────
        try:
            size_bytes = os.path.getsize(file_abs_path)
        except OSError:
            size_bytes = 0

        # ── Step 2: Classify file ─────────────────────────────────────────────
        classification = classify_file(file_path, size_bytes)

        if not classification.should_index:
            self._upsert_file_record(
                organization_id=db_organization_id,
                repository_id=repository_id,
                file_path=file_path,
                language=None,
                file_type=classification.file_type,
                size_bytes=size_bytes,
                checksum=None,
                commit_sha=commit_sha,
                is_indexed=False,
                status=FileStatus.SKIPPED.value,
                skip_reason=classification.skip_reason,
                chunk_count=0,
            )
            return False

        # ── Step 3: Read file content ─────────────────────────────────────────
        try:
            with open(file_abs_path, "rb") as f:
                raw_bytes = f.read()
        except (OSError, PermissionError) as exc:
            raise RuntimeError(f"Cannot read file: {exc}")

        # Detect if binary (look for null bytes)
        if b"\x00" in raw_bytes[:8192]:
            self._upsert_file_record(
                organization_id=db_organization_id,
                repository_id=repository_id,
                file_path=file_path,
                language=None,
                file_type="other",
                size_bytes=size_bytes,
                checksum=None,
                commit_sha=commit_sha,
                is_indexed=False,
                status=FileStatus.SKIPPED.value,
                skip_reason="binary file",
                chunk_count=0,
            )
            return False

        # Decode to text
        try:
            content = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            try:
                import chardet
                detected = chardet.detect(raw_bytes)
                encoding = detected.get("encoding") or "latin-1"
                content = raw_bytes.decode(encoding, errors="replace")
            except Exception:
                content = raw_bytes.decode("latin-1", errors="replace")

        # ── Step 4: Compute checksum for change detection ─────────────────────
        new_checksum = compute_checksum(raw_bytes)

        # Check if file changed since last sync
        existing_file = self._get_existing_file_record(
            organization_id=db_organization_id,
            repository_id=repository_id,
            file_path=file_path,
        )

        if (existing_file
                and existing_file.content_checksum == new_checksum
                and existing_file.is_indexed
                and existing_file.status == FileStatus.INDEXED.value):
            # File unchanged and successfully indexed — skip re-embedding
            logger.debug(
                "File unchanged — skipping re-embed",
                extra={"file_path": file_path},
            )
            return False

        # ── Step 5: Delete old vectors if file changed ────────────────────────
        if existing_file and existing_file.is_indexed:
            vector_store.delete_vectors_by_file(
                repository_id=repository_id,
                file_path=file_path,
            )
            # Delete old knowledge metadata records
            self._delete_knowledge_records(
                repository_id=repository_id,
                file_path=file_path,
            )

        # ── Step 6: Chunk the file ────────────────────────────────────────────
        chunks = chunk_file(
            content=content,
            file_path=file_path,
            language=classification.language,
            file_type=classification.file_type,
            max_tokens=settings.CHUNK_MAX_TOKENS,
            overlap_tokens=settings.CHUNK_OVERLAP_TOKENS,
        )

        if not chunks:
            self._upsert_file_record(
                organization_id=db_organization_id,
                repository_id=repository_id,
                file_path=file_path,
                language=classification.language,
                file_type=classification.file_type,
                size_bytes=size_bytes,
                checksum=new_checksum,
                commit_sha=commit_sha,
                is_indexed=False,
                status=FileStatus.SKIPPED.value,
                skip_reason="no chunks generated",
                chunk_count=0,
            )
            return False

        # ── Step 7: Upsert file record (DISCOVERED status) ────────────────────
        file_record = self._upsert_file_record(
            organization_id=db_organization_id,
            repository_id=repository_id,
            file_path=file_path,
            language=classification.language,
            file_type=classification.file_type,
            size_bytes=size_bytes,
            checksum=new_checksum,
            commit_sha=commit_sha,
            is_indexed=False,
            status=FileStatus.DISCOVERED.value,
            skip_reason=None,
            chunk_count=len(chunks),
        )

        # ── Step 8: Embed chunks in batches ───────────────────────────────────
        chunk_texts = [c.content for c in chunks]
        embeddings = embedder.embed_texts(chunk_texts)

        if len(embeddings) != len(chunks):
            raise RuntimeError(
                f"Embedding count mismatch: got {len(embeddings)}, expected {len(chunks)}"
            )

        # ── Step 9: Upsert vectors + create knowledge records ─────────────────
        vector_points: list[dict] = []
        knowledge_records: list[RepositoryKnowledge] = []

        for chunk, embedding in zip(chunks, embeddings):
            vec_id = vector_store.generate_vector_id()

            vector_points.append({
                "id": vec_id,
                "vector": embedding,
                "payload": {
                    "organization_id": db_organization_id,
                    "repository_id": repository_id,
                    "repository_file_id": file_record.id,
                    "file_path": file_path,
                    "commit_sha": commit_sha,
                    "language": classification.language,
                    "chunk_type": chunk.chunk_type,
                    "chunk_name": chunk.chunk_name,
                    "chunk_index": chunk.chunk_index,
                    "start_line": chunk.start_line,
                    "end_line": chunk.end_line,
                    "content": chunk.content,
                    "token_count": chunk.token_count,
                    "embedding_model": embedder.get_model_name(),
                },
            })

            knowledge_records.append(RepositoryKnowledge(
                organization_id=db_organization_id,
                repository_id=repository_id,
                repository_file_id=file_record.id,
                file_path=file_path,
                commit_sha=commit_sha,
                language=classification.language,
                chunk_type=chunk.chunk_type,
                chunk_name=chunk.chunk_name,
                chunk_index=chunk.chunk_index,
                start_line=chunk.start_line,
                end_line=chunk.end_line,
                content=chunk.content,
                token_count=chunk.token_count,
                vector_id=vec_id,
                embedding_model=embedder.get_model_name(),
            ))

        # Upsert vectors into Qdrant
        vector_store.upsert_vectors(vector_points)

        # Save knowledge metadata into PostgreSQL
        with get_db_session() as db:
            for record in knowledge_records:
                db.add(record)
            db.commit()

        # ── Step 10: Extract code symbols and relationships ────────────────────
        if symbol_extractor.is_supported(classification.language):
            self._extract_and_store_symbols(
                content=content,
                file_path=file_path,
                language=classification.language,
                organization_id=db_organization_id,
                repository_id=repository_id,
                repository_file_id=file_record.id,
                commit_sha=commit_sha,
            )

        # Mark file as INDEXED
        self._mark_file_indexed(
            organization_id=db_organization_id,
            repository_id=repository_id,
            file_path=file_path,
            chunk_count=len(chunks),
        )

        logger.debug(
            "File indexed successfully",
            extra={
                "file_path": file_path,
                "chunks": len(chunks),
                "language": classification.language,
            },
        )
        return True

    # ── DB helpers ─────────────────────────────────────────────────────────────

    def _upsert_file_record(
        self,
        organization_id: int,
        repository_id: int,
        file_path: str,
        language: str | None,
        file_type: str,
        size_bytes: int,
        checksum: str | None,
        commit_sha: str | None,
        is_indexed: bool,
        status: str,
        skip_reason: str | None,
        chunk_count: int,
    ) -> RepositoryFile:
        """Creates or updates the RepositoryFile record for a given path."""
        with get_db_session() as db:
            existing = (
                db.query(RepositoryFile)
                .filter(
                    RepositoryFile.repository_id == repository_id,
                    RepositoryFile.path == file_path,
                )
                .first()
            )

            if existing:
                existing.language = language
                existing.file_type = file_type
                existing.size_bytes = size_bytes
                existing.content_checksum = checksum
                existing.commit_sha = commit_sha
                existing.is_indexed = is_indexed
                existing.status = status
                existing.skip_reason = skip_reason
                existing.chunk_count = chunk_count
                existing.updated_at = datetime.now(timezone.utc)
                db.commit()
                db.refresh(existing)
                return existing

            record = RepositoryFile(
                organization_id=organization_id,
                repository_id=repository_id,
                path=file_path,
                language=language,
                file_type=file_type,
                size_bytes=size_bytes,
                content_checksum=checksum,
                commit_sha=commit_sha,
                is_indexed=is_indexed,
                status=status,
                skip_reason=skip_reason,
                chunk_count=chunk_count,
            )
            db.add(record)
            db.commit()
            db.refresh(record)
            return record

    def _get_existing_file_record(
        self,
        organization_id: int,
        repository_id: int,
        file_path: str,
    ) -> RepositoryFile | None:
        """Returns the existing RepositoryFile record or None."""
        with get_db_session() as db:
            return (
                db.query(RepositoryFile)
                .filter(
                    RepositoryFile.repository_id == repository_id,
                    RepositoryFile.path == file_path,
                )
                .first()
            )

    def _mark_file_indexed(
        self,
        organization_id: int,
        repository_id: int,
        file_path: str,
        chunk_count: int,
    ) -> None:
        """Marks a RepositoryFile record as INDEXED."""
        with get_db_session() as db:
            record = (
                db.query(RepositoryFile)
                .filter(
                    RepositoryFile.repository_id == repository_id,
                    RepositoryFile.path == file_path,
                )
                .first()
            )
            if record:
                record.is_indexed = True
                record.status = FileStatus.INDEXED.value
                record.chunk_count = chunk_count
                record.updated_at = datetime.now(timezone.utc)
                db.commit()

    def _mark_file_failed(
        self,
        organization_id: int,
        repository_id: int,
        file_path: str,
        error: str,
    ) -> None:
        """Marks a RepositoryFile record as FAILED."""
        with get_db_session() as db:
            record = (
                db.query(RepositoryFile)
                .filter(
                    RepositoryFile.repository_id == repository_id,
                    RepositoryFile.path == file_path,
                )
                .first()
            )
            if record:
                record.status = FileStatus.FAILED.value
                record.skip_reason = error[:200]
                record.updated_at = datetime.now(timezone.utc)
                db.commit()

    def _delete_knowledge_records(
        self,
        repository_id: int,
        file_path: str,
    ) -> None:
        """Deletes all RepositoryKnowledge records for a file (before re-indexing)."""
        with get_db_session() as db:
            db.query(RepositoryKnowledge).filter(
                RepositoryKnowledge.repository_id == repository_id,
                RepositoryKnowledge.file_path == file_path,
            ).delete()
            db.commit()

    def _update_progress(
        self,
        sync_id: int,
        files_discovered: int,
        files_processed: int,
        files_failed: int,
    ) -> None:
        """Updates the RepositorySync progress counters."""
        with get_db_session() as db:
            sync = db.get(RepositorySync, sync_id)
            if sync:
                sync.files_discovered = files_discovered
                sync.files_processed = files_processed
                sync.files_failed = files_failed
                db.commit()

    def _mark_failed(
        self,
        sync_id: int,
        repository_id: int,
        error_message: str,
    ) -> None:
        """Marks both the sync and the repository as FAILED."""
        try:
            with get_db_session() as db:
                sync = db.get(RepositorySync, sync_id)
                if sync:
                    sync.status = SyncStatus.FAILED.value
                    sync.completed_at = datetime.now(timezone.utc)
                    sync.error_message = error_message[:2000]
                    db.commit()

                repo = db.get(Repository, repository_id)
                if repo:
                    repo.status = RepositoryStatus.FAILED.value
                    repo.updated_at = datetime.now(timezone.utc)
                    db.commit()
        except Exception as exc:
            logger.exception(
                "Failed to record sync failure in DB",
                extra={"sync_id": sync_id, "error": str(exc)},
            )

    # ── Symbol extraction helpers ─────────────────────────────────────────────

    def _extract_and_store_symbols(
        self,
        content: str,
        file_path: str,
        language: str,
        organization_id: int,
        repository_id: int,
        repository_file_id: int,
        commit_sha: str | None,
    ) -> None:
        """
        Runs tree-sitter symbol extraction on a file and persists the results.

        Old symbol records for this file are deleted first so re-syncs always
        reflect the current state of the code at the given commit.
        """
        result = symbol_extractor.extract_symbols(
            content=content,
            file_path=file_path,
            language=language,
        )

        if not result.symbols and not result.relationships:
            return

        with get_db_session() as db:
            # Delete stale symbol records for this file
            db.query(CodeSymbol).filter(
                CodeSymbol.repository_id == repository_id,
                CodeSymbol.file_path == file_path,
            ).delete(synchronize_session=False)
            # Cascading FK will also clear CodeRelationship rows with those source_symbol_ids

            # Build a name → CodeSymbol map for cross-linking within this file
            symbol_map: dict[str, CodeSymbol] = {}

            for extracted in result.symbols:
                sym = CodeSymbol(
                    organization_id=organization_id,
                    repository_id=repository_id,
                    repository_file_id=repository_file_id,
                    commit_sha=commit_sha,
                    file_path=file_path,
                    symbol_name=extracted.symbol_name,
                    qualified_name=extracted.qualified_name,
                    symbol_type=extracted.symbol_type,
                    language=language,
                    start_line=extracted.start_line,
                    end_line=extracted.end_line,
                    signature=extracted.signature[:2000] if extracted.signature else None,
                    docstring=extracted.docstring[:2000] if extracted.docstring else None,
                    is_async=extracted.is_async,
                    is_exported=extracted.is_exported,
                )
                db.add(sym)
                db.flush()  # Populate sym.id for relationship linking below
                symbol_map[extracted.symbol_name] = sym
                if extracted.qualified_name:
                    symbol_map[extracted.qualified_name] = sym

            # Persist relationships (source resolved within this file only)
            for rel in result.relationships:
                source_sym = symbol_map.get(rel.source_symbol_name)
                target_sym = symbol_map.get(rel.target_symbol_name)

                cr = CodeRelationship(
                    organization_id=organization_id,
                    repository_id=repository_id,
                    commit_sha=commit_sha,
                    source_symbol_id=source_sym.id if source_sym else None,
                    source_file_path=rel.source_file_path,
                    source_line=rel.source_line,
                    target_symbol_id=target_sym.id if target_sym else None,
                    target_file_path=rel.target_file_path,
                    target_symbol_name=rel.target_symbol_name,
                    relationship_type=rel.relationship_type,
                    confidence=rel.confidence,
                    is_resolved=(target_sym is not None),
                )
                db.add(cr)

            db.commit()

        logger.debug(
            "Symbols stored",
            extra={
                "file_path": file_path,
                "symbols": len(result.symbols),
                "relationships": len(result.relationships),
            },
        )

    def _delete_symbol_records(
        self,
        repository_id: int,
        file_path: str,
    ) -> None:
        """Removes all symbol records for a file (called before re-indexing)."""
        with get_db_session() as db:
            db.query(CodeSymbol).filter(
                CodeSymbol.repository_id == repository_id,
                CodeSymbol.file_path == file_path,
            ).delete(synchronize_session=False)
            db.commit()

