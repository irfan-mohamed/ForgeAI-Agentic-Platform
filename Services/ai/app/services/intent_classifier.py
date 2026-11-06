"""
intent_classifier.py — Fast rule-based query intent detection.

Classifies a user query into a retrieval strategy so the hybrid retriever
can weight its search channels appropriately.

Design:
  1. Rule-based patterns first (fast, no LLM cost).
  2. If no pattern matches, fall back to SEMANTIC_SEARCH (default).

Intent values:
    DEFINITION_SEARCH  — "where is X defined?", "find the definition of X"
    REFERENCE_SEARCH   — "where is X used?", "who uses X?"
    CALLER_SEARCH      — "who calls X?", "what calls authenticate?"
    CALLEE_SEARCH      — "what does X call?", "what functions does login call?"
    ROUTE_SEARCH       — "what route handles /api/users?", "find the endpoint for login"
    SEMANTIC_SEARCH    — everything else (default)
"""

import re
from typing import NamedTuple


class Intent(NamedTuple):
    intent: str           # One of the INTENT_* constants below
    subject: str | None   # Extracted subject term (e.g. "login", "UserService")


# ── Intent constants ──────────────────────────────────────────────────────────

DEFINITION_SEARCH = "DEFINITION_SEARCH"
REFERENCE_SEARCH  = "REFERENCE_SEARCH"
CALLER_SEARCH     = "CALLER_SEARCH"
CALLEE_SEARCH     = "CALLEE_SEARCH"
ROUTE_SEARCH      = "ROUTE_SEARCH"
SEMANTIC_SEARCH   = "SEMANTIC_SEARCH"


# ── Patterns ──────────────────────────────────────────────────────────────────
# Each tuple: (compiled_pattern, intent_constant)
# Patterns are tested in order; the first match wins.

_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Route / endpoint search
    (re.compile(
        r'\b(?:route|endpoint|api|url|path)\b.{0,30}\b(?:for|handles?|maps?\s+to|serves?)\b'
        r'|which\s+(?:route|handler|endpoint)',
        re.IGNORECASE,
    ), ROUTE_SEARCH),

    # Definition search
    (re.compile(
        r'\b(?:where\s+is|find|locate|show\s+me)\b.{0,40}\b(?:defined?|declared?|implemented?)\b'
        r'|definition\s+of\b'
        r'|\bwhere\s+(?:is|are|can\s+I\s+find)\b.{0,40}\bclass\b'
        r'|\bwhere\s+(?:is|are|can\s+I\s+find)\b.{0,40}\bfunction\b'
        r'|\blocate\b.{0,50}\b(?:function|class|method|module|service|handler)\b',
        re.IGNORECASE,
    ), DEFINITION_SEARCH),

    # Caller search — "who calls X" / "what calls X"
    (re.compile(
        r'\bwho\s+calls?\b'
        r'|\bwhat\s+(?:code\s+)?calls?\b'
        r'|\bcallers?\s+of\b'
        r'|\bwhat\s+(?:invokes?|triggers?|calls?)\b',
        re.IGNORECASE,
    ), CALLER_SEARCH),

    # Callee search — "what does X call"
    (re.compile(
        r'\bwhat\s+does\b.{0,40}\bcalls?\b'
        r'|\bwhat\s+(?:functions?|methods?)\s+does\b.{0,30}\b(?:call|use|invoke)\b'
        r'|\bcallees?\s+of\b'
        r'|\bdependencies\s+of\b',
        re.IGNORECASE,
    ), CALLEE_SEARCH),

    # Reference / usage search
    (re.compile(
        r'\bwhere\b.{0,40}\b(?:used?|referenced?|imported?|consumed?)\b'
        r'|\bwho\s+(?:uses?|imports?|references?)\b'
        r'|\busages?\s+of\b'
        r'|\breferences?\s+to\b',
        re.IGNORECASE,
    ), REFERENCE_SEARCH),
]


# ── Subject extraction ────────────────────────────────────────────────────────

# Tries to extract a symbol/identifier name from the query
_SUBJECT_PATTERNS = [
    re.compile(r'["`\']([\w.]+)["`\']'),              # quoted: `login`, "UserService"
    re.compile(r'\bfor\s+([\w.]+)\b', re.IGNORECASE), # "for login"
    re.compile(r'\bof\s+([\w.]+)\b', re.IGNORECASE),  # "callers of authenticate"
    re.compile(r'\b([\w]+Service|[\w]+Manager|[\w]+Handler|[\w]+Controller)\b'),  # class-like names
    re.compile(r'\b([a-z_][a-z0-9_]{3,})\b'),         # snake_case function name (≥4 chars)
]


def _extract_subject(query: str) -> str | None:
    """Attempts to extract the primary subject of the query."""
    for pattern in _SUBJECT_PATTERNS:
        m = pattern.search(query)
        if m:
            candidate = m.group(1)
            # Skip common stop words
            if candidate.lower() not in {
                "where", "what", "who", "which", "the", "this", "that",
                "find", "show", "code", "file", "function", "class", "method",
            }:
                return candidate
    return None


# ── Public API ────────────────────────────────────────────────────────────────

def classify(query: str) -> Intent:
    """
    Classify a user query into a retrieval intent.

    Returns an Intent namedtuple with:
        intent  — one of the INTENT_* constants
        subject — the main symbol/term being asked about, if detectable

    Examples:
        classify("where is the login function defined?")
        → Intent(intent='DEFINITION_SEARCH', subject='login')

        classify("who calls authenticate?")
        → Intent(intent='CALLER_SEARCH', subject='authenticate')

        classify("how does the payment system work?")
        → Intent(intent='SEMANTIC_SEARCH', subject='payment')
    """
    for pattern, intent in _PATTERNS:
        if pattern.search(query):
            return Intent(intent=intent, subject=_extract_subject(query))
    return Intent(intent=SEMANTIC_SEARCH, subject=_extract_subject(query))
