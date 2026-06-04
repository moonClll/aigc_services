import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib import request
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BASE_URL = os.getenv("AIGC_BASE_URL", "http://127.0.0.1:8000/api/v1").rstrip("/")
USERNAME = os.getenv("SMOKE_USERNAME", "demo")
PASSWORD = os.getenv("SMOKE_PASSWORD", "Demo@123456")
POLL_TIMEOUT_SECONDS = int(os.getenv("SMOKE_POLL_TIMEOUT_SECONDS", "30"))
POLL_INTERVAL_SECONDS = float(os.getenv("SMOKE_POLL_INTERVAL_SECONDS", "1"))


def request_json(
    method: str,
    path: str,
    payload: dict | None = None,
    token: str | None = None,
) -> tuple[int, dict]:
    data = None
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = request.Request(f"{BASE_URL}{path}", data=data, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, {"raw_error": raw}


def must_ok(step: str, status_code: int, body: dict) -> None:
    if status_code != 200 or body.get("code") != 0:
        raise RuntimeError(f"{step} failed: status={status_code}, body={body}")


def main() -> None:
    suffix = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")

    try:
        login_status, login_data = request_json(
            "POST",
            "/auth/login",
            {"username": USERNAME, "password": PASSWORD},
        )
    except URLError as exc:
        print("Cannot connect to API server.")
        print("Please start backend first: uvicorn app.main:app --reload")
        print("Current target:", BASE_URL)
        print("Original error:", exc)
        return
    must_ok("1) login", login_status, login_data)
    token = login_data["data"]["access_token"]
    print("1) login ok")

    conv_status, conv_data = request_json(
        "POST",
        "/conversations",
        {"title": "runner-mock-flow-smoke"},
        token=token,
    )
    must_ok("2) create conversation", conv_status, conv_data)
    conversation_id = conv_data["data"]["id"]
    print("2) conversation:", conversation_id)

    ask_status, ask_data = request_json(
        "POST",
        "/messages/question",
        {
            "conversation_id": conversation_id,
            "content_text": "Create a beginner learning path for Python basics.",
            "request_id": f"runner-mock-q-{suffix}",
        },
        token=token,
    )
    must_ok("3) submit question", ask_status, ask_data)
    task_id = ask_data["data"]["generation_task_id"]
    print("3) submitted task:", task_id)

    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    last_payload: dict | None = None
    while time.monotonic() < deadline:
        poll_status, poll_data = request_json("GET", f"/tasks/{task_id}/result", token=token)
        must_ok("4) poll task result", poll_status, poll_data)
        last_payload = poll_data["data"]
        task = last_payload["task"]
        if task["status"] == "failed":
            raise RuntimeError(f"Task failed: {task.get('error_message')}")
        if last_payload["answer_ready"]:
            answer = last_payload["answer_message"]
            meta_json = answer.get("meta_json") if answer else None
            if not isinstance(meta_json, dict) or "learning_path" not in meta_json:
                raise RuntimeError(f"Answer missing meta_json.learning_path: {answer}")
            print("4) answer_ready=true")
            print("5) answer message id:", answer["id"])
            print("6) learning path title:", meta_json["learning_path"].get("title"))
            return
        time.sleep(POLL_INTERVAL_SECONDS)

    raise TimeoutError(
        f"Timed out waiting for runner callback. Last payload: {last_payload}"
    )


if __name__ == "__main__":
    main()
