"""
Message routes — the core AI interaction endpoints.

POST /api/v1/conversations/{id}/messages           — send message, get response
GET  /api/v1/conversations/{id}/messages/stream    — SSE streaming response
POST /api/v1/conversations/{id}/test-assistance    — ask the Testing Agent
GET  /api/v1/agent-runs/{id}                       — inspect a run

Flow for every AI call:
  1. Authorize: conversation owner + organization member + repository ready
  2. Save the user message and an AgentRun (RUNNING) and COMMIT, so the
     record survives even if the model call fails
  3. Run the agent (no database transaction is held during the model call)
  4. Save the assistant message and finish the AgentRun
"""
import json
import logging
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.access import (
    RepoInfo,
    get_repository,
    load_user_conversation,
    parse_id,
)
from app.core.config import settings
from app.core.security import BearerToken, UserId
from app.db.database import db_session, get_db
from app.models.conversation import (
    AgentRun,
    AgentStatus,
    AgentType,
    Conversation,
    Message,
    MessageRole,
)
from app.services import repository_client
from app.services.engineering_agent import (
    AgentResult,
    run_engineering_agent,
    stream_engineering_agent,
)
from app.services.testing_agent import TargetNotFound, run_testing_agent

logger = logging.getLogger(__name__)

router = APIRouter()

DB = Annotated[Session, Depends(get_db)]

_AI_FAILED = "The AI request failed. Please try again."


# ── Schemas ───────────────────────────────────────────────────────────────────

class SendMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=8000)


class SendMessageResponse(BaseModel):
    message_id: str
    agent_run_id: str
    status: str
    content: str


class TestAssistanceRequest(BaseModel):
    file_path: str | None = Field(default=None, max_length=500)
    pull_number: int | None = Field(default=None, ge=1)
    instructions: str | None = Field(default=None, max_length=2000)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _open_chat(db: Session, conversation_id: str, user_id: int) -> tuple[Conversation, RepoInfo]:
    """Authorizes access and returns the conversation plus its verified repository."""
    conv = load_user_conversation(db, conversation_id, user_id)
    if not conv.repository_id:
        raise HTTPException(status_code=400, detail="Conversation has no repository attached")
    repo = get_repository(
        db,
        parse_id(conv.org_id, "organization id"),
        parse_id(conv.repository_id, "repository id"),
        require_ready=True,
    )
    return conv, repo


def _recent_history(db: Session, conversation_id: str) -> list[dict]:
    """The latest messages of the conversation, oldest first, in OpenAI format."""
    rows = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(settings.CHAT_HISTORY_MAX_MESSAGES)
        .all()
    )
    rows.reverse()
    return [{"role": m.role.value.lower(), "content": m.content} for m in rows]


def _record_question(
    db: Session,
    conversation_id: str,
    content: str,
    agent_type: AgentType,
) -> str:
    """Saves the user message + a RUNNING AgentRun, commits, returns the run id."""
    user_msg = Message(
        conversation_id=conversation_id,
        role=MessageRole.USER,
        content=content,
    )
    db.add(user_msg)
    db.flush()  # assigns user_msg.id

    run = AgentRun(
        conversation_id=conversation_id,
        user_message_id=user_msg.id,
        agent_type=agent_type,
        status=AgentStatus.RUNNING,
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.commit()
    return run.id


def _complete_run(
    db: Session,
    conversation_id: str,
    run_id: str,
    content: str,
    chunk_ids: list[str],
    completion_tokens: int | None,
    total_tokens: int | None,
) -> str:
    """Saves the assistant reply, finishes the run, returns the assistant message id."""
    now = datetime.now(timezone.utc)
    assistant_msg = Message(
        conversation_id=conversation_id,
        role=MessageRole.ASSISTANT,
        content=content,
        token_count=completion_tokens,
    )
    db.add(assistant_msg)
    db.flush()

    run = db.get(AgentRun, run_id)
    run.status = AgentStatus.COMPLETED
    run.assistant_message_id = assistant_msg.id
    run.retrieved_chunk_ids = ",".join(chunk_ids) if chunk_ids else None
    run.total_tokens = total_tokens
    run.completed_at = now

    conv = db.get(Conversation, conversation_id)
    conv.updated_at = now

    message_id = assistant_msg.id
    db.commit()
    return message_id


def _fail_run(db: Session, run_id: str, exc: BaseException) -> None:
    """Marks a run FAILED. The full error is logged, not returned to the client."""
    logger.error("Agent run failed", extra={"run_id": run_id, "error": str(exc)})
    db.rollback()
    run = db.get(AgentRun, run_id)
    if run is not None:
        run.status = AgentStatus.FAILED
        run.error_message = str(exc)[:2000]
        run.completed_at = datetime.now(timezone.utc)
        db.commit()


def _finish_result(
    db: Session,
    conversation_id: str,
    run_id: str,
    result: AgentResult,
) -> SendMessageResponse:
    message_id = _complete_run(
        db,
        conversation_id,
        run_id,
        result.content,
        result.retrieved_chunk_ids,
        result.completion_tokens,
        result.total_tokens,
    )
    return SendMessageResponse(
        message_id=message_id,
        agent_run_id=run_id,
        status="COMPLETED",
        content=result.content,
    )


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=SendMessageResponse,
)
def send_message(
    conversation_id: str,
    body: SendMessageRequest,
    user_id: UserId,
    db: DB,
):
    """
    Send a message and receive the AI response synchronously.

    Best for: integrations, testing, simple clients.
    Use /stream for real-time UX.
    """
    conv, repo = _open_chat(db, conversation_id, user_id)
    history = _recent_history(db, conv.id)
    conv_id = conv.id
    run_id = _record_question(db, conv_id, body.content, AgentType.ENGINEERING)
    # Use the stored full name; fall back to the live repo record if the
    # conversation was created before the full_name column was added.
    repository_name = conv.repository_full_name or repo.full_name

    try:
        result = run_engineering_agent(
            question=body.content,
            conversation_history=history,
            org_id=repo.organization_id,
            repository_id=repo.id,
            repository_name=repository_name,
        )
    except Exception as exc:
        _fail_run(db, run_id, exc)
        raise HTTPException(status_code=502, detail=_AI_FAILED)

    return _finish_result(db, conv_id, run_id, result)


