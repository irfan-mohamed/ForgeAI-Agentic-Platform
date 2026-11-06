"""
test_phase3.py — Unit tests for Phase 3: LangGraph QA Graph + Feature Planner.

Tests are fully offline — no LLM calls, no repository service, no DB.
All external calls are mocked.

Covers:
  - repo_tools.py: tool function construction + error handling
  - repo_qa_graph.py: state helpers, routing, graph node logic
  - feature_planner_graph.py: validation, state flow, error handling
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


# ── repo_tools tests ──────────────────────────────────────────────────────────

class TestRepoTools:
    """Tests for repository intelligence tool functions."""

    def test_search_symbols_success(self):
        """search_symbols returns list on HTTP 200."""
        from app.services.repo_tools import search_symbols

        mock_data = [
            {"id": 1, "symbol_name": "login", "symbol_type": "function",
             "file_path": "app/auth.py", "start_line": 10, "end_line": 25,
             "qualified_name": "login", "language": "python",
             "is_async": False, "is_exported": True, "signature": "def login()"}
        ]

        with patch("app.services.repo_tools._repo_get", return_value=mock_data):
            result = search_symbols(1, 10, "login")

        assert len(result) == 1
        assert result[0]["symbol_name"] == "login"

    def test_search_symbols_http_error_returns_empty(self):
        """search_symbols returns empty list on error."""
        from app.services.repo_tools import search_symbols

        with patch("app.services.repo_tools._repo_get", return_value={"error": "500"}):
            result = search_symbols(1, 10, "login")

        assert result == []

    def test_get_symbol_by_name_returns_list(self):
        """get_symbol_by_name returns list correctly."""
        from app.services.repo_tools import get_symbol_by_name

        mock_data = [{"id": 5, "symbol_name": "UserService", "symbol_type": "class"}]

        with patch("app.services.repo_tools._repo_get", return_value=mock_data):
            result = get_symbol_by_name(1, 10, "UserService")

        assert result == mock_data

    def test_list_routes_returns_list(self):
        """list_routes returns routes list."""
        from app.services.repo_tools import list_routes

        mock_routes = [
            {"symbol_name": "GET /users", "file_path": "routes.py",
             "handler_symbol_name": "get_users", "handler_file_path": "routes.py",
             "qualified_name": None, "start_line": 5, "signature": None,
             "handler_symbol_id": 7}
        ]

        with patch("app.services.repo_tools._repo_get", return_value=mock_routes):
            result = list_routes(1, 10)

        assert len(result) == 1
        assert result[0]["symbol_name"] == "GET /users"

    def test_get_index_status_returns_dict(self):
        """get_index_status returns the dict directly."""
        from app.services.repo_tools import get_index_status

        mock_status = {"repository_id": 10, "status": "ready", "total_symbols": 500}

        with patch("app.services.repo_tools._repo_get", return_value=mock_status):
            result = get_index_status(1, 10)

        assert result["status"] == "ready"

    def test_get_callers_empty_on_error(self):
        """get_callers returns empty list on non-list response."""
        from app.services.repo_tools import get_callers

        with patch("app.services.repo_tools._repo_get", return_value={"error": "404"}):
            result = get_callers(1, 10, 999)

        assert result == []

    def test_get_file_structure_filters_correctly(self):
        """get_file_structure passes language filter to _repo_get."""
        from app.services.repo_tools import get_file_structure

        captured_params = {}

        def mock_repo_get(path, params=None):
            captured_params.update(params or {})
            return []

        with patch("app.services.repo_tools._repo_get", side_effect=mock_repo_get):
            get_file_structure(1, 10, language="python")

        assert captured_params.get("language") == "python"


# ── repo_qa_graph helper tests ────────────────────────────────────────────────

class TestRepoQAGraphHelpers:
    """Tests for stateless helper functions in the QA graph."""

    def test_extract_symbol_names_pascal_case(self):
        from app.services.repo_qa_graph import _extract_symbol_names
        names = _extract_symbol_names("Where is UserService defined?")
        assert "UserService" in names

    def test_extract_symbol_names_snake_case(self):
        from app.services.repo_qa_graph import _extract_symbol_names
        names = _extract_symbol_names("Who calls verify_token?")
        assert "verify_token" in names

    def test_extract_symbol_names_backtick_quoted(self):
        from app.services.repo_qa_graph import _extract_symbol_names
        names = _extract_symbol_names("What does `process_payment` do?")
        assert "process_payment" in names

    def test_extract_symbol_names_cap_at_5(self):
        from app.services.repo_qa_graph import _extract_symbol_names
        q = "UserService AuthService PaymentService EmailService NotificationService LogService"
        names = _extract_symbol_names(q)
        assert len(names) <= 5

    def test_select_tools_definition_search(self):
        from app.services.repo_qa_graph import _select_tools_for_intent
        tools = _select_tools_for_intent("DEFINITION_SEARCH", ["UserService"])
        assert "search_symbols" in tools
        assert "get_symbol_by_name" in tools

    def test_select_tools_caller_search(self):
        from app.services.repo_qa_graph import _select_tools_for_intent
        tools = _select_tools_for_intent("CALLER_SEARCH", [])
        assert "get_callers" in tools

    def test_select_tools_semantic_default(self):
        from app.services.repo_qa_graph import _select_tools_for_intent
        tools = _select_tools_for_intent("SEMANTIC_SEARCH", [])
        assert "semantic_search" in tools

    def test_select_tools_route_search(self):
        from app.services.repo_qa_graph import _select_tools_for_intent
        tools = _select_tools_for_intent("ROUTE_SEARCH", [])
        assert "list_routes" in tools

    def test_format_evidence_empty(self):
        from app.services.repo_qa_graph import _format_evidence
        result = _format_evidence([])
        assert "No code evidence" in result

    def test_format_evidence_semantic(self):
        from app.services.repo_qa_graph import _format_evidence
        evidence = [{
            "_source": "semantic_search",
            "file_path": "app/auth.py",
            "start_line": 10,
            "end_line": 25,
            "language": "python",
            "content": "def login(): pass",
        }]
        result = _format_evidence(evidence)
        assert "app/auth.py" in result
        assert "semantic" in result

    def test_format_evidence_symbol(self):
        from app.services.repo_qa_graph import _format_evidence
        evidence = [{
            "_source": "search_symbols",
            "symbol_name": "login",
            "symbol_type": "function",
            "file_path": "auth.py",
            "start_line": 10,
            "end_line": 20,
            "signature": "def login(user, password)",
        }]
        result = _format_evidence(evidence)
        assert "login" in result
        assert "auth.py" in result

    def test_should_iterate_at_max(self):
        from app.services.repo_qa_graph import should_iterate
        state = {"iterations": 3, "evidence": []}
        assert should_iterate(state) == "assemble"

    def test_should_iterate_with_few_evidence(self):
        from app.services.repo_qa_graph import should_iterate
        state = {"iterations": 0, "evidence": [{"a": 1}, {"b": 2}]}
        assert should_iterate(state) == "iterate"

    def test_should_assemble_with_enough_evidence(self):
        from app.services.repo_qa_graph import should_iterate
        state = {"iterations": 0, "evidence": [{"a": 1}] * 5}
        assert should_iterate(state) == "assemble"


# ── repo_qa_graph node tests ──────────────────────────────────────────────────

class TestRepoQANodes:
    """Tests for individual graph node functions."""

    def test_understand_query_node_extracts_intent(self):
        from app.services.repo_qa_graph import understand_query_node
        state = {
            "question": "Where is the login function defined?",
            "org_id": 1,
            "repository_id": 10,
            "conversation_history": [],
            "intent": "",
            "named_symbols": [],
            "tools_to_run": [],
            "evidence": [],
            "iterations": 0,
            "context": "",
            "answer": "",
            "citations": [],
        }
        result = understand_query_node(state)
        assert result["intent"] == "DEFINITION_SEARCH"
        assert result["iterations"] == 0

    def test_select_tools_node_returns_tools(self):
        from app.services.repo_qa_graph import select_tools_node
        state = {
            "intent": "CALLER_SEARCH",
            "named_symbols": ["login"],
            "iterations": 0,
        }
        result = select_tools_node(state)
        assert "tools_to_run" in result
        assert len(result["tools_to_run"]) > 0

    def test_select_tools_broadens_on_reiteration(self):
        from app.services.repo_qa_graph import select_tools_node
        state = {
            "intent": "DEFINITION_SEARCH",
            "named_symbols": [],
            "iterations": 1,  # Re-iteration
        }
        result = select_tools_node(state)
        assert "semantic_search" in result["tools_to_run"]

    def test_increment_iteration_node(self):
        from app.services.repo_qa_graph import increment_iteration
        state = {"iterations": 1}
        result = increment_iteration(state)
        assert result["iterations"] == 2

    def test_assemble_context_node(self):
        from app.services.repo_qa_graph import assemble_context_node
        state = {
            "evidence": [
                {
                    "_source": "semantic_search",
                    "file_path": "auth.py",
                    "start_line": 1,
                    "end_line": 10,
                    "language": "python",
                    "content": "def login(): pass",
                }
            ]
        }
        result = assemble_context_node(state)
        assert "context" in result
        assert "auth.py" in result["context"]
        assert len(result["citations"]) == 1

    def test_execute_tools_handles_exception(self):
        """execute_tools_node does not raise if a tool call fails."""
        from app.services.repo_qa_graph import execute_tools_node

        state = {
            "org_id": 1,
            "repository_id": 10,
            "question": "Who calls login?",
            "named_symbols": ["login"],
            "tools_to_run": ["semantic_search"],
            "evidence": [],
            "iterations": 0,
        }

        # Patch at the source module since the tool is lazy-imported
        with patch("app.services.repo_tools.semantic_search", side_effect=Exception("network error")):
            result = execute_tools_node(state)

        # Should not raise; should return empty new evidence
        assert "evidence" in result


# ── feature_planner_graph tests ───────────────────────────────────────────────

class TestFeaturePlannerNodes:
    """Tests for feature planner graph node functions."""

    def test_validate_request_rejects_empty_request(self):
        """Blank feature_request is rejected before any tool calls."""
        from app.services.feature_planner_graph import validate_request_node

        state = {
            "feature_request": "   ",  # blank
            "org_id": 1,
            "repository_id": 10,
        }

        # Patch at source module — get_index_status is lazy-imported from repo_tools
        with patch(
            "app.services.repo_tools.get_index_status",
            return_value={"status": "ready", "total_symbols": 100},
        ):
            result = validate_request_node(state)

        assert result["status"] == "failed"
        assert "empty" in result["error_message"].lower()

    def test_validate_request_rejects_unready_repo(self):
        """Repo not yet ready for analysis → fails fast."""
        from app.services.feature_planner_graph import validate_request_node

        state = {
            "feature_request": "Add password reset",
            "org_id": 1,
            "repository_id": 10,
        }

        with patch(
            "app.services.repo_tools.get_index_status",
            return_value={"status": "syncing", "total_symbols": 0},
        ):
            result = validate_request_node(state)

        assert result["status"] == "failed"
        assert "not ready" in result["error_message"].lower()

    def test_validate_request_passes_ready_repo(self):
        """Ready repo with non-empty request passes validation."""
        from app.services.feature_planner_graph import validate_request_node

        state = {
            "feature_request": "Add user password reset via email",
            "org_id": 1,
            "repository_id": 10,
        }

        with patch(
            "app.services.repo_tools.get_index_status",
            return_value={"status": "ready", "total_symbols": 300},
        ):
            result = validate_request_node(state)

        assert result["status"] == "investigating"

    def test_investigate_node_collects_evidence(self):
        """investigate_node calls all 4 repo tools and aggregates results."""
        from app.services.feature_planner_graph import investigate_node

        state = {
            "status": "investigating",
            "org_id": 1,
            "repository_id": 10,
            "feature_request": "Add password reset",
        }

        # Patch at source — all tools are lazy-imported from app.services.repo_tools
        with (
            patch("app.services.repo_tools.get_file_structure",
                  return_value=[{"path": "app/auth.py", "language": "python"}]),
            patch("app.services.repo_tools.list_routes", return_value=[]),
            patch("app.services.repo_tools.search_symbols", return_value=[]),
            patch("app.services.repo_tools.semantic_search", return_value=[]),
        ):
            result = investigate_node(state)

        assert len(result["repo_structure"]) == 1
        assert result["repo_structure"][0]["path"] == "app/auth.py"

    def test_investigate_node_skips_when_failed(self):
        """If status is already 'failed', investigate_node returns immediately."""
        from app.services.feature_planner_graph import investigate_node
        state = {"status": "failed"}
        result = investigate_node(state)
        assert result == {}

    def test_should_continue_planning_on_failed(self):
        from app.services.feature_planner_graph import should_continue_planning
        state = {"status": "failed"}
        assert should_continue_planning(state) == "end"

    def test_should_continue_planning_on_success(self):
        from app.services.feature_planner_graph import should_continue_planning
        state = {"status": "investigating"}
        assert should_continue_planning(state) == "continue"


# ── Graph construction sanity check ──────────────────────────────────────────

class TestGraphConstruction:
    """Sanity checks that graphs compile without error."""

    def test_qa_graph_compiles(self):
        from app.services.repo_qa_graph import build_repo_qa_graph
        graph = build_repo_qa_graph()
        assert graph is not None

    def test_planner_graph_compiles(self):
        from app.services.feature_planner_graph import build_feature_planner_graph
        graph = build_feature_planner_graph()
        assert graph is not None
