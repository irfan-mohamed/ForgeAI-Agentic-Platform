"""
test_feature_plans_api.py — Integration tests for feature plan REST API endpoints.
"""
import uuid
from unittest.mock import patch
from sqlalchemy import text

from app.models.conversation import Conversation
from app.models.plan import ImplementationPlan
from tests.conftest import auth_headers

USER_ID = 4
ORG_ID = 1
REPO_ID = 16


def seed_membership(db, user_id=USER_ID, org_id=ORG_ID):
    db.execute(
        text("INSERT INTO memberships (user_id, organization_id, role, status) VALUES (:u, :o, 'company_admin', 'active')"),
        {"u": user_id, "o": org_id},
    )
    db.commit()


def seed_conversation(db, conv_id="conv-123", user_id=USER_ID, org_id=ORG_ID, repo_id=REPO_ID):
    convo = Conversation(
        id=conv_id,
        org_id=str(org_id),
        user_id=str(user_id),
        repository_id=str(repo_id) if repo_id is not None else None,
        title="Test Conversation",
    )
    db.add(convo)
    db.commit()
    return convo


def seed_plan(db, plan_id=None, org_id=ORG_ID, repo_id=REPO_ID, user_id=USER_ID, status="awaiting_approval"):
    pid = plan_id or str(uuid.uuid4())
    plan = ImplementationPlan(
        id=pid,
        organization_id=org_id,
        repository_id=repo_id,
        created_by_user_id=user_id,
        feature_request="Add rate limiting middleware",
        status=status,
        plan_data={"title": "Rate Limiting", "tasks": []},
        version=1,
    )
    db.add(plan)
    db.commit()
    return plan


def test_create_feature_plan_resolves_convo_attributes(client, db):
    """POST /conversations/{id}/feature-plans resolves org_id and repository_id without AttributeError."""
    seed_membership(db, USER_ID, ORG_ID)
    seed_conversation(db, conv_id="conv-123", user_id=USER_ID, org_id=ORG_ID, repo_id=REPO_ID)

    mock_result = {
        "status": "awaiting_approval",
        "plan_id": str(uuid.uuid4()),
        "plan_data": {"title": "Test Plan", "tasks": []},
    }

    with patch("app.services.feature_planner_graph.run_feature_planner", return_value=mock_result) as mock_runner:
        resp = client.post(
            "/api/v1/conversations/conv-123/feature-plans",
            json={"feature_request": "Implement OAuth2 login with Google"},
            headers=auth_headers(USER_ID),
        )
        assert resp.status_code == 202
        data = resp.json()
        assert data["plan_id"] == mock_result["plan_id"]
        assert data["status"] == "awaiting_approval"

        # Verify correct args passed to runner
        mock_runner.assert_called_once_with(
            feature_request="Implement OAuth2 login with Google",
            org_id=ORG_ID,
            repository_id=REPO_ID,
            user_id=USER_ID,
            conversation_id="conv-123",
        )


def test_create_feature_plan_conversation_without_repo(client, db):
    """POST /conversations/{id}/feature-plans returns 400 if conversation has no repository_id."""
    seed_membership(db, USER_ID, ORG_ID)
    seed_conversation(db, conv_id="conv-norepo", user_id=USER_ID, org_id=ORG_ID, repo_id=None)

    resp = client.post(
        "/api/v1/conversations/conv-norepo/feature-plans",
        json={"feature_request": "Implement OAuth2 login with Google"},
        headers=auth_headers(USER_ID),
    )
    assert resp.status_code == 400
    assert "not associated with any repository" in resp.json()["detail"]


def test_get_and_approve_feature_plan(client, db):
    """GET and POST approve feature plan verifies org membership in correct order."""
    seed_membership(db, USER_ID, ORG_ID)
    plan = seed_plan(db, org_id=ORG_ID, repo_id=REPO_ID, user_id=USER_ID)

    # 1. GET
    resp = client.get(
        f"/api/v1/feature-plans/{plan.id}",
        headers=auth_headers(USER_ID),
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == plan.id

    # 2. Approve
    resp = client.post(
        f"/api/v1/feature-plans/{plan.id}/approve",
        json={"comment": "Looks solid, approved for execution."},
        headers=auth_headers(USER_ID),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"
    assert len(resp.json()["approvals"]) == 1
    assert resp.json()["approvals"][0]["action"] == "approved"


def test_reject_feature_plan(client, db):
    """POST reject sets status to rejected."""
    seed_membership(db, USER_ID, ORG_ID)
    plan = seed_plan(db, org_id=ORG_ID, repo_id=REPO_ID, user_id=USER_ID)

    resp = client.post(
        f"/api/v1/feature-plans/{plan.id}/reject",
        json={"comment": "Approach not aligned with requirements."},
        headers=auth_headers(USER_ID),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"