@router.get("/conversations/{conversation_id}/messages/stream")
def stream_message(
    conversation_id: str,
    user_id: UserId,
    db: DB,
    content: str = Query(min_length=1, max_length=8000),
):
    """
    Send a message and receive the AI response as a Server-Sent Events stream.

    Each event is ``data: <JSON string>`` holding one text token; an error is
    sent as ``data: {"error": "..."}``; the stream always ends with
    ``data: [DONE]``.

    ``EventSource`` cannot send an Authorization header, so clients should use
    ``fetch`` with a streaming reader (the ForgeAI frontend does).
    """
    conv, repo = _open_chat(db, conversation_id, user_id)
    history = _recent_history(db, conv.id)
    conv_id = conv.id
    run_id = _record_question(db, conv_id, content, AgentType.ENGINEERING)

    org_id = repo.organization_id
    repository_id = repo.id
    repository_name = conv.repository_full_name or repo.full_name

    def event_generator():
        parts: list[str] = []
        meta: dict = {}

        try:
            for token in stream_engineering_agent(
                question=content,
                conversation_history=history,
                org_id=org_id,
                repository_id=repository_id,
                repository_name=repository_name,
                meta=meta,
            ):
                parts.append(token)
                yield f"data: {json.dumps(token)}\n\n"

            # The request's DB session may already be closed while streaming,
            # so finish the run with a session of our own.
            with db_session() as stream_db:
                _complete_run(
                    stream_db,
                    conv_id,
                    run_id,
                    "".join(parts),
                    meta.get("retrieved_chunk_ids", []),
                    meta.get("completion_tokens"),
                    meta.get("total_tokens"),
                )

        except GeneratorExit:
            # Client went away mid-answer.
            with db_session() as stream_db:
                _fail_run(stream_db, run_id, RuntimeError("Client disconnected"))
            raise

        except Exception as exc:
            with db_session() as stream_db:
                _fail_run(stream_db, run_id, exc)
            yield f"data: {json.dumps({'error': _AI_FAILED})}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # Disable nginx buffering for SSE
        },
    )


@router.post(
    "/conversations/{conversation_id}/test-assistance",
    response_model=SendMessageResponse,
)
def test_assistance(
    conversation_id: str,
    body: TestAssistanceRequest,
    user_id: UserId,
    token: BearerToken,
    db: DB,
):
    """
    Ask the Testing Agent for missing tests for a file and/or a pull request.

    The suggestion is saved in the conversation like any other answer. Nothing
    is written to the repository.
    """
    file_path = (body.file_path or "").strip() or None
    if not file_path and body.pull_number is None:
        raise HTTPException(
            status_code=422,
            detail="Provide a file_path or a pull_number.",
        )

    conv, repo = _open_chat(db, conversation_id, user_id)
    conv_id = conv.id

    pr = None
    if body.pull_number is not None:
        pr = repository_client.get_pull_request(repo.id, body.pull_number, token)

    target = file_path or f"pull request #{body.pull_number}"
    if file_path and body.pull_number is not None:
        target = f"{file_path} (pull request #{body.pull_number})"
    question = f"Generate tests for {target}."
    if body.instructions:
        question += f"\n\n{body.instructions.strip()}"

    run_id = _record_question(db, conv_id, question, AgentType.TESTING)

    try:
        result = run_testing_agent(
            org_id=repo.organization_id,
            repository_id=repo.id,
            repository_name=repo.full_name,
            file_path=file_path,
            pr=pr,
            instructions=body.instructions,
        )
    except TargetNotFound:
        _fail_run(db, run_id, RuntimeError("File not found in repository knowledge"))
        raise HTTPException(
            status_code=404,
            detail="That file was not found in the indexed repository. Check the path.",
        )
    except Exception as exc:
        _fail_run(db, run_id, exc)
        raise HTTPException(status_code=502, detail=_AI_FAILED)

    return _finish_result(db, conv_id, run_id, result)


@router.get("/agent-runs/{agent_run_id}")
def get_agent_run(
    agent_run_id: str,
    user_id: UserId,
    db: DB,
):
    """Get the status and metadata of an agent run (owner only)."""
    run = db.get(AgentRun, agent_run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Agent run not found")
    # Raises 404/403 unless the caller owns the conversation and is still a member.
    load_user_conversation(db, run.conversation_id, user_id)
    return {
        "id": run.id,
        "conversation_id": run.conversation_id,
        "type": run.agent_type.value,
        "status": run.status.value,
        "total_tokens": run.total_tokens,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "error_message": run.error_message,
    }
