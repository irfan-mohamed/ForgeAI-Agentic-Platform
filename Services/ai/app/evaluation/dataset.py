"""
dataset.py — Golden evaluation dataset of 35 realistic developer queries.

Used to benchmark retrieval strategies (Lexical vs Vector vs Hybrid vs Agentic)
and verify Recall@k, MRR, latency, and context token costs before choosing strategies.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EvalTestCase:
    id: str
    query: str
    category: str  # definition | route | caller | semantic | multi_file
    expected_files: list[str] = field(default_factory=list)
    expected_symbols: list[str] = field(default_factory=list)
    expected_routes: list[str] = field(default_factory=list)
    description: str = ""


EVAL_DATASET: list[EvalTestCase] = [
    # ── 1. Symbol Definition & Exact Name Queries ────────────────────────────
    EvalTestCase(
        id="def-01",
        query="where is the User model defined?",
        category="definition",
        expected_files=["app/models/user.py", "Services/api/app/models/user.py"],
        expected_symbols=["User"],
        description="Core User database model definition",
    ),
    EvalTestCase(
        id="def-02",
        query="find the definition of create_access_token",
        category="definition",
        expected_files=["app/core/security.py", "Services/api/app/core/security.py"],
        expected_symbols=["create_access_token"],
        description="JWT token creation utility",
    ),
    EvalTestCase(
        id="def-03",
        query="locate the authenticate_user function",
        category="definition",
        expected_files=["app/services/auth_service.py", "app/core/security.py"],
        expected_symbols=["authenticate_user"],
        description="User credential verification",
    ),
    EvalTestCase(
        id="def-04",
        query="where is the Repository model defined?",
        category="definition",
        expected_files=["app/models/repository.py", "Services/repository/app/models/repository.py"],
        expected_symbols=["Repository"],
        description="Repository database model",
    ),
    EvalTestCase(
        id="def-05",
        query="find the definition of get_current_user_id",
        category="definition",
        expected_files=["app/api/dependencies.py"],
        expected_symbols=["get_current_user_id"],
        description="Authentication dependency in repository service",
    ),
    EvalTestCase(
        id="def-06",
        query="show me where RepositorySync is defined",
        category="definition",
        expected_files=["app/models/repository_sync.py"],
        expected_symbols=["RepositorySync"],
        description="Repository sync record model",
    ),
    EvalTestCase(
        id="def-07",
        query="where is the CodeSymbol model located?",
        category="definition",
        expected_files=["app/models/code_symbol.py"],
        expected_symbols=["CodeSymbol"],
        description="AST symbol record model",
    ),
    EvalTestCase(
        id="def-08",
        query="find the definition of CodeRelationship",
        category="definition",
        expected_files=["app/models/code_relationship.py"],
        expected_symbols=["CodeRelationship"],
        description="Symbol relationship edge model",
    ),

    # ── 2. HTTP Route & API Surface Queries ──────────────────────────────────
    EvalTestCase(
        id="route-01",
        query="what route handles POST /conversations?",
        category="route",
        expected_files=["app/api/routes/conversations.py"],
        expected_symbols=["create_conversation"],
        expected_routes=["/organizations/{org_id}/conversations"],
        description="Create conversation API endpoint",
    ),
    EvalTestCase(
        id="route-02",
        query="show me the endpoint for GET /symbols/search",
        category="route",
        expected_files=["app/api/routes/internal.py"],
        expected_symbols=["search_symbols"],
        expected_routes=["/symbols/search"],
        description="Repository internal symbol search endpoint",
    ),
    EvalTestCase(
        id="route-03",
        query="what handles github callback requests?",
        category="route",
        expected_files=["app/api/routes/github.py"],
        expected_symbols=["github_callback"],
        expected_routes=["/github/callback"],
        description="GitHub App callback handler",
    ),
    EvalTestCase(
        id="route-04",
        query="where is the list repositories route implemented?",
        category="route",
        expected_files=["app/api/routes/repositories.py"],
        expected_symbols=["list_repositories"],
        expected_routes=["/organizations/{org_id}/repositories"],
        description="List repositories endpoint",
    ),
    EvalTestCase(
        id="route-05",
        query="which handler serves repository map requests?",
        category="route",
        expected_files=["app/api/routes/internal.py"],
        expected_symbols=["get_repo_map"],
        expected_routes=["/repo-map"],
        description="Repo map retrieval internal route",
    ),
    EvalTestCase(
        id="route-06",
        query="where is the message streaming route implemented?",
        category="route",
        expected_files=["app/api/routes/messages.py"],
        expected_symbols=["stream_messages", "stream_engineering_agent"],
        description="SSE streaming endpoint for assistant responses",
    ),
    EvalTestCase(
        id="route-07",
        query="find the pull request detail route",
        category="route",
        expected_files=["app/api/routes/pull_requests.py"],
        expected_symbols=["get_pull_request"],
        description="Get pull request details and diff patches",
    ),

    # ── 3. Callers & Dependency Graph Queries ────────────────────────────────
    EvalTestCase(
        id="call-01",
        query="who calls get_repository?",
        category="caller",
        expected_files=["app/api/routes/conversations.py", "app/api/routes/messages.py", "app/core/access.py"],
        expected_symbols=["get_repository", "_open_chat"],
        description="Access guard callers for repository verification",
    ),
    EvalTestCase(
        id="call-02",
        query="what invokes resolve_relationships?",
        category="caller",
        expected_files=["app/services/sync_service.py", "app/services/relationship_resolver.py"],
        expected_symbols=["resolve_relationships"],
        description="Worker invocation of relationship resolution",
    ),
    EvalTestCase(
        id="call-03",
        query="where is build_repo_map called?",
        category="caller",
        expected_files=["app/services/sync_service.py", "app/services/repo_map_builder.py"],
        expected_symbols=["build_repo_map"],
        description="Worker sync trigger for repo map builder",
    ),
    EvalTestCase(
        id="call-04",
        query="who imports the database session dependency get_db?",
        category="caller",
        expected_files=["app/api/routes/conversations.py", "app/api/routes/internal.py"],
        expected_symbols=["get_db"],
        description="Dependency injection callers for DB session",
    ),
    EvalTestCase(
        id="call-05",
        query="callers of decode_access_token",
        category="caller",
        expected_files=["app/api/dependencies.py", "app/core/security.py"],
        expected_symbols=["decode_access_token", "get_current_user_id"],
        description="Callers of JWT decoding logic",
    ),
    EvalTestCase(
        id="call-06",
        query="what functions call search_repository?",
        category="caller",
        expected_files=["app/services/hybrid_retriever.py", "app/services/retrieval/vector.py"],
        expected_symbols=["search_repository", "search"],
        description="Retrievers invoking Qdrant search",
    ),

    # ── 4. Semantic & Conceptual Queries ─────────────────────────────────────
    EvalTestCase(
        id="sem-01",
        query="how does JWT authentication and org membership check work?",
        category="semantic",
        expected_files=["app/core/access.py", "app/api/dependencies.py", "app/core/security.py"],
        expected_symbols=["get_org_membership", "require_org_member"],
        description="Multi-tenant authorization logic",
    ),
    EvalTestCase(
        id="sem-02",
        query="explain how files are chunked by tree-sitter AST",
        category="semantic",
        expected_files=["app/services/chunker.py", "Services/worker/app/services/chunker.py"],
        expected_symbols=["chunk_file", "PythonChunker"],
        description="Syntax-aware code chunking implementation",
    ),
    EvalTestCase(
        id="sem-03",
        query="where is the vector indexing and embedding generation logic?",
        category="semantic",
        expected_files=["app/services/embedder.py", "app/services/vector_store.py", "app/services/sync_service.py"],
        expected_symbols=["embed_texts", "upsert_vectors"],
        description="Embedding pipeline in the Worker service",
    ),
    EvalTestCase(
        id="sem-04",
        query="how does cross-file import relationship resolution work?",
        category="semantic",
        expected_files=["app/services/relationship_resolver.py"],
        expected_symbols=["resolve_relationships", "RelationshipResolver"],
        description="Resolution of symbol import edges to target symbols",
    ),
    EvalTestCase(
        id="sem-05",
        query="how are tenant filters applied to Qdrant queries?",
        category="semantic",
        expected_files=["app/services/retriever.py"],
        expected_symbols=["tenant_filter"],
        description="Mandatory organization_id and repository_id filtering",
    ),
    EvalTestCase(
        id="sem-06",
        query="where is the reciprocal rank fusion calculation structured?",
        category="semantic",
        expected_files=["app/services/hybrid_retriever.py"],
        expected_symbols=["reciprocal_rank_fusion"],
        description="RRF implementation merging search channels",
    ),
    EvalTestCase(
        id="sem-07",
        query="explain the state machine for repository sync status",
        category="semantic",
        expected_files=["app/models/repository.py", "app/models/repository_sync.py"],
        expected_symbols=["RepositoryStatus", "SyncStatus"],
        description="Lifecycle states connecting -> syncing -> indexing -> ready",
    ),
    EvalTestCase(
        id="sem-08",
        query="how does the cross-encoder reranker score code candidates?",
        category="semantic",
        expected_files=["app/services/reranker.py"],
        expected_symbols=["CodeAwareReranker", "rerank"],
        description="Neural cross-encoder and code heuristic boosts",
    ),

    # ── 5. Multi-file & Architectural Queries ────────────────────────────────
    EvalTestCase(
        id="arch-01",
        query="which files manage repository readiness checkpoints?",
        category="multi_file",
        expected_files=["app/models/repository.py", "app/services/sync_service.py", "app/core/access.py"],
        expected_symbols=["repo_map_ready_at", "chat_ready_at", "index_ready_at"],
        description="Decoupled readiness tracking across services",
    ),
    EvalTestCase(
        id="arch-02",
        query="how do models interact with database sessions across services?",
        category="multi_file",
        expected_files=["app/db/database.py", "app/db/base.py"],
        expected_symbols=["get_db", "db_session", "Base"],
        description="Database session handling and connection pools",
    ),
    EvalTestCase(
        id="arch-03",
        query="where is the pluggable retriever factory configured?",
        category="multi_file",
        expected_files=["app/services/retrieval/factory.py", "app/services/retrieval/base.py"],
        expected_symbols=["get_retriever_for_repo", "detect_repo_tier"],
        description="Selection of retriever based on repo token size",
    ),
    EvalTestCase(
        id="arch-04",
        query="how does the background worker communicate progress during indexing?",
        category="multi_file",
        expected_files=["app/services/sync_service.py", "app/models/repository_sync.py"],
        expected_symbols=["_update_progress", "RepositorySync"],
        description="Progress reporting from worker to Postgres",
    ),
    EvalTestCase(
        id="arch-05",
        query="show the relationship between Repository and RepositoryFile models",
        category="multi_file",
        expected_files=["app/models/repository.py", "app/models/repository_file.py"],
        expected_symbols=["Repository", "RepositoryFile"],
        description="Data models for connected repos and their files",
    ),
    EvalTestCase(
        id="arch-06",
        query="where are the LangGraph multi-step Q&A nodes defined?",
        category="multi_file",
        expected_files=["app/services/repo_qa_graph.py"],
        expected_symbols=["execute_tools_node", "understand_query_node"],
        description="Agent workflow graph nodes",
    ),
]
