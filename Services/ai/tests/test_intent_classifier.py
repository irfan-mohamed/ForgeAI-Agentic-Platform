"""
test_intent_classifier.py — Unit tests for the query intent classifier.

All tests are fully offline, no external deps.
"""
import pytest

from app.services.intent_classifier import (
    classify,
    DEFINITION_SEARCH,
    REFERENCE_SEARCH,
    CALLER_SEARCH,
    CALLEE_SEARCH,
    ROUTE_SEARCH,
    SEMANTIC_SEARCH,
    Intent,
)


class TestDefinitionSearch:
    def test_where_is_defined(self):
        assert classify("where is the login function defined?").intent == DEFINITION_SEARCH

    def test_find_definition_of(self):
        assert classify("find the definition of UserService").intent == DEFINITION_SEARCH

    def test_locate(self):
        assert classify("locate the authenticate function").intent == DEFINITION_SEARCH

    def test_where_is_class(self):
        assert classify("where is the AuthManager class?").intent == DEFINITION_SEARCH

    def test_show_me_implemented(self):
        assert classify("show me where payment is implemented").intent == DEFINITION_SEARCH


class TestCallerSearch:
    def test_who_calls(self):
        assert classify("who calls authenticate?").intent == CALLER_SEARCH

    def test_what_calls(self):
        assert classify("what calls the login function?").intent == CALLER_SEARCH

    def test_callers_of(self):
        assert classify("callers of verify_password").intent == CALLER_SEARCH

    def test_what_invokes(self):
        assert classify("what invokes the payment handler?").intent == CALLER_SEARCH


class TestCalleeSearch:
    def test_what_does_x_call(self):
        assert classify("what does login call?").intent == CALLEE_SEARCH

    def test_what_functions_does_x_use(self):
        assert classify("what functions does authenticate use?").intent == CALLEE_SEARCH

    def test_dependencies_of(self):
        assert classify("dependencies of UserService").intent == CALLEE_SEARCH


class TestReferenceSearch:
    def test_where_used(self):
        assert classify("where is UserService used?").intent == REFERENCE_SEARCH

    def test_who_imports(self):
        assert classify("who imports the auth module?").intent == REFERENCE_SEARCH

    def test_references_to(self):
        assert classify("references to generate_access_token").intent == REFERENCE_SEARCH

    def test_usages_of(self):
        assert classify("usages of the db connection").intent == REFERENCE_SEARCH


class TestRouteSearch:
    def test_what_route_handles(self):
        assert classify("what route handles /api/users?").intent == ROUTE_SEARCH

    def test_which_handler(self):
        assert classify("which handler serves the login endpoint?").intent == ROUTE_SEARCH

    def test_endpoint_for(self):
        assert classify("what endpoint maps to user login?").intent == ROUTE_SEARCH


class TestSemanticSearch:
    def test_how_does_payment_work(self):
        assert classify("how does the payment system work?").intent == SEMANTIC_SEARCH

    def test_explain_auth(self):
        assert classify("explain the authentication flow").intent == SEMANTIC_SEARCH

    def test_what_is_the_architecture(self):
        assert classify("what is the overall architecture?").intent == SEMANTIC_SEARCH

    def test_vague_question(self):
        assert classify("tell me about the codebase").intent == SEMANTIC_SEARCH

    def test_empty_string(self):
        # Should not raise
        result = classify("")
        assert result.intent == SEMANTIC_SEARCH


class TestSubjectExtraction:
    def test_extracts_backtick_quoted(self):
        result = classify("where is `login` defined?")
        assert result.subject == "login"

    def test_extracts_after_of(self):
        result = classify("callers of authenticate")
        assert result.subject == "authenticate"

    def test_extracts_service_class_name(self):
        result = classify("what does UserService do?")
        assert result.subject == "UserService"

    def test_returns_none_for_stop_words_only(self):
        result = classify("what is this?")
        # subject should not be a stop word
        assert result.subject not in {"what", "this", "is", None} or result.subject is None

    def test_returns_intent_and_subject(self):
        result = classify("where is authenticate defined?")
        assert isinstance(result, Intent)
        assert result.intent == DEFINITION_SEARCH
        # Subject extraction is best-effort; just check it's a string or None
        assert result.subject is None or isinstance(result.subject, str)


class TestHybridRetrieverRRF:
    """Tests for the RRF merging logic (no I/O)."""

    def test_rrf_boosts_item_in_both_lists(self):
        from app.services.hybrid_retriever import reciprocal_rank_fusion

        semantic = [("a", 0.9), ("b", 0.7), ("c", 0.5)]
        symbol  = [("b", 1.0), ("d", 0.8), ("e", 0.3)]

        scores = reciprocal_rank_fusion(semantic, symbol)

        # "b" appears in both lists — should beat "a" (semantic-only, rank 1)
        assert scores["b"] > scores["a"], (
            f"Item in both lists should outscore item in one list: b={scores['b']:.4f} a={scores['a']:.4f}"
        )

    def test_rrf_all_items_present(self):
        from app.services.hybrid_retriever import reciprocal_rank_fusion

        sem = [("x", 0.9), ("y", 0.7)]
        lex = [("y", 1.0), ("z", 0.5)]

        scores = reciprocal_rank_fusion(sem, lex)
        assert set(scores.keys()) == {"x", "y", "z"}

    def test_rrf_empty_lists(self):
        from app.services.hybrid_retriever import reciprocal_rank_fusion

        scores = reciprocal_rank_fusion([], [])
        assert scores == {}

    def test_rrf_single_list(self):
        from app.services.hybrid_retriever import reciprocal_rank_fusion

        scores = reciprocal_rank_fusion([("a", 0.9), ("b", 0.5)])
        assert scores["a"] > scores["b"]

    def test_rrf_k_parameter(self):
        from app.services.hybrid_retriever import reciprocal_rank_fusion

        sem = [("a", 1.0)]
        scores_60 = reciprocal_rank_fusion(sem, k=60)
        scores_1  = reciprocal_rank_fusion(sem, k=1)
        # Lower k → higher scores (less damping)
        assert scores_1["a"] > scores_60["a"]
