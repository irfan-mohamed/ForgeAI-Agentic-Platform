"""
feature_planner_graph.py — LangGraph Feature Planning workflow.

Generates a structured, human-reviewable implementation plan for a feature
request. The graph runs synchronously until it reaches the
``awaiting_approval`` state, then persists the plan to PostgreSQL and returns.

Approval / rejection / change-requests happen via REST API endpoints
(not inside this graph) so that the graph does not need to be long-running.

Graph topology:
    START
      ↓
    validate_request     ← checks repo is indexed, request is actionable
      ↓
    investigate          ← gathers evidence using repo tools
      ↓
    identify_changes     ← determines which files + components are affected
      ↓
    generate_plan        ← LLM generates structured task list
      ↓
    persist_plan         ← saves to implementation_plans table
      ↓
    END  (status = awaiting_approval)

Owned by: AI Service.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, TypedDict

# All service-level imports (langgraph, settings, llm, repo_tools) are lazy
# inside functions to keep this module importable with zero transitive deps.

logger = logging.getLogger(__name__)


# ── State ─────────────────────────────────────────────────────────────────────

class PlannerState(TypedDict):
    # Input
    feature_request: str
    org_id: int
    repository_id: int
    user_id: int
    conversation_id: str | None
    revision_feedback: str | None     # Set when re-planning after changes_requested

    # Derived
    repo_structure: list[dict]
    routes: list[dict]
    relevant_symbols: list[dict]
    semantic_evidence: list[dict]
    affected_files: list[str]

    # Output
    plan_data: dict | None
    plan_id: str | None
    status: str
    error_message: str | None


# ── Nodes ─────────────────────────────────────────────────────────────────────

def validate_request_node(state: PlannerState) -> dict:
    """
    Checks that the repository is indexed and the request is non-empty.
    If not indexed, fails fast with a clear error.
    """
    from app.services.repo_tools import get_index_status  # lazy
    org_id = state["org_id"]
    repo_id = state["repository_id"]

    # Check index status
    status_data = get_index_status(org_id, repo_id)
    if "error" in status_data:
        return {
            "status": "failed",
            "error_message": f"Repository index unavailable: {status_data['error']}",
        }

    repo_status = status_data.get("status", "")
    is_ready = (
        repo_status in ("ready", "READY")
        or bool(status_data.get("chat_ready"))
        or bool(status_data.get("repo_map_ready"))
    )
    if not is_ready:
        return {
            "status": "failed",
            "error_message": (
                f"Repository is not ready for analysis (status: {repo_status}). "
                "Please wait for the sync to complete."
            ),
        }

    if not state.get("feature_request", "").strip():
        return {
            "status": "failed",
            "error_message": "Feature request cannot be empty.",
        }

    logger.info(
        "Planner: request validated",
        extra={
            "repository_id": repo_id,
            "total_symbols": status_data.get("total_symbols", 0),
            "total_files": status_data.get("total_files", 0),
        },
    )
    return {"status": "investigating"}


def investigate_node(state: PlannerState) -> dict:
    """
    Gathers evidence about the current codebase relevant to the feature request.
    Runs multiple tools in sequence to build a comprehensive picture.
    """
    if state.get("status") == "failed":
        return {}

    from app.services.repo_tools import (  # lazy
        get_file_structure, list_routes, search_symbols, semantic_search,
    )
    org_id = state["org_id"]
    repo_id = state["repository_id"]
    request = state["feature_request"]

    # Gather broad context
    structure = get_file_structure(org_id, repo_id, limit=200)
    routes = list_routes(org_id, repo_id)
    symbols = search_symbols(org_id, repo_id, request, limit=15)
    semantic = semantic_search(request, org_id, repo_id, top_k=10)

    logger.info(
        "Planner: investigation complete",
        extra={
            "files": len(structure),
            "routes": len(routes),
            "symbols": len(symbols),
            "semantic_chunks": len(semantic),
        },
    )
    return {
        "repo_structure": structure,
        "routes": routes,
        "relevant_symbols": symbols,
        "semantic_evidence": semantic,
    }


def identify_changes_node(state: PlannerState) -> dict:
    """
    Uses LLM to identify which files and components will need to change.
    Produces a focused affected_files list used in generate_plan.
    """
    if state.get("status") == "failed":
        return {}

    # Build a compact evidence summary for the LLM
    structure_summary = "\n".join(
        f"  - {f['path']} ({f.get('language') or 'unknown'})"
        for f in (state.get("repo_structure") or [])[:50]
    )
    routes_summary = "\n".join(
        f"  - {r['symbol_name']} → {r.get('handler_symbol_name', '?')} in {r['file_path']}"
        for r in (state.get("routes") or [])[:15]
    )
    symbols_summary = "\n".join(
        f"  - {s['symbol_name']} ({s['symbol_type']}) in {s['file_path']}:{s.get('start_line')}"
        for s in (state.get("relevant_symbols") or [])[:15]
    )
    semantic_summary = "\n\n".join(
        f"// {e['file_path']} (lines {e.get('start_line')}-{e.get('end_line')})\n{e['content'][:500]}"
        for e in (state.get("semantic_evidence") or [])[:5]
    )

    prompt = f"""You are a senior software architect analyzing a codebase to determine which files need to change for a new feature.

