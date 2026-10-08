"""
repository_service.py — All business logic for repository management.

This service is the single source of truth for:
  - GitHub installation lifecycle (create, get, revoke)
  - Repository connections (connect, list, get, disconnect)
  - Sync management (request, status)
  - Webhook event handling (push, installation deleted)

Routes should be thin — all business decisions live here.
"""

import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.github_installation import GitHubInstallation, InstallationStatus
from app.models.repository import Repository, RepositoryStatus
from app.models.repository_sync import RepositorySync, SyncStatus, SyncTrigger
from app.schemas.github import GitHubAvailableRepo, GitHubConnectionStatus, GitHubAccountInfo
from app.schemas.repository import RepositorySyncStatusResponse, SyncProgressDetail
from app.services import github_service
from app.services import kafka_producer

logger = logging.getLogger(__name__)


# ── GitHub Installation ───────────────────────────────────────────────────────

class RepositoryService:

    @staticmethod
    def create_or_update_installation(
        organization_id: int,
        github_installation_id: int,
        github_account_id: int,
        github_account_login: str,
        account_type: str,
        db: Session,
    ) -> GitHubInstallation:
        """
        Called from the GitHub callback route after a user installs the App.

        If an installation already exists for this org, it is updated.
        If not, a new record is created.

        This handles the case where a user re-installs the App after revocation.
        """
        existing = (
            db.query(GitHubInstallation)
            .filter(GitHubInstallation.organization_id == organization_id)
            .first()
        )

        if existing:
            existing.github_installation_id = github_installation_id
            existing.github_account_id = github_account_id
            existing.github_account_login = github_account_login
            existing.account_type = account_type
            existing.status = InstallationStatus.ACTIVE.value
            existing.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(existing)
            logger.info(
                "GitHub installation updated",
                extra={"org_id": organization_id, "installation_id": github_installation_id},
            )
            return existing

        installation = GitHubInstallation(
            organization_id=organization_id,
            github_installation_id=github_installation_id,
            github_account_id=github_account_id,
            github_account_login=github_account_login,
            account_type=account_type,
            status=InstallationStatus.ACTIVE.value,
        )
        db.add(installation)
        db.commit()
        db.refresh(installation)

        logger.info(
            "GitHub installation created",
            extra={"org_id": organization_id, "installation_id": github_installation_id},
        )
        return installation

    @staticmethod
    def get_installation(
        organization_id: int,
        db: Session,
    ) -> GitHubInstallation | None:
        """Returns the active GitHub installation for an org, or None."""
        return (
            db.query(GitHubInstallation)
            .filter(
                GitHubInstallation.organization_id == organization_id,
                GitHubInstallation.status == InstallationStatus.ACTIVE.value,
            )
            .first()
        )

    @staticmethod
    def get_installation_or_404(
        organization_id: int,
        db: Session,
    ) -> GitHubInstallation:
        """Returns the active installation or raises 404."""
        installation = RepositoryService.get_installation(organization_id, db)
        if not installation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    "GitHub is not connected to this organization. "
                    "Connect GitHub first via /organizations/{org_id}/github/install"
                ),
            )
        return installation

    @staticmethod
    def get_connection_status(
        organization_id: int,
        db: Session,
    ) -> GitHubConnectionStatus:
        """Returns the GitHub connection status for an organization."""
        installation = RepositoryService.get_installation(organization_id, db)
        if not installation:
            return GitHubConnectionStatus(connected=False)

        return GitHubConnectionStatus(
            connected=True,
            account=GitHubAccountInfo(
                login=installation.github_account_login,
                account_type=installation.account_type,
            ),
        )

    # ── Available Repositories ────────────────────────────────────────────────

    @staticmethod
    def list_available_repositories(
        organization_id: int,
        db: Session,
    ) -> list[GitHubAvailableRepo]:
        """
        Fetches repositories available through the GitHub App installation.

        Does NOT save anything — purely reads from GitHub API.
        Raises 404 if no GitHub installation exists for the org.
        Raises 502 if GitHub API call fails.
        """
        installation = RepositoryService.get_installation_or_404(organization_id, db)

        try:
            token = github_service.get_installation_access_token(
                installation.github_installation_id
            )
            return github_service.list_installation_repositories(token)
        except RuntimeError as exc:
            logger.error(
                "Failed to list repositories from GitHub",
                extra={"org_id": organization_id, "error": str(exc)},
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to fetch repositories from GitHub. Please try again.",
            )

    # ── Repository CRUD ───────────────────────────────────────────────────────

    @staticmethod
    def connect_repository(
        organization_id: int,
        github_repository_id: str,
        db: Session,
    ) -> Repository:
        """
        Connects a GitHub repository to a ForgeAI organization.

        Steps:
        1. Validates the org has a GitHub installation.
        2. Checks the repo is not already connected in this org.
        3. Fetches repository metadata from GitHub.
        4. Creates the Repository record (status=CONNECTING).
        5. Creates the first RepositorySync record (trigger=initial).
        6. Publishes repository.connected Kafka event.

        Raises:
            404 — No GitHub installation for the org
            409 — Repository already connected in this org
            502 — GitHub API failure
        """
        installation = RepositoryService.get_installation_or_404(organization_id, db)

        # Check for duplicate connection.
        existing = (
            db.query(Repository)
            .filter(
                Repository.organization_id == organization_id,
                Repository.github_repository_id == github_repository_id,
                Repository.status != RepositoryStatus.DISCONNECTED.value,
            )
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Repository '{github_repository_id}' is already connected "
                    "to this organization."
                ),
            )

        # Fetch real repo metadata from GitHub.
        try:
            token = github_service.get_installation_access_token(
                installation.github_installation_id
            )
            meta = github_service.get_repository_metadata(token, github_repository_id)
        except RuntimeError as exc:
            logger.error(
                "Failed to fetch repository metadata from GitHub",
                extra={"github_repository_id": github_repository_id, "error": str(exc)},
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to fetch repository information from GitHub.",
            )

        # Create Repository record.
        repo = Repository(
            organization_id=organization_id,
            github_installation_id=installation.id,
            github_repository_id=github_repository_id,
            name=meta["name"],
            full_name=meta["full_name"],
            owner=meta["owner"]["login"],
            description=meta.get("description"),
            visibility="private" if meta.get("private") else "public",
            default_branch=meta.get("default_branch", "main"),
            status=RepositoryStatus.CONNECTING.value,
        )
        db.add(repo)
        db.flush()  # Populate repo.id before creating the sync record.

        # Create initial sync record.
        sync = RepositorySync(
            repository_id=repo.id,
            status=SyncStatus.QUEUED.value,
            trigger=SyncTrigger.INITIAL.value,
        )
        db.add(sync)
        db.commit()
        db.refresh(repo)
        db.refresh(sync)

        # Publish event to Kafka (or log in stub mode).
        kafka_producer.publish_repository_connected(
            organization_id=organization_id,
            repository_id=repo.id,
            sync_id=sync.id,
        )

        logger.info(
            "Repository connected",
            extra={
                "org_id": organization_id,
                "repo_id": repo.id,
                "full_name": repo.full_name,
                "sync_id": sync.id,
            },
        )
        return repo

    @staticmethod
    def get_repository(
        repo_id: int,
        organization_id: int,
        db: Session,
    ) -> Repository:
        """
        Returns a repository by ID.

        Validates that the repository belongs to the given organization
        to prevent cross-tenant data leaks.

        Raises 404 if not found or 403 if org does not match.
        """
        repo = db.get(Repository, repo_id)
        if not repo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Repository not found.",
            )
        if repo.organization_id != organization_id:
            # Return 404 rather than 403 to avoid revealing repository existence.
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Repository not found.",
            )
        return repo

    @staticmethod
    def list_org_repositories(
        organization_id: int,
        db: Session,
    ) -> list[Repository]:
        """Returns all non-disconnected repositories for an organization."""
        return (
            db.query(Repository)
            .filter(
                Repository.organization_id == organization_id,
                Repository.status != RepositoryStatus.DISCONNECTED.value,
            )
            .order_by(Repository.name)
            .all()
        )

    @staticmethod
    def disconnect_repository(
        repo_id: int,
        organization_id: int,
        db: Session,
    ) -> None:
        """
        Marks a repository as DISCONNECTED and publishes the corresponding event.

        Does not delete the record — we preserve the history.
        The data retention/cleanup policy is handled separately.
        """
        repo = RepositoryService.get_repository(repo_id, organization_id, db)

        repo.status = RepositoryStatus.DISCONNECTED.value
        repo.updated_at = datetime.now(timezone.utc)
        db.commit()

        kafka_producer.publish_repository_disconnected(
            organization_id=organization_id,
            repository_id=repo_id,
        )

        logger.info(
            "Repository disconnected",
            extra={"org_id": organization_id, "repo_id": repo_id},
        )

    # ── Sync Management ───────────────────────────────────────────────────────

    @staticmethod
    def request_sync(
        repo_id: int,
        organization_id: int,
        db: Session,
    ) -> RepositorySync:
        """
        Queues a manual sync for a repository.

        Creates a RepositorySync record and publishes a sync.requested event.
        The actual processing is done by the Worker service.

        Raises 404 if the repository is not found in this org.
        Raises 409 if a sync is already running.
        """
        repo = RepositoryService.get_repository(repo_id, organization_id, db)

        # Prevent duplicate concurrent syncs.
        running_sync = (
            db.query(RepositorySync)
            .filter(
                RepositorySync.repository_id == repo_id,
                RepositorySync.status.in_([
                    SyncStatus.QUEUED.value,
                    SyncStatus.RUNNING.value,
                ]),
            )
            .first()
        )
        if running_sync:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A sync is already queued or running for this repository.",
            )

        sync = RepositorySync(
            repository_id=repo_id,
            status=SyncStatus.QUEUED.value,
            trigger=SyncTrigger.MANUAL.value,
        )
        db.add(sync)
        db.commit()
        db.refresh(sync)

        kafka_producer.publish_sync_requested(
            organization_id=organization_id,
            repository_id=repo_id,
            sync_id=sync.id,
            trigger=SyncTrigger.MANUAL.value,
        )

        logger.info(
            "Manual sync requested",
            extra={"org_id": organization_id, "repo_id": repo_id, "sync_id": sync.id},
        )
        return sync

    @staticmethod
    def get_sync_status(
        repo_id: int,
        organization_id: int,
        db: Session,
    ) -> RepositorySyncStatusResponse:
        """
        Returns the latest sync record for a repository.

        Raises 404 if the repository doesn't exist in this org or
        if no sync has ever been created for it.
        """
        # Verify ownership first.
        RepositoryService.get_repository(repo_id, organization_id, db)

        sync = (
            db.query(RepositorySync)
            .filter(RepositorySync.repository_id == repo_id)
            .order_by(RepositorySync.created_at.desc())
            .first()
        )
        if not sync:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No sync records found for this repository.",
            )

        return RepositorySyncStatusResponse(
            id=sync.id,
            repository_id=sync.repository_id,
            status=sync.status,
            trigger=sync.trigger,
            commit_sha=sync.commit_sha,
            started_at=sync.started_at,
            completed_at=sync.completed_at,
            progress=SyncProgressDetail(
                files_discovered=sync.files_discovered,
                files_processed=sync.files_processed,
                files_failed=sync.files_failed,
            ),
            error_message=sync.error_message,
            created_at=sync.created_at,
        )

    # ── Webhook Event Handlers ────────────────────────────────────────────────

    @staticmethod
    def handle_installation_deleted(
        github_installation_id: int,
        db: Session,
    ) -> None:
        """
        Called when GitHub reports the App installation was deleted/uninstalled.

        Marks all repositories under this installation as ACCESS_REVOKED
        and publishes an access.revoked event for each.
        """
        installation = (
            db.query(GitHubInstallation)
            .filter(
                GitHubInstallation.github_installation_id == github_installation_id
            )
            .first()
        )
        if not installation:
            logger.warning(
                "Received deletion for unknown installation",
                extra={"github_installation_id": github_installation_id},
            )
            return

        installation.status = InstallationStatus.REVOKED.value
        installation.updated_at = datetime.now(timezone.utc)

        # Revoke all active repositories linked to this installation.
        repos = (
            db.query(Repository)
            .filter(
                Repository.github_installation_id == installation.id,
                Repository.status.not_in([
                    RepositoryStatus.DISCONNECTED.value,
                    RepositoryStatus.ACCESS_REVOKED.value,
                ]),
            )
            .all()
        )

        for repo in repos:
            repo.status = RepositoryStatus.ACCESS_REVOKED.value
            repo.updated_at = datetime.now(timezone.utc)

        db.commit()

        for repo in repos:
            kafka_producer.publish_access_revoked(
                organization_id=repo.organization_id,
                repository_id=repo.id,
            )

        logger.warning(
            "GitHub installation deleted — repos revoked",
            extra={
                "github_installation_id": github_installation_id,
                "revoked_repo_count": len(repos),
            },
        )

    @staticmethod
    def handle_installation_repos_removed(
        github_installation_id: int,
        removed_github_repo_ids: list[str],
        db: Session,
    ) -> None:
        """
        Called when a user removes specific repositories from the installation.

        Only the explicitly removed repos are revoked, not all repos
        under the installation.
        """
        installation = (
            db.query(GitHubInstallation)
            .filter(
                GitHubInstallation.github_installation_id == github_installation_id
            )
            .first()
        )
        if not installation:
            return

        for github_repo_id in removed_github_repo_ids:
            repo = (
                db.query(Repository)
                .filter(
                    Repository.github_installation_id == installation.id,
                    Repository.github_repository_id == str(github_repo_id),
                    Repository.status.not_in([
                        RepositoryStatus.DISCONNECTED.value,
                        RepositoryStatus.ACCESS_REVOKED.value,
                    ]),
                )
                .first()
            )
            if repo:
                repo.status = RepositoryStatus.ACCESS_REVOKED.value
                repo.updated_at = datetime.now(timezone.utc)
                db.commit()
                kafka_producer.publish_access_revoked(
                    organization_id=repo.organization_id,
                    repository_id=repo.id,
                )
                logger.info(
                    "Repository access revoked via installation_repositories event",
                    extra={"repo_id": repo.id, "github_repo_id": github_repo_id},
                )

    @staticmethod
    def handle_push_event(
        github_installation_id: int,
        github_repository_id: str,
        commit_sha: str,
        db: Session,
    ) -> None:
        """
        Called when GitHub reports a push to a connected repository.

        Creates a new RepositorySync (trigger=webhook_push) and publishes
        a sync.requested event so the Worker picks it up.

        Silently ignores the event if the repository is not found (it may
        not be connected to ForgeAI).
        """
        installation = (
            db.query(GitHubInstallation)
            .filter(
                GitHubInstallation.github_installation_id == github_installation_id
            )
            .first()
        )
        if not installation:
            return

        repo = (
            db.query(Repository)
            .filter(
                Repository.github_installation_id == installation.id,
                Repository.github_repository_id == github_repository_id,
                Repository.status == RepositoryStatus.READY.value,
            )
            .first()
        )
        if not repo:
            # Repo is not connected or not yet ready — skip.
            return

        sync = RepositorySync(
            repository_id=repo.id,
            status=SyncStatus.QUEUED.value,
            trigger=SyncTrigger.WEBHOOK_PUSH.value,
            commit_sha=commit_sha,
        )
        db.add(sync)
        db.commit()
        db.refresh(sync)

        kafka_producer.publish_sync_requested(
            organization_id=repo.organization_id,
            repository_id=repo.id,
            sync_id=sync.id,
            trigger=SyncTrigger.WEBHOOK_PUSH.value,
        )

        logger.info(
            "Push webhook triggered repository sync",
            extra={
                "repo_id": repo.id,
                "commit_sha": commit_sha,
                "sync_id": sync.id,
            },
        )
