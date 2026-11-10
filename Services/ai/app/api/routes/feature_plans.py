"""
feature_plans.py — Feature Plan API routes (Phase 3).

Endpoints:
  POST /api/v1/conversations/{conversation_id}/feature-plans
      — Trigger the feature planner graph for a new plan

  GET  /api/v1/feature-plans/{plan_id}
      — Get plan details (tasks, status, approval history)

  POST /api/v1/feature-plans/{plan_id}/approve
      — Approve the plan (human gate ✓)

  POST /api/v1/feature-plans/{plan_id}/reject
      — Reject the plan

  POST /api/v1/feature-plans/{plan_id}/request-changes
      — Request changes with feedback; triggers re-planning

Security:
  - All endpoints require a valid JWT.
  - Org membership is verified via the conversation's org_id.
  - Only the plan creator's org members can approve/reject/revise.

Owned by: AI Service.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.access import load_user_conversation, parse_id, require_org_member
from app.core.security import UserId
from app.db.database import get_db
from app.models.plan import ImplementationApproval, ImplementationPlan

logger = logging.getLogger(__name__)

router = APIRouter()
DB = Annotated[Session, Depends(get_db)]


# ── Pydantic Schemas ──────────────────────────────────────────────────────────

class CreatePlanRequest(BaseModel):
    feature_request: str = Field(..., min_length=10, max_length=4000)


class ApprovalRequest(BaseModel):
    comment: Optional[str] = Field(None, max_length=2000)
    commit_sha: Optional[str] = Field(None, max_length=40)


class RequestChangesRequest(BaseModel):
    feedback: str = Field(..., min_length=5, max_length=4000,
                          description="Specific feedback on what needs to change in the plan")
    comment: Optional[str] = Field(None, max_length=2000)


class ApprovalOut(BaseModel):
    id: str
    action: str
    comment: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class PlanOut(BaseModel):
    id: str
    organization_id: int
    repository_id: int
    conversation_id: Optional[str]
    feature_request: str
    plan_data: Optional[dict]
    status: str
    version: int
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime
    approvals: list[ApprovalOut] = []

    class Config:
        from_attributes = True


class CreatePlanResponse(BaseModel):
    plan_id: Optional[str]
    status: str
    plan_data: Optional[dict]
    error_message: Optional[str]
    message: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_plan(db: Session, plan_id: str, org_id: int) -> ImplementationPlan:
    """Load a plan, verifying it belongs to the org."""
    plan = (
        db.query(ImplementationPlan)
        .filter(
            ImplementationPlan.id == plan_id,
            ImplementationPlan.organization_id == org_id,
        )
        .first()
    )
    if not plan:
        raise HTTPException(status_code=404, detail="Implementation plan not found")
    return plan


def _get_org_id_from_conversation(db: Session, conversation_id: str, user_id: int) -> tuple[int, int]:
    """Return (org_id, repository_id) from a conversation, verifying user access."""
    convo = load_user_conversation(db, conversation_id, user_id)
    if not convo:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if not convo.repository_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This conversation is not associated with any repository.",
        )
    return parse_id(convo.org_id, "organization id"), parse_id(convo.repository_id, "repository id")


def _run_planner_background(
    feature_request: str,
    org_id: int,
    repository_id: int,
    user_id: int,
    conversation_id: str,
    revision_feedback: Optional[str],
    plan_id_container: dict,
):
    """Runs the feature planner synchronously in a background thread."""
    from app.services.feature_planner_graph import run_feature_planner
    result = run_feature_planner(
        feature_request=feature_request,
        org_id=org_id,
        repository_id=repository_id,
        user_id=user_id,
        conversation_id=conversation_id,
        revision_feedback=revision_feedback,
    )
    plan_id_container.update(result)


# ── 1. Create Feature Plan ────────────────────────────────────────────────────

@router.post(
    "/conversations/{conversation_id}/feature-plans",
    response_model=CreatePlanResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Generate a feature implementation plan from a natural language request",
)
def create_feature_plan(
    conversation_id: str,
    body: CreatePlanRequest,
    user_id: UserId,
    db: DB,
) -> CreatePlanResponse:
    """
    Runs the Feature Planner LangGraph to generate a structured implementation plan.

    The graph:
    1. Validates the repo is indexed
    2. Investigates relevant code with 4 repository intelligence tools
    3. Identifies affected files (LLM)
    4. Generates a structured task list (LLM)
    5. Persists plan → status = awaiting_approval

    This endpoint runs synchronously (returns after the plan is generated).
    For large codebases this may take 20-40 seconds.
    """
    org_id, repository_id = _get_org_id_from_conversation(db, conversation_id, user_id)

    from app.services.feature_planner_graph import run_feature_planner

    result = run_feature_planner(
        feature_request=body.feature_request,
        org_id=org_id,
        repository_id=repository_id,
        user_id=user_id,
        conversation_id=conversation_id,
    )

    if result["status"] == "failed":
        return CreatePlanResponse(
            plan_id=None,
            status="failed",
            plan_data=None,
            error_message=result.get("error_message"),
            message="Feature planning failed. See error_message for details.",
        )

    return CreatePlanResponse(
        plan_id=result["plan_id"],
        status=result["status"],
        plan_data=result["plan_data"],
        error_message=None,
        message=(
            "Implementation plan generated and is awaiting your approval. "
            "Review the tasks, then call /approve, /reject, or /request-changes."
        ),
    )


# ── 2. Get Feature Plan ───────────────────────────────────────────────────────

@router.get(
    "/feature-plans/{plan_id}",
    response_model=PlanOut,
    summary="Get full implementation plan detail with approval history",
)
def get_feature_plan(
    plan_id: str,
    user_id: UserId,
    db: DB,
) -> PlanOut:
    """Returns the plan data, current status, and full approval audit trail."""
    # Find plan first (without org check) to determine org_id for membership check
    plan = db.query(ImplementationPlan).filter(ImplementationPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Implementation plan not found")

    # Verify membership
    require_org_member(db, user_id, plan.organization_id)

    return plan


# ── 3. Approve Plan ───────────────────────────────────────────────────────────

@router.post(
    "/feature-plans/{plan_id}/approve",
    response_model=PlanOut,
    summary="Approve a feature plan — enables build execution (Phase 4)",
)
def approve_plan(
    plan_id: str,
    body: ApprovalRequest,
    user_id: UserId,
    db: DB,
) -> PlanOut:
    """
    Marks the plan as approved.

    Only plans in `awaiting_approval` status can be approved.
    Once approved, the plan is ready to be executed as a build run (Phase 4).
    """
    plan = db.query(ImplementationPlan).filter(ImplementationPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    require_org_member(db, user_id, plan.organization_id)

    if plan.status not in ("awaiting_approval",):
        raise HTTPException(
            status_code=409,
            detail=f"Plan cannot be approved in its current status: {plan.status}",
        )

    # Record approval
    approval = ImplementationApproval(
        plan_id=plan_id,
        user_id=user_id,
        action="approved",
        commit_sha_at_approval=body.commit_sha,
        comment=body.comment,
    )
    db.add(approval)

    plan.status = "approved"
    db.commit()
    db.refresh(plan)

    logger.info("Plan approved", extra={"plan_id": plan_id, "user_id": user_id})
    return plan


# ── 4. Reject Plan ────────────────────────────────────────────────────────────

@router.post(
    "/feature-plans/{plan_id}/reject",
    response_model=PlanOut,
    summary="Reject a feature plan",
)
def reject_plan(
    plan_id: str,
    body: ApprovalRequest,
    user_id: UserId,
    db: DB,
) -> PlanOut:
    """
    Rejects the plan. Terminal state — a new plan must be generated for this feature.
    """
    plan = db.query(ImplementationPlan).filter(ImplementationPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    require_org_member(db, user_id, plan.organization_id)

    if plan.status not in ("awaiting_approval",):
        raise HTTPException(
            status_code=409,
            detail=f"Plan cannot be rejected in its current status: {plan.status}",
        )

    approval = ImplementationApproval(
        plan_id=plan_id,
        user_id=user_id,
        action="rejected",
        comment=body.comment,
    )
    db.add(approval)
    plan.status = "rejected"
    db.commit()
    db.refresh(plan)

    logger.info("Plan rejected", extra={"plan_id": plan_id, "user_id": user_id})
    return plan


# ── 5. Request Changes ────────────────────────────────────────────────────────

@router.post(
    "/feature-plans/{plan_id}/request-changes",
    response_model=CreatePlanResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request changes to a plan — triggers a revised plan generation",
)
def request_changes(
    plan_id: str,
    body: RequestChangesRequest,
    user_id: UserId,
    db: DB,
) -> CreatePlanResponse:
    """
    Records a change request and triggers re-planning with the feedback incorporated.

    The original plan's status is set to `changes_requested`.
    A new plan (with version = old_version + 1) is generated and returned.
    The new plan is the one to review next.
    """
    plan = db.query(ImplementationPlan).filter(ImplementationPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    require_org_member(db, user_id, plan.organization_id)

    if plan.status not in ("awaiting_approval",):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot request changes for a plan in status: {plan.status}",
        )

    # Record the action
    approval = ImplementationApproval(
        plan_id=plan_id,
        user_id=user_id,
        action="changes_requested",
        comment=body.comment or body.feedback,
    )
    db.add(approval)
    plan.status = "changes_requested"
    db.commit()

    logger.info(
        "Plan changes requested — re-planning",
        extra={"plan_id": plan_id, "user_id": user_id},
    )

    # Re-plan with feedback
    from app.services.feature_planner_graph import run_feature_planner

    result = run_feature_planner(
        feature_request=plan.feature_request,
        org_id=plan.organization_id,
        repository_id=plan.repository_id,
        user_id=user_id,
        conversation_id=plan.conversation_id,
        revision_feedback=body.feedback,
    )

    # Bump version on the new plan
    if result.get("plan_id"):
        new_plan = db.query(ImplementationPlan).filter(
            ImplementationPlan.id == result["plan_id"]
        ).first()
        if new_plan:
            new_plan.version = plan.version + 1
            db.commit()

    if result["status"] == "failed":
        return CreatePlanResponse(
            plan_id=None,
            status="failed",
            plan_data=None,
            error_message=result.get("error_message"),
            message="Re-planning failed. See error_message for details.",
        )

    return CreatePlanResponse(
        plan_id=result["plan_id"],
        status=result["status"],
        plan_data=result["plan_data"],
        error_message=None,
        message=(
            f"Revised plan (version {plan.version + 1}) generated incorporating your feedback. "
            "Review and approve when ready."
        ),
    )