## Feature Request
{state['feature_request']}

## Current File Structure (sample)
{structure_summary or "(none)"}

## Existing Routes
{routes_summary or "(none)"}

## Relevant Symbols Found
{symbols_summary or "(none)"}

## Related Code (semantic search results)
{semantic_summary or "(none)"}

## Task
List the files that will likely need to be created or modified to implement this feature.
For each file, briefly explain what change is needed.

Respond in JSON format:
{{
  "affected_files": [
    {{"path": "services/auth.py", "action": "modify", "reason": "Add password reset logic"}},
    {{"path": "api/routes/auth.py", "action": "modify", "reason": "Add /reset-password endpoint"}},
    {{"path": "models/password_reset_token.py", "action": "create", "reason": "New model for reset tokens"}}
  ],
  "estimated_complexity": "medium"
}}

Only include files that are truly necessary. Do not add files speculatively."""

    try:
        from app.services import llm as llm_service  # lazy
        from app.core.config import settings  # lazy
        result = llm_service.chat_completion(
            [{"role": "user", "content": prompt}],
            model=settings.GROQ_CHAT_MODEL,
            temperature=0.1,
            max_tokens=1024,
        )
        data = json.loads(result.content)
        affected = [item["path"] for item in data.get("affected_files", [])]
    except Exception as exc:
        logger.warning("identify_changes LLM call failed", extra={"error": str(exc)})
        affected = []

    return {"affected_files": affected}


def generate_plan_node(state: PlannerState) -> dict:
    """
    Generates the full structured implementation plan using the LLM.
    Produces a JSON plan_data dict ready to be stored and shown to the user.
    """
    if state.get("status") == "failed":
        return {}

    affected_files_str = "\n".join(
        f"  - {f}" for f in (state.get("affected_files") or [])
    ) or "  (to be determined)"

    symbols_str = "\n".join(
        f"  - {s['symbol_name']} ({s['symbol_type']}) in {s['file_path']}"
        for s in (state.get("relevant_symbols") or [])[:10]
    )

    semantic_str = "\n\n".join(
        f"// {e['file_path']} (lines {e.get('start_line')}-{e.get('end_line')})\n{e['content'][:600]}"
        for e in (state.get("semantic_evidence") or [])[:4]
    )

    feedback_section = ""
    if state.get("revision_feedback"):
        feedback_section = f"""
## Revision Feedback from Reviewer
{state['revision_feedback']}

Please incorporate this feedback into the revised plan.
"""

    prompt = f"""You are ForgeAI Feature Planner — you create detailed, executable implementation plans for software features.

## Feature Request
{state['feature_request']}
{feedback_section}
## Files That Need To Change
{affected_files_str}

## Relevant Existing Code Symbols
{symbols_str or "(none found)"}

## Related Code Snippets
{semantic_str or "(none found)"}

## Task
Generate a detailed, step-by-step implementation plan. Each task must be:
- Self-contained and independently executable
- Specific about which file to change and exactly what to add/modify
- In the correct dependency order (no task should depend on an unfinished later task)

