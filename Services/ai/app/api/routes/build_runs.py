"""
build_runs.py — Build Run API routes (Phase 4).

Endpoints:
  POST /api/v1/feature-plans/{plan_id}/build
      — Trigger a build run for an approved plan (202 Accepted)

  GET  /api/v1/build-runs/{build_run_id}
      — Poll build run status, test results, patches, and PR URL

  GET  /api/v1/build-runs/{build_run_id}/stream
      — SSE log stream (text/event-stream)
        Events: log | status | complete | error
        Auth: JWT from Authorization header OR ?token= query param (SSE workaround)

Security:
  - All endpoints require a valid JWT.
  - Org membership is verified on every request.

Owned by: AI Service.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.access import require_org_member
from app.core.security import UserId, decode_token
from app.db.database import get_db
from app.models.build_run import BuildRun
from app.models.plan import ImplementationPlan

logger = logging.getLogger(__name__)

router = APIRouter()
DB = Annotated[Session, Depends(get_db)]


# ── Pydantic output schemas ───────────────────────────────────────────────────

class TestSuiteOut(BaseModel):
    name: str
    passed: int
    failed: int
    errors: int
    duration: float


class TestResultsOut(BaseModel):
    passed: int
    failed: int
    errors: int
    duration: float
    exit_code: int
    suites: list[TestSuiteOut] = []
    raw_output: Optional[str] = None


class PatchOut(BaseModel):
    task_id: str
    file_path: str
    diff: str


class BuildRunOut(BaseModel):
    id: str
    plan_id: str
    organization_id: int
    repository_id: int
    triggered_by_user_id: int
    status: str
    build_log: Optional[str]
    otel_trace_id: Optional[str]
    test_results: Optional[dict]
    generated_patches: Optional[list[dict]]
    pull_request_url: Optional[str]
    pull_request_number: Optional[int]
    branch_name: Optional[str]
    error_message: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class TriggerBuildResponse(BaseModel):
    build_run_id: str
    trace_id: Optional[str]
    message: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_uuid(value: str) -> bool:
    """
    True if `value` is a syntactically valid UUID.

    Both BuildRun.id and ImplementationPlan.id are Postgres UUID columns.
    Comparing them against a malformed string raises a database error, which
    would surface as a 500 — so validate before querying.
    """
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def _load_build_run(db: Session, build_run_id: str, user_id: int) -> BuildRun:
    if not _is_uuid(build_run_id):
        raise HTTPException(status_code=404, detail="Build run not found")
    run = db.query(BuildRun).filter(BuildRun.id == build_run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Build run not found")
    require_org_member(db, user_id, run.organization_id)
    return run


def _auth_from_query_token(token: str) -> int:
    """Decode a JWT from a query parameter (SSE workaround — EventSource can't set headers)."""
    try:
        payload = decode_token(token)
        user_id = int(payload.get("sub", 0))
        if not user_id:
            raise ValueError("empty sub")
        return user_id
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token in query param",
        )


# ── 1. Trigger Build Run ──────────────────────────────────────────────────────

