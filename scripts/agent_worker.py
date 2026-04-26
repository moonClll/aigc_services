import json
import os
import random
import signal
import socket
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib import request
from urllib.error import HTTPError, URLError


@dataclass
class WorkerConfig:
    base_url: str
    internal_token: str | None
    worker_id: str
    model_name: str
    poll_interval_seconds: float
    heartbeat_interval_seconds: float
    lease_seconds: int
    backend_request_timeout_seconds: float
    upstream_timeout_seconds: float
    total_task_timeout_seconds: float
    upstream_max_retries: int
    retry_base_delay_seconds: float
    retry_max_delay_seconds: float
    retry_jitter_seconds: float
    vivo_api_url: str
    vivo_app_key: str | None


class UpstreamCallError(RuntimeError):
    def __init__(
        self,
        category: str,
        message: str,
        recoverable: bool,
        *,
        status_code: int | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.recoverable = recoverable
        self.status_code = status_code
        self.detail = detail or {}


def _env_int(name: str, default: int, minimum: int | None = None) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        value = default
    else:
        value = int(raw)
    if minimum is not None:
        value = max(minimum, value)
    return value


def _env_float(name: str, default: float, minimum: float | None = None) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        value = default
    else:
        value = float(raw)
    if minimum is not None:
        value = max(minimum, value)
    return value


def load_config() -> WorkerConfig:
    base_url = os.getenv("AIGC_BASE_URL", "http://127.0.0.1:8000/api/v1").rstrip("/")
    backend_timeout = _env_float("AGENT_BACKEND_REQUEST_TIMEOUT_SECONDS", 30.0, minimum=1.0)
    legacy_timeout = os.getenv("AGENT_REQUEST_TIMEOUT_SECONDS")
    if legacy_timeout is not None and legacy_timeout.strip() != "":
        backend_timeout = max(1.0, float(legacy_timeout))

    return WorkerConfig(
        base_url=base_url,
        internal_token=os.getenv("BACKEND_CALLBACK_TOKEN") or os.getenv("AGENT_INTERNAL_TOKEN"),
        worker_id=os.getenv("AGENT_WORKER_ID", "agent-worker-1"),
        model_name=os.getenv("AGENT_MODEL_NAME", "Volc-DeepSeek-V3.2"),
        poll_interval_seconds=_env_float("AGENT_POLL_INTERVAL_SECONDS", 2.0, minimum=0.2),
        heartbeat_interval_seconds=_env_float("AGENT_HEARTBEAT_INTERVAL_SECONDS", 20.0, minimum=1.0),
        lease_seconds=_env_int("AGENT_LEASE_SECONDS", 300, minimum=30),
        backend_request_timeout_seconds=backend_timeout,
        upstream_timeout_seconds=_env_float("AGENT_UPSTREAM_TIMEOUT_SECONDS", 60.0, minimum=1.0),
        total_task_timeout_seconds=_env_float("AGENT_TOTAL_TASK_TIMEOUT_SECONDS", 180.0, minimum=5.0),
        upstream_max_retries=_env_int("AGENT_UPSTREAM_MAX_RETRIES", 2, minimum=0),
        retry_base_delay_seconds=_env_float("AGENT_RETRY_BASE_DELAY_SECONDS", 1.0, minimum=0.1),
        retry_max_delay_seconds=_env_float("AGENT_RETRY_MAX_DELAY_SECONDS", 8.0, minimum=0.2),
        retry_jitter_seconds=_env_float("AGENT_RETRY_JITTER_SECONDS", 0.4, minimum=0.0),
        vivo_api_url=os.getenv("VIVO_API_URL", "https://api-ai.vivo.com.cn/v1/chat/completions"),
        vivo_app_key=os.getenv("VIVO_APP_KEY"),
    )


def log_event(level: str, message: str, trace: dict[str, Any] | None = None, **extra: Any) -> None:
    payload: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "message": message,
    }
    if trace:
        payload.update(trace)
    if extra:
        payload.update(extra)
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def post_json(
    url: str,
    payload: dict[str, Any],
    timeout_seconds: float,
    internal_token: str | None = None,
    bearer_token: str | None = None,
) -> tuple[int, dict[str, Any]]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if internal_token:
        headers["X-Internal-Token"] = internal_token
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"

    req = request.Request(url, data=body, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=timeout_seconds) as resp:
            status_code = resp.status
            raw = resp.read().decode("utf-8")
            parsed = json.loads(raw) if raw else {}
            return status_code, parsed
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, {"raw_error": raw}
    except TimeoutError as exc:
        return 599, {"error": str(exc), "timeout": True}
    except socket.timeout as exc:
        return 599, {"error": str(exc), "timeout": True}
    except URLError as exc:
        timeout_flag = isinstance(exc.reason, TimeoutError) or isinstance(exc.reason, socket.timeout)
        return 599, {"error": str(exc), "timeout": timeout_flag}


