"""
llm.py — Groq client, token counting, and chat-completion helper.

Uses the Groq API which is fully OpenAI-compatible: just swap the base_url
and api_key. Every agent calls the model through this module so tests can
replace a single function.

Groq provides ultra-fast inference for open-source models (Llama 3, Mixtral, etc.)
at very low cost with a generous free tier.

Groq API docs: https://console.groq.com/docs
Compatible endpoint: https://api.groq.com/openai/v1
"""
import logging
from dataclasses import dataclass

from openai import OpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)

_client: OpenAI | None = None
_encoder = None
_encoder_failed = False


class LLMNotConfigured(RuntimeError):
    """Raised when GROQ_API_KEY is missing."""


@dataclass
class LLMResult:
    content: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


def openai_client() -> OpenAI:
    """
    Returns the process-wide Groq client (created on first use).

    The OpenAI SDK works directly with Groq's API — just point base_url
    at https://api.groq.com/openai/v1 and use your Groq API key.
    Get a free key at: https://console.groq.com
    """
    global _client
    if not settings.GROQ_API_KEY:
        raise LLMNotConfigured(
            "GROQ_API_KEY is not configured for the AI service. "
            "Get a free key at https://console.groq.com"
        )
    if _client is None:
        _client = OpenAI(
            api_key=settings.GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1",
        )
        logger.info(
            "Groq client initialized",
            extra={"chat_model": settings.GROQ_CHAT_MODEL},
        )
    return _client


def _get_encoder():
    global _encoder, _encoder_failed
    if _encoder is not None or _encoder_failed:
        return _encoder
    try:
        import tiktoken
        _encoder = tiktoken.get_encoding("cl100k_base")
    except Exception as exc:
        _encoder_failed = True
        logger.warning(
            "tiktoken unavailable — falling back to character-based estimates",
            extra={"error": str(exc)},
        )
    return _encoder


def count_tokens(text: str) -> int:
    """Counts tokens (approximately len/4 if tiktoken cannot be loaded)."""
    encoder = _get_encoder()
    if encoder is None:
        return max(1, len(text) // 4)
    return len(encoder.encode(text))


def truncate_to_tokens(text: str, max_tokens: int) -> str:
    """Cuts ``text`` down to at most ``max_tokens`` tokens."""
    if count_tokens(text) <= max_tokens:
        return text
    encoder = _get_encoder()
    if encoder is None:
        return text[: max_tokens * 4]
    return encoder.decode(encoder.encode(text)[:max_tokens])


def chat_completion(
    messages: list[dict],
    *,
    model: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 2048,
    json_mode: bool = False,
) -> LLMResult:
    """Runs a non-streaming chat completion via Groq and returns text plus token usage."""
    kwargs: dict = {
        "model": model or settings.GROQ_CHAT_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    response = openai_client().chat.completions.create(**kwargs)
    choice = response.choices[0]
    usage = response.usage
    return LLMResult(
        content=choice.message.content or "",
        prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
        completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
        total_tokens=getattr(usage, "total_tokens", 0) or 0,
    )