Respond ONLY with valid JSON in this exact format:
{{
  "title": "Short, clear feature title",
  "summary": "2-3 sentence description of the implementation approach",
  "estimated_complexity": "low|medium|high",
  "tasks": [
    {{
      "task_id": "task_01",
      "title": "Create database model for password reset tokens",
      "description": "Add a new PasswordResetToken SQLAlchemy model with fields: id, user_id, token_hash, expires_at, used_at, created_at",
      "file_action": "create",
      "file_path": "app/models/password_reset.py",
      "acceptance_criteria": "Model created with correct fields and relationships; table created in migrations"
    }},
    {{
      "task_id": "task_02",
      "title": "Add password reset service logic",
      "description": "Implement generate_reset_token() and verify_reset_token() in auth_service.py. Token should expire in 1 hour. Hash token with SHA-256 before storing.",
      "file_action": "modify",
      "file_path": "app/services/auth_service.py",
      "acceptance_criteria": "Functions generate and verify tokens correctly; expired tokens return None; used tokens cannot be reused"
    }}
  ],
  "affected_files": {json.dumps(state.get("affected_files") or [])}
}}"""

    try:
        from app.services import llm as llm_service  # lazy
        from app.core.config import settings  # lazy
        result = llm_service.chat_completion(
            [{"role": "user", "content": prompt}],
            model=settings.GROQ_CHAT_MODEL,
            temperature=0.2,
            max_tokens=3000,
        )
        # Parse JSON — handle markdown code fences
        raw = result.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```", 2)[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.rsplit("```", 1)[0]

        plan_data = json.loads(raw)
        logger.info(
            "Planner: plan generated",
            extra={"tasks": len(plan_data.get("tasks", []))},
        )
    except Exception as exc:
        logger.error("generate_plan LLM call failed", extra={"error": str(exc)})
        return {
            "status": "failed",
            "error_message": f"Failed to generate implementation plan: {exc}",
            "plan_data": None,
        }

    # Attach investigation context for transparency
    investigation_context = {
        "relevant_symbols_count": len(state.get("relevant_symbols") or []),
        "semantic_chunks_count": len(state.get("semantic_evidence") or []),
        "routes_count": len(state.get("routes") or []),
        "files_count": len(state.get("repo_structure") or []),
    }

    return {
        "plan_data": plan_data,
        "status": "plan_generated",
    }


def persist_plan_node(state: PlannerState) -> dict:
    """
    Saves the generated plan to the implementation_plans table.
    Sets status to awaiting_approval.
    """
    if state.get("status") == "failed" or not state.get("plan_data"):
        return {}

    from app.db.database import db_session
    from app.models.plan import ImplementationPlan

    plan_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    with db_session() as db:
        plan = ImplementationPlan(
            id=plan_id,
            organization_id=state["org_id"],
            repository_id=state["repository_id"],
            created_by_user_id=state["user_id"],
            conversation_id=state.get("conversation_id"),
            feature_request=state["feature_request"],
            plan_data=state["plan_data"],
            investigation_context={
                "relevant_symbols_count": len(state.get("relevant_symbols") or []),
                "semantic_chunks_count": len(state.get("semantic_evidence") or []),
                "affected_files": state.get("affected_files") or [],
                "revision_feedback": state.get("revision_feedback"),
            },
            status="awaiting_approval",
            version=1,
        )
        db.add(plan)

    logger.info(
        "Planner: plan persisted",
        extra={"plan_id": plan_id, "tasks": len(state["plan_data"].get("tasks", []))},
    )
    return {"plan_id": plan_id, "status": "awaiting_approval"}


def should_continue_planning(state: PlannerState) -> str:
    """Routes away from investigation if validation failed."""
    if state.get("status") == "failed":
        return "end"
    return "continue"


# ── Graph Construction ────────────────────────────────────────────────────────

def build_feature_planner_graph() -> Any:
    """Builds and compiles the feature planner LangGraph."""
    from langgraph.graph import END, START, StateGraph  # lazy import

    builder = StateGraph(PlannerState)

    builder.add_node("validate_request", validate_request_node)
    builder.add_node("investigate", investigate_node)
    builder.add_node("identify_changes", identify_changes_node)
    builder.add_node("generate_plan", generate_plan_node)
    builder.add_node("persist_plan", persist_plan_node)

    builder.add_edge(START, "validate_request")
    builder.add_conditional_edges(
        "validate_request",
        should_continue_planning,
        {"continue": "investigate", "end": END},
    )
    builder.add_edge("investigate", "identify_changes")
    builder.add_edge("identify_changes", "generate_plan")
    builder.add_conditional_edges(
        "generate_plan",
        should_continue_planning,
        {"continue": "persist_plan", "end": END},
    )
    builder.add_edge("persist_plan", END)

    return builder.compile()


_planner_graph = None


def get_feature_planner_graph() -> Any:
    global _planner_graph
    if _planner_graph is None:
        _planner_graph = build_feature_planner_graph()
    return _planner_graph


# ── Public entry point ────────────────────────────────────────────────────────

def run_feature_planner(
    feature_request: str,
    org_id: int,
    repository_id: int,
    user_id: int,
    conversation_id: str | None = None,
    revision_feedback: str | None = None,
) -> dict:
    """
    Run the feature planning graph.

    Returns:
        plan_id:   UUID string of the persisted plan (if successful)
        status:    'awaiting_approval' | 'failed'
        plan_data: The structured plan dict
        error_message: Set if status == 'failed'
    """
    graph = get_feature_planner_graph()

    initial_state: PlannerState = {
        "feature_request": feature_request,
        "org_id": org_id,
        "repository_id": repository_id,
        "user_id": user_id,
        "conversation_id": conversation_id,
        "revision_feedback": revision_feedback,
        "repo_structure": [],
        "routes": [],
        "relevant_symbols": [],
        "semantic_evidence": [],
        "affected_files": [],
        "plan_data": None,
        "plan_id": None,
        "status": "pending_investigation",
        "error_message": None,
    }

    try:
        final_state = graph.invoke(initial_state)
    except Exception as exc:
        logger.error("Feature planner graph failed", extra={"error": str(exc)})
        return {
            "plan_id": None,
            "status": "failed",
            "plan_data": None,
            "error_message": f"Planning failed: {exc}",
        }

    return {
        "plan_id": final_state.get("plan_id"),
        "status": final_state.get("status", "failed"),
        "plan_data": final_state.get("plan_data"),
        "error_message": final_state.get("error_message"),
    }