def _as_short_json(data: Any, max_len: int = 500) -> str:
    rendered = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    if len(rendered) <= max_len:
        return rendered
    return rendered[: max_len - 3] + "..."


def _is_content_blocked(data: dict[str, Any]) -> bool:
    raw = _as_short_json(data, max_len=1000).lower()
    keywords = (
        "moderation",
        "content blocked",
        "content policy",
        "safety",
        "blocked",
        "审核",
        "拦截",
    )
    return any(word in raw for word in keywords)


def classify_upstream_error(status_code: int, data: dict[str, Any]) -> UpstreamCallError:
    if status_code == 429:
        return UpstreamCallError(
            "rate_limit",
            "LLM rate limited, retry exhausted",
            True,
            status_code=status_code,
            detail=data,
        )

    if status_code == 599:
        if data.get("timeout"):
            return UpstreamCallError(
                "upstream_timeout",
                "LLM request timeout",
                True,
                status_code=status_code,
                detail=data,
            )
        return UpstreamCallError(
            "upstream_unavailable",
            "LLM upstream unavailable",
            True,
            status_code=status_code,
            detail=data,
        )

    if 500 <= status_code <= 599:
        return UpstreamCallError(
            "upstream_unavailable",
            "LLM upstream 5xx",
            True,
            status_code=status_code,
            detail=data,
        )

    if _is_content_blocked(data):
        return UpstreamCallError(
            "content_blocked",
            "Request blocked by upstream moderation",
            False,
            status_code=status_code,
            detail=data,
        )

    if 400 <= status_code <= 499:
        return UpstreamCallError(
            "adapter_invalid_payload",
            "Invalid model payload or request rejected by upstream",
            False,
            status_code=status_code,
            detail=data,
        )

    return UpstreamCallError(
        "upstream_unavailable",
        f"Unexpected upstream status={status_code}",
        True,
        status_code=status_code,
        detail=data,
    )


def _remaining_seconds(deadline: float) -> float:
    return max(0.0, deadline - time.monotonic())


def _normalize_prompt_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value)


def _format_context_block(claim: dict[str, Any]) -> str:
    context_payload = {
        "conversation_id": claim.get("conversation_id"),
        "task_id": claim.get("task_id"),
        "backend_task_id": claim.get("backend_task_id"),
        "frontend_request_id": claim.get("frontend_request_id"),
        "question_meta_json": claim.get("question_meta_json"),
        "feedback_id": claim.get("feedback_id"),
        "feedback_rating": claim.get("feedback_rating"),
        "feedback_reason": claim.get("feedback_reason"),
        "feedback_detail": claim.get("feedback_detail"),
    }
    return _as_short_json(context_payload, max_len=5000)


