import json
from datetime import datetime, timezone
from pathlib import Path
import sys
from urllib import request
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BASE_URL = "http://127.0.0.1:8000/api/v1"
USERNAME = "demo"
PASSWORD = "Demo@123456"


def post_json(
    url: str,
    payload: dict,
    token: str | None = None,
    internal_token: str | None = None,
) -> tuple[int, dict]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if internal_token:
        headers["X-Internal-Token"] = internal_token
    req = request.Request(url, data=body, headers=headers, method="POST")

    try:
        with request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, {"raw_error": raw}


def get_json(url: str, token: str) -> tuple[int, dict]:
    headers = {"Authorization": f"Bearer {token}"}
    req = request.Request(url, headers=headers, method="GET")
    with request.urlopen(req, timeout=30) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def main() -> None:
    try:
        login_status, login_data = post_json(
            f"{BASE_URL}/auth/login",
            {"username": USERNAME, "password": PASSWORD},
        )
    except URLError as exc:
        print("Cannot connect to API server.")
        print("Please start server first: uvicorn app.main:app --reload")
        print("Current target:", BASE_URL)
        print("Original error:", exc)
        return

    if login_status != 200 or login_data.get("code") != 0:
        print("Login failed:", login_status, login_data)
        return
    token = login_data["data"]["access_token"]

    suffix = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")

    conv_status, conv_data = post_json(
        f"{BASE_URL}/conversations",
        {"title": "backend-claim-smoke"},
        token=token,
    )
    if conv_status != 200 or conv_data.get("code") != 0:
        print("Create conversation failed:", conv_status, conv_data)
        return
    conversation_id = conv_data["data"]["id"]
    print("1) conversation:", conversation_id)

    ask_status, ask_data = post_json(
        f"{BASE_URL}/messages/question",
        {
            "conversation_id": conversation_id,
            "content_text": "claim flow question",
            "request_id": f"claim-flow-q-{suffix}",
        },
        token=token,
    )
    if ask_status != 200 or ask_data.get("code") != 0:
        print("Question failed:", ask_status, ask_data)
        return
    print("2) question accepted, task id:", ask_data["data"]["generation_task_id"])

    claim_status, claim_data = post_json(
        f"{BASE_URL}/backend/tasks/claim",
        {
            "worker_id": "worker-a",
            "model_name": "demo-model",
            "conversation_id": conversation_id,
            "lease_seconds": 300,
        },
    )
    if claim_status != 200 or claim_data.get("code") != 0 or claim_data.get("data") is None:
        print("Claim failed:", claim_status, claim_data)
        return
    claimed = claim_data["data"]
    print(
        "3) claimed task:",
        claimed["task_id"],
        "backend_task_id:",
        claimed["backend_task_id"],
        "attempts:",
        claimed["dispatch_attempts"],
    )
    print("   question:", claimed["question_text"])

    heartbeat_status, heartbeat_data = post_json(
        f"{BASE_URL}/backend/tasks/{claimed['task_id']}/heartbeat",
        {"worker_id": "worker-a", "lease_seconds": 300},
    )
    print("4) heartbeat:", heartbeat_status, heartbeat_data.get("message"))

    answer_status, answer_data = post_json(
        f"{BASE_URL}/callbacks/model-answer",
        {
            "conversation_id": claimed["conversation_id"],
            "generation_task_id": claimed["task_id"],
            "backend_task_id": claimed["backend_task_id"],
            "model_name": "demo-model",
            "answer_text": "claim flow answer",
            "answer_request_id": f"claim-flow-a-{suffix}",
            "assets": [],
        },
    )
    if answer_status != 200 or answer_data.get("code") != 0:
        print("Answer callback failed:", answer_status, answer_data)
        return
    print("5) answer stored message id:", answer_data["data"]["id"])

    task_status, task_data = get_json(f"{BASE_URL}/tasks/{claimed['task_id']}", token=token)
    print("6) task status:", task_status, task_data["data"]["status"])

    no_task_status, no_task_data = post_json(
        f"{BASE_URL}/backend/tasks/claim",
        {"worker_id": "worker-a", "model_name": "demo-model", "conversation_id": conversation_id},
    )
    print("7) next claim:", no_task_status, no_task_data["message"])


if __name__ == "__main__":
    main()
