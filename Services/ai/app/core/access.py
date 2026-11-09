"""
access.py — Tenant-isolation checks for the AI Service.

Every AI endpoint must prove three things before touching repository
knowledge:

  1. The caller is an active member of the organization.
  2. The repository belongs to that organization.
  3. For conversations, the caller owns the conversation.

The ``memberships`` table is owned by the API service and ``repositories`` by
the Repository Service. Both live in the shared PostgreSQL database, so —
like the Repository Service does — we read them with small read-only queries
instead of importing the other services' models.

IDs from clients are never trusted: the organization and repository IDs that
reach Qdrant always come from these checks (``RepoInfo``), not from the
request body.
"""
from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.conversation import Conversation

# Repositories in these states can no longer be used for AI work.
_UNAVAILABLE_REPO_STATUSES = {"disconnected", "access_revoked"}


@dataclass(frozen=True)
class RepoInfo:
    id: int
    organization_id: int
    name: str
    full_name: str
    status: str
    default_branch: str
    # Readiness checkpoints. Older rows predate these columns; a repository
    # with status "ready" is treated as ready on all three dimensions.
    repo_map_ready: bool = False
    chat_ready: bool = False
    index_ready: bool = False


def parse_id(value: object, label: str = "id") -> int:
    """Parses a client-supplied ID into a positive int or raises HTTP 400."""
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {label}.",
        )
    if parsed <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {label}.",
        )
    return parsed


def require_org_member(db: Session, user_id: int, org_id: int) -> None:
    """Raises HTTP 403 unless the user is an active member of the organization."""
    row = db.execute(
        text(
            "SELECT id FROM memberships "
            "WHERE user_id = :user_id "
            "  AND organization_id = :org_id "
            "  AND status = 'active' "
            "LIMIT 1"
        ),
        {"user_id": user_id, "org_id": org_id},
    ).fetchone()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this organization.",
        )


def get_repository(
    db: Session,
    org_id: int,
    repository_id: int,
    *,
    require_ready: bool = False,
) -> RepoInfo:
    """
    Returns the repository if it belongs to ``org_id`` and is still connected.

    Raises 404 for repositories that do not exist, belong to another
    organization, or were disconnected / lost GitHub access (404 rather than
    403 so repository IDs of other tenants are not revealed).
    Raises 409 when ``require_ready`` is set and the repository is not
    chat-ready yet.

    ``SELECT *`` is intentional: the readiness timestamp columns may not exist
    in older deployments or lightweight test schemas. Missing fields simply
    fall back to the legacy ``status == "ready"`` compatibility rule.
    """
    row = db.execute(
        text(
            "SELECT * FROM repositories "
            "WHERE id = :repository_id AND organization_id = :org_id"
        ),
        {"repository_id": repository_id, "org_id": org_id},
    ).fetchone()

    if not row or row._mapping["status"] in _UNAVAILABLE_REPO_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found.",
        )

    data = row._mapping
    status_value = data["status"]

    def _ready(field_name: str) -> bool:
        # Legacy rows only have status == "ready".
        timestamp = data.get(field_name) if hasattr(data, "get") else None
        return timestamp is not None or status_value == "ready"

    repo_map_ready = _ready("repo_map_ready_at")
    chat_ready = _ready("chat_ready_at")
    index_ready = _ready("index_ready_at")

    if require_ready and not chat_ready:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This repository is not ready yet "
                f"(not ready for chat, status: {status_value}). Wait for the repository map to finish."
            ),
        )

    return RepoInfo(
        id=data["id"],
        organization_id=data["organization_id"],
        name=data["name"],
        full_name=data["full_name"],
        status=status_value,
        default_branch=data["default_branch"],
        repo_map_ready=repo_map_ready,
        chat_ready=chat_ready,
        index_ready=index_ready,
    )


def load_user_conversation(
    db: Session,
    conversation_id: str,
    user_id: int,
) -> Conversation:
    """
    Loads a conversation the user owns and re-checks organization membership
    (so removing a user from an organization also cuts off their old chats).

    Other users' conversations return 404, not 403.
    """
    conv = db.get(Conversation, conversation_id)
    if not conv or conv.user_id != str(user_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    require_org_member(db, user_id, parse_id(conv.org_id, "organization id"))
    return conv