def build_prompt_messages(claim: dict[str, Any]) -> list[dict[str, str]]:
    question_text = _normalize_prompt_text(claim.get("question_text"))
    if not question_text:
        raise UpstreamCallError(
            "adapter_invalid_payload",
            "Invalid model payload: missing question_text",
            False,
        )

    feedback_rating = _normalize_prompt_text(claim.get("feedback_rating"))
    feedback_reason = _normalize_prompt_text(claim.get("feedback_reason"))
    feedback_detail = _normalize_prompt_text(claim.get("feedback_detail"))

    system_prompt = (
        "You are a learning assistant. Provide clear, actionable, and verifiable guidance. "
        "Keep responses safe and educational."
    )
    policy_lines = [
        "Prefer a staged plan when the user asks for learning or implementation steps.",
        "Each stage should contain objective, concrete tasks, and acceptance criteria.",
    ]
    if feedback_rating or feedback_reason or feedback_detail:
        policy_lines.append(
            "This is a regenerate request based on feedback. Keep useful parts and explicitly fix issues raised in feedback."
        )

    policy_prompt = "\n".join(policy_lines)
    context_prompt = _format_context_block(claim)
    user_prompt = question_text

    return [
        {"role": "system", "content": f"[SYSTEM]\n{system_prompt}"},
        {"role": "system", "content": f"[POLICY]\n{policy_prompt}"},
        {"role": "system", "content": f"[CONTEXT]\n{context_prompt}"},
        {"role": "user", "content": f"[USER]\n{user_prompt}"},
    ]


def _build_answer_request_id(claim: dict[str, Any], request_id: str) -> str:
    task_id = claim.get("task_id")
    compact = request_id.replace("-", "")[:20]
    return f"ans-{task_id}-{compact}"


def _backoff_delay_seconds(cfg: WorkerConfig, retry_index: int) -> float:
    exponential = cfg.retry_base_delay_seconds * (2 ** retry_index)
    jitter = random.uniform(0.0, cfg.retry_jitter_seconds)
    return min(cfg.retry_max_delay_seconds, exponential + jitter)


def _build_failure_message(exc: Exception) -> str:
    if isinstance(exc, UpstreamCallError):
        return f"{exc.category}: {str(exc)}"
    return f"internal_worker_error: {str(exc)}"


def call_vivo_completion_once(
    cfg: WorkerConfig,
    claim: dict[str, Any],
    request_id: str,
    deadline: float,
) -> str:
    if not cfg.vivo_app_key:
        raise RuntimeError("VIVO_APP_KEY is required for LLM calls")

    messages = build_prompt_messages(claim)
    payload = {
        "requestId": request_id,
        "model": cfg.model_name,
        "stream": False,
        "messages": messages,
    }

    remaining = _remaining_seconds(deadline)
    if remaining <= 0:
        raise UpstreamCallError(
            "upstream_timeout",
            "total task timeout exhausted before upstream call",
            False,
        )

    upstream_timeout = min(cfg.upstream_timeout_seconds, remaining)
    status_code, data = post_json(
        cfg.vivo_api_url,
        payload,
        timeout_seconds=upstream_timeout,
        bearer_token=cfg.vivo_app_key,
    )
    if status_code != 200:
        raise classify_upstream_error(status_code, data)

    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise UpstreamCallError(
            "adapter_invalid_payload",
            "Invalid model payload: upstream response missing choices",
            False,
            status_code=status_code,
            detail=data,
        )

    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        raise UpstreamCallError(
            "adapter_invalid_payload",
            "Invalid model payload: upstream response missing message",
            False,
            status_code=status_code,
            detail=data,
        )

    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise UpstreamCallError(
            "adapter_invalid_payload",
            "Invalid model payload: upstream response empty content",
            False,
            status_code=status_code,
            detail=data,
        )

    return content.strip()


