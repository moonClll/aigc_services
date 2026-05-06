"""
LLM client for the vivo platform.

Supports two modes controlled by AI_MODE env var:
  - mock : returns a fixed learning path JSON (no network call)
  - real : calls vivo /v1/chat/completions with retry and error classification
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger("llm_client")

# ---------------------------------------------------------------------------
# Configuration (read once at import time)
# ---------------------------------------------------------------------------

_AI_MODE = os.getenv("AI_MODE", "mock").strip().lower()  # "mock" | "real"
_VIVO_API_URL = os.getenv("VIVO_API_URL", "https://api-ai.vivo.com.cn/v1/chat/completions")
_VIVO_APP_KEY = os.getenv("VIVO_APP_KEY", "")
_AI_MODEL = os.getenv("AI_MODEL", "Volc-DeepSeek-V3.2")
_AI_TIMEOUT = int(os.getenv("AI_TIMEOUT", "60"))
_AI_MAX_RETRIES = int(os.getenv("AI_MAX_RETRIES", "3"))


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class LLMError(Exception):
    """Base error for LLM calls."""


class LLMJsonParseError(LLMError):
    """LLM returned content that could not be parsed as JSON."""


class LLMRateLimitError(LLMError):
    """Upstream rate limit (429)."""


class LLMTimeoutError(LLMError):
    """Request timed out."""


class LLMUpstreamError(LLMError):
    """Upstream 5xx or network error."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_json_from_content(content: str) -> dict[str, Any]:
    """Extract a JSON object from LLM content, tolerating markdown wrappers."""
    content = content.strip()

    # 1) Direct parse
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # 2) Extract from ```json ... ``` or ``` ... ```
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", content, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 3) Find outermost { ... }
    start = content.find("{")
    end = content.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(content[start : end + 1])
        except json.JSONDecodeError:
            pass

    raise LLMJsonParseError("LLM response is not valid JSON")


def _classify_http_error(status_code: int) -> type[LLMError]:
    if status_code == 429:
        return LLMRateLimitError
    if 500 <= status_code < 600:
        return LLMUpstreamError
    return LLMUpstreamError


# ---------------------------------------------------------------------------
# Mock response
# ---------------------------------------------------------------------------

_MOCK_LEARNING_PATH = {
    "learning_path": {
        "title": "Mock Learning Path",
        "goal": "Demonstrate the end-to-end agent flow with a sample path",
        "nodes": [
            {
                "node_code": "step_01",
                "title": "Introduction and Overview",
                "node_type": "lesson",
                "description": "Understand the core concepts and why this topic matters.",
                "est_minutes": 15,
                "sort_no": 1,
                "parent_node_code": None,
            },
            {
                "node_code": "step_02",
                "title": "Core Fundamentals",
                "node_type": "lesson",
                "description": "Learn the foundational knowledge needed to progress.",
                "est_minutes": 30,
                "sort_no": 2,
                "parent_node_code": "step_01",
            },
            {
                "node_code": "step_03",
                "title": "Knowledge Check",
                "node_type": "checkpoint",
                "description": "Verify your understanding of the fundamentals.",
                "est_minutes": 10,
                "sort_no": 3,
                "parent_node_code": "step_02",
            },
            {
                "node_code": "step_04",
                "title": "Hands-on Practice",
                "node_type": "practice",
                "description": "Apply what you learned through a practical exercise.",
                "est_minutes": 45,
                "sort_no": 4,
                "parent_node_code": "step_03",
            },
            {
                "node_code": "step_05",
                "title": "Summary and Next Steps",
                "node_type": "resource",
                "description": "Review key takeaways and explore further resources.",
                "est_minutes": 10,
                "sort_no": 5,
                "parent_node_code": "step_04",
            },
        ],
    }
}


def _mock_call() -> dict[str, Any]:
    return _MOCK_LEARNING_PATH


# ---------------------------------------------------------------------------
# Real vivo API call (stdlib only, no requests/httpx)
# ---------------------------------------------------------------------------


def _real_call(messages: list[dict[str, str]], task_id: int | str | None = None) -> dict[str, Any]:
    """Call vivo /v1/chat/completions with retry and error classification."""
    if not _VIVO_APP_KEY:
        raise LLMUpstreamError("VIVO_APP_KEY is not configured")

    last_exc: LLMError | None = None

    for attempt in range(1, _AI_MAX_RETRIES + 1):
        request_id = uuid.uuid4().hex
        payload = {
            "requestId": request_id,
            "model": _AI_MODEL,
            "messages": messages,
            "stream": False,
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        req = Request(
            _VIVO_API_URL,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {_VIVO_APP_KEY}",
            },
            method="POST",
        )

        start = time.monotonic()
        try:
            with urlopen(req, timeout=_AI_TIMEOUT) as resp:
                raw = resp.read().decode("utf-8")

            elapsed_ms = int((time.monotonic() - start) * 1000)
            data: dict[str, Any] = json.loads(raw)

            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            logger.info(
                "LLM ok | task=%s req=%s elapsed=%dms tokens=%s",
                task_id,
                request_id,
                elapsed_ms,
                usage.get("total_tokens"),
            )
            return _parse_json_from_content(content)

        except HTTPError as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            status_code = exc.code
            err_cls = _classify_http_error(status_code)

            try:
                err_body = exc.read().decode("utf-8", errors="replace")[:500]
            except Exception:
                err_body = ""

            logger.warning(
                "LLM HTTP %d | task=%s req=%s elapsed=%dms attempt=%d/%d body=%s",
                status_code,
                task_id,
                request_id,
                elapsed_ms,
                attempt,
                _AI_MAX_RETRIES,
                err_body,
            )
            last_exc = err_cls(f"HTTP {status_code}")

        except (TimeoutError, URLError) as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            logger.warning(
                "LLM timeout/network | task=%s req=%s elapsed=%dms attempt=%d/%d err=%s",
                task_id,
                request_id,
                elapsed_ms,
                attempt,
                _AI_MAX_RETRIES,
                exc,
            )
            last_exc = LLMTimeoutError(str(exc))

        except (KeyError, IndexError, json.JSONDecodeError) as exc:
            logger.warning(
                "LLM bad response | task=%s req=%s attempt=%d/%d err=%s",
                task_id,
                request_id,
                attempt,
                _AI_MAX_RETRIES,
                exc,
            )
            last_exc = LLMJsonParseError(str(exc))

        # Backoff before retry (skip on last attempt)
        if attempt < _AI_MAX_RETRIES:
            backoff = min(2**attempt, 10) * (0.5 + 0.5 * (hash(request_id) % 100) / 100)
            logger.info("Retrying in %.1fs...", backoff)
            time.sleep(backoff)

    raise last_exc  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def call_llm(messages: list[dict[str, str]], task_id: int | str | None = None) -> dict[str, Any]:
    """
    Call the LLM and return the parsed JSON result.

    Args:
        messages: list of {"role": ..., "content": ...} dicts from agent_worker.
        task_id: optional, used only for log correlation.

    Returns:
        Parsed JSON dict (e.g. {"learning_path": {...}}).

    Raises:
        LLMError (or subclass) on failure.
    """
    if _AI_MODE == "mock":
        logger.info("MOCK mode | task=%s — returning fixed learning path", task_id)
        return _mock_call()

    return _real_call(messages, task_id=task_id)
