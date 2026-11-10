"""
build_run.py — BuildRun model.

Tracks one execution attempt on an approved ImplementationPlan.

Lifecycle:
    queued → building → integration_testing → pr_opened | failed

Owned by: AI Service.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime, ForeignKey, Integer, String, Text, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import JSON

from app.db.base import Base

_JSON_TYPE = JSON().with_variant(JSONB, "postgresql")


class BuildRun(Base):
    """
    One build execution attempt for an approved ImplementationPlan.

    Status transitions:
        queued → building → integration_testing → pr_opened | failed
    """

    __tablename__ = "build_runs"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )

    plan_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("implementation_plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Tenant isolation
    organization_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    repository_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    triggered_by_user_id: Mapped[int] = mapped_column(Integer, nullable=False)

    # Status lifecycle
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="queued", index=True
    )

    # Append-only streamed log (all phases)
    build_log: Mapped[str | None] = mapped_column(Text, nullable=True)

    # OpenTelemetry root trace ID for this build run
    otel_trace_id: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # Parsed pytest/junit results
    test_results: Mapped[dict | None] = mapped_column(_JSON_TYPE, nullable=True)

    # [{task_id, file_path, diff}] - one entry per plan task
    generated_patches: Mapped[list | None] = mapped_column(_JSON_TYPE, nullable=True)

    # GitHub PR details (set after pr_opened)
    pull_request_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    pull_request_number: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Branch name used for the generated commit
    branch_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Error message if status == failed
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    plan = relationship("ImplementationPlan", backref="build_runs")