def call_vivo_completion_with_retry(
    cfg: WorkerConfig,
    claim: dict[str, Any],
    trace_base: dict[str, Any],
    deadline: float,
) -> tuple[str, str]:
    max_attempts = cfg.upstream_max_retries + 1

    for attempt in range(1, max_attempts + 1):
        request_id = str(uuid.uuid4())
        trace = {**trace_base, "requestId": request_id, "attempt": attempt}
        try:
            answer_text = call_vivo_completion_once(cfg, claim, request_id, deadline)
            log_event("INFO", "upstream completion success", trace)
            return answer_text, request_id
        except UpstreamCallError as exc:
            exc.detail.setdefault("requestId", request_id)
            log_event(
                "WARN" if exc.recoverable else "ERROR",
                "upstream completion failed",
                trace,
                error_category=exc.category,
                error_message=str(exc),
                upstream_status=exc.status_code,
            )
            if not exc.recoverable or attempt >= max_attempts:
                raise

            delay = _backoff_delay_seconds(cfg, attempt - 1)
            delay = min(delay, _remaining_seconds(deadline))
            if delay <= 0:
                raise UpstreamCallError(
                    "upstream_timeout",
                    "total task timeout exhausted before retry",
                    False,
                    detail={"requestId": request_id},
                )
            log_event("INFO", "retrying upstream completion", trace, sleep_seconds=round(delay, 3))
            time.sleep(delay)


def callback_success(
    cfg: WorkerConfig,
    claim: dict[str, Any],
    request_id: str,
    answer_request_id: str,
    answer_text: str,
    trace: dict[str, Any],
) -> None:
    payload = {
        "conversation_id": claim["conversation_id"],
        "generation_task_id": claim["task_id"],
        "backend_task_id": claim["backend_task_id"],
        "question_message_id": claim["question_message_id"],
        "model_name": cfg.model_name,
        "answer_text": answer_text,
        "answer_request_id": answer_request_id,
        "assets": [],
        "meta_json": {
            "agent_trace": {
                "requestId": request_id,
                "answer_request_id": answer_request_id,
                "worker_id": cfg.worker_id,
            },
            "prompt_mapping": {
                "question_text": "[USER]",
                "question_meta_json": "[CONTEXT].question_meta_json",
                "feedback_*": "[CONTEXT].feedback_*",
            },
        },
    }
    status_code, data = post_json(
        f"{cfg.base_url}/callbacks/model-answer",
        payload,
        timeout_seconds=cfg.backend_request_timeout_seconds,
        internal_token=cfg.internal_token,
    )
    if status_code != 200 or data.get("code") != 0:
        raise RuntimeError(f"model-answer callback failed status={status_code}, body={data}")
    log_event("INFO", "model-answer callback success", trace)


def callback_failure(
    cfg: WorkerConfig,
    claim: dict[str, Any],
    error_message: str,
    trace: dict[str, Any],
) -> None:
    payload = {
        "conversation_id": claim["conversation_id"],
        "generation_task_id": claim["task_id"],
        "backend_task_id": claim["backend_task_id"],
        "model_name": cfg.model_name,
        "error_message": error_message[:500],
    }
    status_code, data = post_json(
        f"{cfg.base_url}/callbacks/model-failure",
        payload,
        timeout_seconds=cfg.backend_request_timeout_seconds,
        internal_token=cfg.internal_token,
    )
    if status_code != 200 or data.get("code") != 0:
        log_event(
            "ERROR",
            "model-failure callback failed",
            trace,
            callback_status=status_code,
            callback_body=data,
        )
        return
    log_event("WARN", "model-failure callback success", trace, error_message=error_message)


def heartbeat_loop(
    cfg: WorkerConfig,
    task_id: int,
    stop_event: threading.Event,
    trace: dict[str, Any],
) -> None:
    while not stop_event.wait(cfg.heartbeat_interval_seconds):
        payload = {
            "worker_id": cfg.worker_id,
            "lease_seconds": cfg.lease_seconds,
        }
        status_code, data = post_json(
            f"{cfg.base_url}/backend/tasks/{task_id}/heartbeat",
            payload,
            timeout_seconds=cfg.backend_request_timeout_seconds,
            internal_token=cfg.internal_token,
        )
        if status_code != 200 or data.get("code") != 0:
            log_event(
                "ERROR",
                "heartbeat failed",
                trace,
                heartbeat_status=status_code,
                heartbeat_body=data,
            )
        else:
            log_event("INFO", "heartbeat ok", trace)