@router.post(
    "/feature-plans/{plan_id}/build",
    response_model=TriggerBuildResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger a build run for an approved feature plan",
)
def trigger_build_run(
    plan_id: str,
    user_id: UserId,
    db: DB,
) -> TriggerBuildResponse:
    """
    Kicks off the Phase 4 Build Execution LangGraph in a background thread.

    Prerequisites:
      - Plan must be in `approved` status.
      - User must be a member of the plan's organization.

    Returns the `build_run_id` immediately (202 Accepted).
    Poll GET /build-runs/{build_run_id} or stream GET /build-runs/{build_run_id}/stream.
    """
    plan = None
    if _is_uuid(plan_id):
        plan = db.query(ImplementationPlan).filter(ImplementationPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Implementation plan not found")
    require_org_member(db, user_id, plan.organization_id)

    if plan.status != "approved":
        raise HTTPException(
            status_code=409,
            detail=f"Plan must be in 'approved' status to trigger a build (current: {plan.status})",
        )

    # Create the BuildRun record
    build_run_id = str(uuid.uuid4())
    run = BuildRun(
        id=build_run_id,
        plan_id=plan_id,
        organization_id=plan.organization_id,
        repository_id=plan.repository_id,
        triggered_by_user_id=user_id,
        status="queued",
    )
    db.add(run)
    db.commit()

    logger.info(
        "Build run created",
        extra={"build_run_id": build_run_id, "plan_id": plan_id, "user_id": user_id},
    )

    # Capture plan_data before closing the session
    plan_data = plan.plan_data or {}
    org_id = plan.organization_id
    repository_id = plan.repository_id

    def _run_in_background():
        from app.services.build_execution_graph import run_build_execution
        run_build_execution(
            build_run_id=build_run_id,
            plan_id=plan_id,
            org_id=org_id,
            repository_id=repository_id,
            user_id=user_id,
            plan_data=plan_data,
        )

    thread = threading.Thread(target=_run_in_background, daemon=True, name=f"build-{build_run_id[:8]}")
    thread.start()

    return TriggerBuildResponse(
        build_run_id=build_run_id,
        trace_id=None,  # populated after init_run node completes
        message=(
            "Build run queued. "
            f"Stream logs at /api/v1/build-runs/{build_run_id}/stream "
            f"or poll /api/v1/build-runs/{build_run_id}."
        ),
    )


# ── 2. Get Build Run ──────────────────────────────────────────────────────────

@router.get(
    "/build-runs/{build_run_id}",
    response_model=BuildRunOut,
    summary="Get build run status, test results, patches, and PR URL",
)
def get_build_run(
    build_run_id: str,
    user_id: UserId,
    db: DB,
) -> BuildRunOut:
    """Returns the full BuildRun record. Poll every 3-5s until status is terminal."""
    run = _load_build_run(db, build_run_id, user_id)
    return run


# ── 3. SSE Log Stream ─────────────────────────────────────────────────────────

TERMINAL_STATUSES = {"pr_opened", "failed"}
SSE_POLL_INTERVAL = 1.0   # seconds between DB polls
SSE_TIMEOUT = 1800        # 30-minute hard cap


@router.get(
    "/build-runs/{build_run_id}/stream",
    summary="SSE stream of build log lines, status changes, and final result",
    response_class=StreamingResponse,
)
def stream_build_logs(
    build_run_id: str,
    request: Request,
    db: DB,
    token: Optional[str] = Query(None, description="JWT fallback for EventSource (can't set headers)"),
):
    """
    Server-Sent Events stream.

    Event types:
      log      — {"line": "..."}                 (new log line)
      status   — {"status": "..."}               (status change)
      complete — full BuildRunOut JSON            (terminal success)
      error    — {"status":"failed", ...}         (terminal failure)

    Auth: Bearer token from Authorization header OR ?token= query param.
    """
    # Resolve user identity — prefer header, fall back to query param.
    user_id: Optional[int] = None
    auth_header = request.headers.get("authorization") or ""
    if auth_header.lower().startswith("bearer "):
        try:
            payload = decode_token(auth_header.split(" ", 1)[1].strip())
            user_id = int(payload.get("sub", 0)) or None
        except Exception:
            user_id = None

    if user_id is None:
        if not token:
            raise HTTPException(status_code=401, detail="Authentication required")
        user_id = _auth_from_query_token(token)

    # Verify membership
    if not _is_uuid(build_run_id):
        raise HTTPException(status_code=404, detail="Build run not found")
    run = db.query(BuildRun).filter(BuildRun.id == build_run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Build run not found")
    require_org_member(db, user_id, run.organization_id)

    def _event(name: str, data: str) -> str:
        return f"event: {name}\ndata: {data}\n\n"

    def _generate():
        import json as _json
        from app.db.database import SessionLocal

        session = SessionLocal()
        try:
            last_log_len = 0
            last_status = None
            deadline = time.monotonic() + SSE_TIMEOUT

            while time.monotonic() < deadline:
                run_row = session.query(BuildRun).filter(BuildRun.id == build_run_id).first()
                if not run_row:
                    yield _event("error", _json.dumps({"detail": "build run disappeared"}))
                    break

                # Emit new log lines
                full_log = run_row.build_log or ""
                all_lines = [l for l in full_log.split("\n") if l]
                new_lines = all_lines[last_log_len:]
                for line in new_lines:
                    yield _event("log", _json.dumps({"line": line}))
                last_log_len = len(all_lines)

                # Emit status change
                if run_row.status != last_status:
                    last_status = run_row.status
                    yield _event("status", _json.dumps({"status": run_row.status}))

                # Terminal — emit complete/error and close
                if run_row.status in TERMINAL_STATUSES:
                    payload = {
                        "id": run_row.id,
                        "status": run_row.status,
                        "test_results": run_row.test_results,
                        "generated_patches": run_row.generated_patches,
                        "pull_request_url": run_row.pull_request_url,
                        "pull_request_number": run_row.pull_request_number,
                        "error_message": run_row.error_message,
                        "branch_name": run_row.branch_name,
                        "otel_trace_id": run_row.otel_trace_id,
                        "completed_at": run_row.completed_at.isoformat() if run_row.completed_at else None,
                    }
                    event_type = "complete" if run_row.status == "pr_opened" else "error"
                    yield _event(event_type, _json.dumps(payload))
                    break

                # Send a keepalive comment every loop to prevent proxy timeouts
                yield ": keepalive\n\n"
                session.expire_all()
                time.sleep(SSE_POLL_INTERVAL)

        except GeneratorExit:
            pass
        finally:
            session.close()

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # disable Nginx buffering
            "Connection": "keep-alive",
        },
    )
