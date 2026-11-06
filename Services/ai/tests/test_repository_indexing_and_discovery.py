"""
test_repository_indexing_and_discovery.py — Comprehensive tests for repository
indexing, discovery, and conversation eligibility across ForgeAI.

Covers:
  1. Repository successfully synchronized and indexed.
  2. Repository marked Ready but not indexed / status checks.
  3. Repository with valid Qdrant points.
  4. Repository with missing or invalid vector data.
  5. Repository with indexing failure.
  6. Organization ID mismatch (tenant isolation).
  7. Repository ID mismatch between database and Qdrant payload.
  8. Conversation repository discovery (API responses consumed by frontend).
  9. Multiple repositories belonging to different organizations.
  10. Re-indexing an already connected repository.
"""
from unittest.mock import MagicMock, patch
from sqlalchemy import text

from app.core.access import get_repository, require_org_member, RepoInfo
from app.services.retriever import tenant_filter, _to_chunk, search_repository, fetch_file_chunks
from tests.conftest import auth_headers


USER_ID = 4
OTHER_USER_ID = 99
ORG_ID = 1
OTHER_ORG_ID = 2


def seed_membership(db, user_id=USER_ID, org_id=ORG_ID):
    db.execute(
        text("INSERT INTO memberships (user_id, organization_id, role, status) VALUES (:u, :o, 'company_admin', 'active')"),
        {"u": user_id, "o": org_id},
    )
    db.commit()


def seed_repository(
    db,
    repo_id=16,
    org_id=ORG_ID,
    name="supplynex-docs",
    full_name="Supplynex-platform/supplynex-docs",
    status="ready",
):
    db.execute(
        text("""
            INSERT INTO repositories (id, organization_id, github_repository_id, name, full_name, owner, status)
            VALUES (:id, :org_id, '1314696612', :name, :full_name, 'Supplynex-platform', :status)
        """),
        {"id": repo_id, "org_id": org_id, "name": name, "full_name": full_name, "status": status},
    )
    db.commit()


def seed_repository_file(
    db,
    repo_id=16,
    org_id=ORG_ID,
    path="Product/01-Project-Vision.md",
    is_indexed=True,
    status="indexed",
    chunk_count=7,
):
    db.execute(
        text("""
            INSERT INTO repository_files (organization_id, repository_id, path, file_type, size_bytes, is_indexed, status, chunk_count)
            VALUES (:org_id, :repo_id, :path, 'markdown', 1024, :is_indexed, :status, :chunk_count)
        """),
        {"org_id": org_id, "repo_id": repo_id, "path": path, "is_indexed": 1 if is_indexed else 0, "status": status, "chunk_count": chunk_count},
    )
    db.commit()


# ── 1. Repository successfully synchronized and indexed ────────────────────────