def claim_task(cfg: WorkerConfig) -> dict[str, Any] | None:
    payload = {
        "worker_id": cfg.worker_id,
        "model_name": cfg.model_name,
        "lease_seconds": cfg.lease_seconds,
    }
    status_code, data = post_json(
        f"{cfg.base_url}/backend/tasks/claim",
        payload,
        timeout_seconds=cfg.backend_request_timeout_seconds,
        internal_token=cfg.internal_token,
    )
    if status_code != 200 or data.get("code") != 0:
        raise RuntimeError(f"claim failed status={status_code}, body={data}")

    claimed = data.get("data")
    if not isinstance(claimed, dict):
        return None
    return claimed


def process_task(cfg: WorkerConfig, claim: dict[str, Any]) -> None:
    trace_base = {
        "task_id": claim.get("task_id"),
        "backend_task_id": claim.get("backend_task_id"),
    }
    log_event("INFO", "task claimed", trace_base, question_text=claim.get("question_text", ""))

    deadline = time.monotonic() + cfg.total_task_timeout_seconds

    stop_event = threading.Event()
    heartbeat_thread = threading.Thread(
        target=heartbeat_loop,
        args=(cfg, int(claim["task_id"]), stop_event, trace_base),
        daemon=True,
    )
    heartbeat_thread.start()

    request_id: str | None = None
    try:
        answer_text, request_id = call_vivo_completion_with_retry(cfg, claim, trace_base, deadline)
        answer_request_id = _build_answer_request_id(claim, request_id)
        callback_success(cfg, claim, request_id, answer_request_id, answer_text, {**trace_base, "requestId": request_id})
    except Exception as exc:
        failure_trace = dict(trace_base)
        if request_id:
            failure_trace["requestId"] = request_id
        elif isinstance(exc, UpstreamCallError):
            maybe_request_id = exc.detail.get("requestId")
            if isinstance(maybe_request_id, str) and maybe_request_id:
                failure_trace["requestId"] = maybe_request_id
        callback_failure(cfg, claim, _build_failure_message(exc), failure_trace)
    finally:
        stop_event.set()
        heartbeat_thread.join(timeout=1.0)


def run_worker(cfg: WorkerConfig) -> None:
    running = True

    def _stop_handler(signum: int, _frame: Any) -> None:
        nonlocal running
        running = False
        log_event("INFO", "stop signal received", None, signal=signum)

    signal.signal(signal.SIGINT, _stop_handler)
    signal.signal(signal.SIGTERM, _stop_handler)

    log_event(
        "INFO",
        "agent worker started",
        None,
        base_url=cfg.base_url,
        worker_id=cfg.worker_id,
        model_name=cfg.model_name,
        lease_seconds=cfg.lease_seconds,
        heartbeat_interval_seconds=cfg.heartbeat_interval_seconds,
        backend_request_timeout_seconds=cfg.backend_request_timeout_seconds,
        upstream_timeout_seconds=cfg.upstream_timeout_seconds,
        total_task_timeout_seconds=cfg.total_task_timeout_seconds,
        upstream_max_retries=cfg.upstream_max_retries,
    )
    if not cfg.vivo_app_key:
        log_event("WARN", "VIVO_APP_KEY is empty, worker will only produce failure callbacks")

    while running:
        try:
            claim = claim_task(cfg)
            if claim is None:
                time.sleep(cfg.poll_interval_seconds)
                continue
            process_task(cfg, claim)
        except Exception as exc:
            log_event("ERROR", "worker loop error", None, error=str(exc))
            time.sleep(cfg.poll_interval_seconds)

    log_event("INFO", "agent worker stopped")


def main() -> None:
    cfg = load_config()
    run_worker(cfg)


if __name__ == "__main__":
    main()