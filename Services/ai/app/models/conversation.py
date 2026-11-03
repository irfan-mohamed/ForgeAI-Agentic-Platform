"""
AI Service owned models:
  - Conversation  : a chat session tied to a repository
  - Message       : individual user/assistant turns in a conversation
  - AgentRun      : tracks each LLM execution with status and metadata
"""
import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import (
    DateTime, ForeignKey, Integer, Numeric, String, Text, Enum
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


# ── Enums ─────────────────────────────────────────────────────────────────────

class MessageRole(str, PyEnum):
    USER = "USER"
    ASSISTANT = "ASSISTANT"


class AgentType(str, PyEnum):
    ENGINEERING = "ENGINEERING"
    CODE_REVIEW = "CODE_REVIEW"
    TESTING = "TESTING"


class AgentStatus(str, PyEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


# ── Models ────────────────────────────────────────────────────────────────────

class Conversation(Base):
    """
    A chat session. Scoped to an organization and optionally a repository.

    - org_id and user_id are FK references to the API service's tables.
      The AI service reads them but doesn't own those tables.
    - repository_id references repositories owned by the Repository Service.
    - title is auto-generated or user-supplied.
    """
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    # Optional — null means org-wide conversation (future)
    repository_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    # Human-readable full name of the repository (e.g. "acme/backend")
    # Stored at creation so prompts always contain the real name even if
    # the repository record is later renamed or disconnected.
    repository_full_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    # Deleting a conversation must delete its messages and runs; without the
    # cascade SQLAlchemy tries to NULL the (NOT NULL) foreign keys instead.
    messages: Mapped[list["Message"]] = relationship(
        "Message",
        back_populates="conversation",
        order_by="Message.created_at",
        cascade="all, delete-orphan",
    )
    agent_runs: Mapped[list["AgentRun"]] = relationship(
        "AgentRun",
        back_populates="conversation",
        cascade="all, delete-orphan",
    )


class Message(Base):
    """
    A single turn (user or assistant) in a conversation.
    content is the full text of the message.
    token_count is filled after generation for usage tracking.
    """
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[MessageRole] = mapped_column(Enum(MessageRole), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Token count filled after generation (nullable until then)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="messages")


class AgentRun(Base):
    """
    Tracks one LLM execution cycle — from user question to final response.
    Stores retrieved chunk IDs for explainability (which code was used to answer).
    """
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # The user message that triggered this run
    user_message_id: Mapped[str] = mapped_column(String(36), nullable=False)
    # The assistant message produced (null until completed)
    assistant_message_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    agent_type: Mapped[AgentType] = mapped_column(
        Enum(AgentType), nullable=False, default=AgentType.ENGINEERING
    )
    status: Mapped[AgentStatus] = mapped_column(
        Enum(AgentStatus), nullable=False, default=AgentStatus.PENDING
    )
    # Comma-separated Qdrant point IDs used for context (for explainability)
    retrieved_chunk_ids: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Total tokens consumed (prompt + completion)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="agent_runs")