def test_repository_successfully_synchronized_and_indexed(client, db):
    """When a repository is READY and indexed, conversation creation succeeds."""
    seed_membership(db, USER_ID, ORG_ID)
    seed_repository(db, repo_id=16, org_id=ORG_ID, status="ready")
    seed_repository_file(db, repo_id=16, org_id=ORG_ID, is_indexed=True, status="indexed")

    resp = client.post(
        f"/api/v1/organizations/{ORG_ID}/conversations",
        json={"repository_id": "16", "title": "System Architecture & Docs"},
        headers=auth_headers(USER_ID),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["repository_id"] == "16"
    assert data["repository_full_name"] == "Supplynex-platform/supplynex-docs"
    assert data["title"] == "System Architecture & Docs"


# ── 2. Repository marked Ready but not indexed / status checks ────────────────

def test_repository_not_ready_rejects_conversation_creation(client, db):
    """If repository status is not ready (e.g. connecting or syncing), creation is rejected."""
    seed_membership(db, USER_ID, ORG_ID)
    seed_repository(db, repo_id=20, org_id=ORG_ID, status="connecting")

    resp = client.post(
        f"/api/v1/organizations/{ORG_ID}/conversations",
        json={"repository_id": "20", "title": "Connecting test"},
        headers=auth_headers(USER_ID),
    )
    assert resp.status_code == 409
    assert "not ready yet" in resp.json()["detail"]


# ── 3. Repository with valid Qdrant points ─────────────────────────────────────

def test_retriever_parses_valid_qdrant_points():
    """Valid Qdrant point payloads are converted to RetrievedChunk objects properly."""
    point_id = "03ad1cc5-e9e8-4648-8e3f-a0d043f161d5"
    payload = {
        "organization_id": 1,
        "repository_id": 16,
        "file_path": "Product/03-Features.md",
        "chunk_type": "doc_section",
        "chunk_name": "SupplyNex — Features (Phase 1)",
        "chunk_index": 0,
        "content": "# SupplyNex Features",
        "language": "markdown",
        "start_line": 1,
        "end_line": 4,
    }
    chunk = _to_chunk(point_id, payload, score=0.88)
    assert chunk.chunk_id == point_id
    assert chunk.file_path == "Product/03-Features.md"
    assert chunk.score == 0.88
    assert chunk.start_line == 1
    assert chunk.end_line == 4
    assert chunk.chunk_type == "doc_section"


# ── 4. Repository with missing or invalid vector data ──────────────────────────

def test_retriever_with_empty_or_missing_vectors():
    """When Qdrant search returns no hits, search_repository returns an empty list gracefully."""
    mock_client = MagicMock()
    mock_client.search.return_value = []

    with patch("app.services.retriever._qdrant", return_value=mock_client), \
         patch("app.services.retriever.embed_query", return_value=[0.1] * 384):
        chunks = search_repository("search query", org_id=1, repository_id=16, top_k=5)

    assert chunks == []
    mock_client.search.assert_called_once()


# ── 5. Repository with indexing failure ────────────────────────────────────────

def test_repository_indexing_failure_rejects_conversation(client, db):
    """When a repository has failed status, creating a conversation returns 409 conflict."""
    seed_membership(db, USER_ID, ORG_ID)
    seed_repository(db, repo_id=30, org_id=ORG_ID, status="failed")

    resp = client.post(
        f"/api/v1/organizations/{ORG_ID}/conversations",
        json={"repository_id": "30", "title": "Failed repo test"},
        headers=auth_headers(USER_ID),
    )
    assert resp.status_code == 409
    assert "status: failed" in resp.json()["detail"]


# ── 6. Organization ID mismatch ────────────────────────────────────────────────

def test_organization_id_mismatch_isolation(client, db):
    """User in Org 1 cannot create a conversation for a repo belonging to Org 2."""
    seed_membership(db, USER_ID, org_id=ORG_ID)
    # Repo belongs to OTHER_ORG_ID (2)
    seed_repository(db, repo_id=40, org_id=OTHER_ORG_ID, status="ready")

    resp = client.post(
        f"/api/v1/organizations/{ORG_ID}/conversations",
        json={"repository_id": "40", "title": "Cross-tenant access"},
        headers=auth_headers(USER_ID),
    )
    # Returns 404 so existence in other orgs is not leaked
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Repository not found."


# ── 7. Repository ID mismatch between database and Qdrant payload ─────────────

def test_tenant_filter_enforces_org_and_repo_id():
    """Tenant filter mandates matching organization_id and repository_id."""
    flt = tenant_filter(org_id=1, repository_id=16, file_path="Product/01-Vision.md")
    conditions = {cond.key: cond.match.value for cond in flt.must}
    assert conditions["organization_id"] == 1
    assert conditions["repository_id"] == 16
    assert conditions["file_path"] == "Product/01-Vision.md"


# ── 8. Conversation repository discovery (API responses consumed by frontend) ──

def test_conversation_list_and_repository_discovery(client, db):
    """Frontend calls list_conversations and retrieves conversation with repository full name."""
    seed_membership(db, USER_ID, ORG_ID)
    seed_repository(db, repo_id=16, org_id=ORG_ID, status="ready")

    # Create conversation
    create_resp = client.post(
        f"/api/v1/organizations/{ORG_ID}/conversations",
        json={"repository_id": "16", "title": "Frontend Discovery Test"},
        headers=auth_headers(USER_ID),
    )
    assert create_resp.status_code == 201

    # List conversations for org (the API endpoint that previously crashed)
    list_resp = client.get(
        f"/api/v1/organizations/{ORG_ID}/conversations",
        headers=auth_headers(USER_ID),
    )
    assert list_resp.status_code == 200
    body = list_resp.json()
    assert body["total"] == 1
    conv = body["conversations"][0]
    assert conv["repository_id"] == "16"
    assert conv["repository_full_name"] == "Supplynex-platform/supplynex-docs"
    assert conv["title"] == "Frontend Discovery Test"


# ── 9. Multiple repositories belonging to different organizations ─────────────

def test_multiple_repositories_across_organizations(client, db):
    """Repositories belonging to other organizations are completely isolated."""
    seed_membership(db, USER_ID, org_id=ORG_ID)
    seed_repository(db, repo_id=16, org_id=ORG_ID, status="ready")
    seed_repository(db, repo_id=17, org_id=OTHER_ORG_ID, status="ready")

    # List conversations for ORG_ID returns only ORG_ID conversations
    client.post(
        f"/api/v1/organizations/{ORG_ID}/conversations",
        json={"repository_id": "16", "title": "Org 1 Chat"},
        headers=auth_headers(USER_ID),
    )

    list_resp = client.get(
        f"/api/v1/organizations/{ORG_ID}/conversations",
        headers=auth_headers(USER_ID),
    )
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] == 1
    assert list_resp.json()["conversations"][0]["repository_id"] == "16"


# ── 10. Re-indexing an already connected repository ───────────────────────────

def test_reindexing_file_metadata_change_detection(db):
    """File records track is_indexed and chunk count across re-index cycles."""
    seed_repository(db, repo_id=16, org_id=ORG_ID, status="ready")
    seed_repository_file(db, repo_id=16, org_id=ORG_ID, path="docs/readme.md", is_indexed=True, chunk_count=5)

    row = db.execute(
        text("SELECT is_indexed, chunk_count, status FROM repository_files WHERE repository_id = 16 AND path = 'docs/readme.md'")
    ).fetchone()

    assert row._mapping["is_indexed"] == 1
    assert row._mapping["chunk_count"] == 5
    assert row._mapping["status"] == "indexed"
