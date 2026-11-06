"""
Conversation routes.

POST   /api/v1/organizations/{org_id}/conversations          — create
GET    /api/v1/organizations/{org_id}/conversations          — list
GET    /api/v1/conversations/{conversation_id}               — get with messages
DELETE /api/v1/conversations/{conversation_id}               — delete

Every route verifies organization membership; creating a conversation also
verifies that the repository belongs to the organization.
"""
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.access import (
    get_repository,
    load_user_conversation,
    parse_id,
    require_org_member,
)
from app.core.logging import get_logger
from app.core.security import UserId
from app.db.database import get_db
from app.models.conversation import Conversation

logger = get_logger(__name__)

router = APIRouter()

DB = Annotated[Session, Depends(get_db)]


# ── Schemas ───────────────────────────────────────────────────────────────────

class CreateConversationRequest(BaseModel):
    repository_id: str
    title: str = Field(min_length=1, max_length=255)


class ConversationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    repository_id: str | None
    repository_full_name: str | None = None
    updated_at: datetime


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    role: str
    content: str
    created_at: datetime


class ConversationDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    repository_id: str | None
    repository_full_name: str | None = None
    messages: list[MessageOut]
    created_at: datetime
    updated_at: datetime


class ConversationListResponse(BaseModel):
    conversations: list[ConversationSummary]
    total: int


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post(
    "/organizations/{org_id}/conversations",
    response_model=ConversationSummary,
    status_code=status.HTTP_201_CREATED,
)
def create_conversation(
    org_id: str,
    body: CreateConversationRequest,
    user_id: UserId,
    db: DB,
):
    """Create a new conversation tied to a repository of the organization."""
    org = parse_id(org_id, "organization id")
    require_org_member(db, user_id, org)
    repo = get_repository(db, org, parse_id(body.repository_id, "repository id"), require_ready=True)

    logger.info(
        "Repository eligibility verified for conversation",
        extra={"org_id": org, "repo_id": repo.id, "repo_status": repo.status, "user_id": user_id},
    )

    conv = Conversation(
        org_id=str(org),
        user_id=str(user_id),
        repository_id=str(repo.id),
        repository_full_name=repo.full_name,
        title=body.title.strip(),
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


@router.get(
    "/organizations/{org_id}/conversations",
    response_model=ConversationListResponse,
)
def list_conversations(
    org_id: str,
    user_id: UserId,
    db: DB,
    repository_id: str | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    """List the caller's conversations in an organization."""
    org = parse_id(org_id, "organization id")
    require_org_member(db, user_id, org)

    query = db.query(Conversation).filter(
        Conversation.org_id == str(org),
        Conversation.user_id == str(user_id),
    )
    if repository_id:
        query = query.filter(
            Conversation.repository_id == str(parse_id(repository_id, "repository id"))
        )

    total = query.count()
    convs = (
        query.order_by(Conversation.updated_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )
    logger.info(
        "Listing conversations for organization",
        extra={"org_id": org, "user_id": user_id, "total_found": total, "returned": len(convs)},
    )
    return {"conversations": convs, "total": total}


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationDetail,
)
def get_conversation(
    conversation_id: str,
    user_id: UserId,
    db: DB,
):
    """Get a conversation with all its messages."""
    return load_user_conversation(db, conversation_id, user_id)


@router.delete(
    "/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_conversation(
    conversation_id: str,
    user_id: UserId,
    db: DB,
):
    """Delete a conversation and all its messages."""
    conv = load_user_conversation(db, conversation_id, user_id)
    db.delete(conv)
    db.commit()
