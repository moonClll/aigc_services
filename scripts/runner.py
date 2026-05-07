"""
Agent Worker Runner — the main process loop.

Polls the backend for pending tasks, builds prompts via agent_worker,
calls the LLM via llm_client, and pushes results back via callback.

Usage:
    python scripts/runner.py          # reads config from env / .env
    AI_MODE=mock python scripts/runner.py   # force mock mode
"""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_dotenv(path: Path = ROOT / ".env") -> None:
    """Load simple KEY=VALUE pairs without overriding exported env vars."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.split("#", 1)[0].strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()

from agent_worker import build_prompt_messages
from llm_client import (
    LLMError,
    LLMJsonParseError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMUpstreamError,
    call_llm,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("runner")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_BASE_URL = os.getenv("AIGC_BASE_URL", "http://127.0.0.1:8000/api/v1").rstrip("/")
_WORKER_ID = os.getenv("AI_WORKER_ID", "worker-a")
_MODEL_NAME = os.getenv("AI_MODEL", "Volc-DeepSeek-V3.2")
_POLL_INTERVAL = int(os.getenv("AI_POLL_INTERVAL", "5"))
_LEASE_SECONDS = int(os.getenv("BACKEND_TASK_LEASE_SECONDS", "300"))
_CALLBACK_TOKEN = os.getenv("BACKEND_CALLBACK_TOKEN", "")

# Heartbeat fires at 1/3 of the lease window (min 10s).
_HEARTBEAT_INTERVAL = max(10, _LEASE_SECONDS // 3)

# ---------------------------------------------------------------------------
# Graceful shutdown
# ---------------------------------------------------------------------------

_shutdown = threading.Event()


def _handle_signal(signum: int, _frame: Any) -> None:
    name = signal.Signals(signum).name
    logger.info("Received %s — shutting down after current task finishes", name)
    _shutdown.set()


# ---------------------------------------------------------------------------
# HTTP helpers (stdlib only)
# ---------------------------------------------------------------------------


def _headers() -> dict[str, str]:
    h: dict[str, str] = {"Content-Type": "application/json"}
    if _CALLBACK_TOKEN:
        h["X-Internal-Token"] = _CALLBACK_TOKEN
    return h


def _post_json(path: str, body: dict[str, Any]) -> dict[str, Any] | None:
    """POST JSON to the backend and return the parsed response envelope."""
    url = f"{_BASE_URL}{path}"
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = Request(url, data=data, headers=_headers(), method="POST")
    try:
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        err_body = ""
        try:
            err_body = exc.read().decode("utf-8", errors="replace")[:500]
        except Exception:
            pass
        logger.error("POST %s -> HTTP %d: %s", path, exc.code, err_body)
        raise
    except URLError as exc:
        logger.error("POST %s -> network error: %s", path, exc.reason)
        raise


# ---------------------------------------------------------------------------
# Backend actions
# ---------------------------------------------------------------------------


def claim_task() -> dict[str, Any] | None:
    """Claim a pending task. Returns claim data dict or None."""
    resp = _post_json(
        "/backend/tasks/claim",
        {
            "worker_id": _WORKER_ID,
            "model_name": _MODEL_NAME,
            "lease_seconds": _LEASE_SECONDS,
        },
    )
    if resp is None:
        return None
    data = resp.get("data")
    if data is None:
        return None
    logger.info(
        "Claimed task %d (conversation=%d, attempt=%d)",
        data["task_id"],
        data["conversation_id"],
        data.get("dispatch_attempts", 1),
    )
    return data


def heartbeat_loop(task_id: int, worker_id: str, stop_event: threading.Event) -> None:
    """Run heartbeat in a loop until the task finishes or process shuts down."""
    while not _shutdown.is_set() and not stop_event.wait(timeout=_HEARTBEAT_INTERVAL):
        try:
            _post_json(
                f"/backend/tasks/{task_id}/heartbeat",
                {"worker_id": worker_id, "lease_seconds": _LEASE_SECONDS},
            )
            logger.debug("Heartbeat sent for task %d", task_id)
        except Exception as exc:
            logger.warning("Heartbeat failed for task %d: %s", task_id, exc)


def start_heartbeat(task_id: int, worker_id: str) -> tuple[threading.Event, threading.Thread]:
    stop_event = threading.Event()
    t = threading.Thread(
        target=heartbeat_loop,
        args=(task_id, worker_id, stop_event),
        name=f"heartbeat-{task_id}",
        daemon=True,
    )
    t.start()
    return stop_event, t


def callback_success(claim: dict[str, Any], answer_json: dict[str, Any]) -> None:
    """Send the success callback to the backend."""
    answer_text = json.dumps(answer_json, ensure_ascii=False)
    answer_request_id = f"answer-task-{claim['task_id']}-{uuid.uuid4().hex[:8]}"

    body: dict[str, Any] = {
        "conversation_id": claim["conversation_id"],
        "generation_task_id": claim["task_id"],
        "backend_task_id": claim["backend_task_id"],
        "model_name": _MODEL_NAME,
        "answer_text": answer_text,
        "answer_request_id": answer_request_id,
        "meta_json": answer_json,
    }

    _post_json("/callbacks/model-answer", body)
    logger.info("Success callback sent for task %d", claim["task_id"])


def callback_failure(claim: dict[str, Any], error_message: str) -> None:
    """Send the failure callback to the backend."""
    body: dict[str, Any] = {
        "conversation_id": claim["conversation_id"],
        "generation_task_id": claim["task_id"],
        "backend_task_id": claim["backend_task_id"],
        "model_name": _MODEL_NAME,
        "error_message": error_message[:500],
    }

    try:
        _post_json("/callbacks/model-failure", body)
        logger.info("Failure callback sent for task %d", claim["task_id"])
    except Exception as exc:
        logger.error("Failed to send failure callback for task %d: %s", claim["task_id"], exc)


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------


def _classify_error(exc: LLMError) -> str:
    if isinstance(exc, LLMRateLimitError):
        return "rate_limit"
    if isinstance(exc, LLMTimeoutError):
        return "upstream_timeout"
    if isinstance(exc, LLMUpstreamError):
        return "upstream_unavailable"
    if isinstance(exc, LLMJsonParseError):
        return "adapter_invalid_payload"
    return "upstream_unavailable"


def _error_message(exc: LLMError) -> str:
    cls = _classify_error(exc)
    messages = {
        "rate_limit": "LLM rate limited, retry exhausted",
        "upstream_timeout": "LLM request timeout",
        "upstream_unavailable": "LLM upstream error",
        "adapter_invalid_payload": "LLM returned invalid JSON",
    }
    return messages.get(cls, str(exc))


# ---------------------------------------------------------------------------
# Process one task
# ---------------------------------------------------------------------------


def process_task(claim: dict[str, Any]) -> None:
    """Build prompt, call LLM, send callback. Always sends a callback."""
    task_id = claim["task_id"]
    worker_id = claim.get("worker_id") or _WORKER_ID

    heartbeat_stop, heartbeat_thread = start_heartbeat(task_id, worker_id)

    try:
        logger.info("Building prompt for task %d", task_id)
        messages = build_prompt_messages(claim)

        logger.info("Calling LLM for task %d", task_id)
        answer_json = call_llm(messages, task_id=task_id)

        # Validate the response contains a learning_path
        if "learning_path" not in answer_json:
            raise LLMJsonParseError("Response missing 'learning_path' key")

        logger.info("LLM returned valid learning_path for task %d", task_id)
        callback_success(claim, answer_json)

    except LLMError as exc:
        logger.warning("LLM error for task %d: %s: %s", task_id, type(exc).__name__, exc)
        callback_failure(claim, _error_message(exc))

    except Exception as exc:
        logger.exception("Unexpected error processing task %d", task_id)
        callback_failure(claim, f"Internal error: {type(exc).__name__}")

    finally:
        heartbeat_stop.set()
        heartbeat_thread.join(timeout=1)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


def run() -> None:
    logger.info("Agent Worker starting | base_url=%s worker=%s model=%s mode=%s",
                _BASE_URL, _WORKER_ID, _MODEL_NAME, os.getenv("AI_MODE", "mock"))

    while not _shutdown.is_set():
        try:
            claim = claim_task()
        except (HTTPError, URLError) as exc:
            logger.warning("Claim request failed: %s — retrying in %ds", exc, _POLL_INTERVAL)
            _shutdown.wait(timeout=_POLL_INTERVAL)
            continue

        if claim is None:
            _shutdown.wait(timeout=_POLL_INTERVAL)
            continue

        process_task(claim)

    logger.info("Agent Worker stopped")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    try:
        run()
    except Exception:
        logger.exception("Fatal error in runner")
        sys.exit(1)


if __name__ == "__main__":
    main()
