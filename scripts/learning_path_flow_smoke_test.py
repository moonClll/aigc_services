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


def request_json(
    method: str,
    url: str,
    payload: dict | None = None,
    token: str | None = None,
) -> tuple[int, dict]:
    data = None
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = request.Request(url, data=data, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, {"raw_error": raw}


def must_ok(step: str, status_code: int, body: dict) -> bool:
    if status_code != 200 or body.get("code") != 0:
        print(f"{step} failed:", status_code, body)
        return False
    return True


def main() -> None:
    suffix = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")

    try:
        login_status, login_data = request_json(
            "POST",
            f"{BASE_URL}/auth/login",
            {"username": USERNAME, "password": PASSWORD},
        )
    except URLError as exc:
        print("Cannot connect to API server.")
        print("Please start server first: uvicorn app.main:app --reload")
        print("Current target:", BASE_URL)
        print("Original error:", exc)
        return
    if not must_ok("1) login", login_status, login_data):
        return
    token = login_data["data"]["access_token"]

    conv_status, conv_data = request_json(
        "POST",
        f"{BASE_URL}/conversations",
        {"title": "learning-path-flow"},
        token=token,
    )
    if not must_ok("2) create conversation", conv_status, conv_data):
        return
    conversation_id = conv_data["data"]["id"]
    print("2) conversation:", conversation_id)

    ask_status, ask_data = request_json(
        "POST",
        f"{BASE_URL}/messages/question",
        {
            "conversation_id": conversation_id,
            "content_text": "Please create a 7-day learning path",
            "request_id": f"lp-q-{suffix}",
        },
        token=token,
    )
    if not must_ok("3) submit question", ask_status, ask_data):
        return
    task_id = ask_data["data"]["generation_task_id"]
    print("3) generation_task_id:", task_id)

    claim_status, claim_data = request_json(
        "POST",
        f"{BASE_URL}/backend/tasks/claim",
        {"worker_id": "worker-learning", "model_name": "demo-model", "conversation_id": conversation_id},
    )
    if not must_ok("4) claim task", claim_status, claim_data):
        return
    claim = claim_data["data"]

    answer_status, answer_data = request_json(
        "POST",
        f"{BASE_URL}/callbacks/model-answer",
        {
            "conversation_id": conversation_id,
            "generation_task_id": claim["task_id"],
            "backend_task_id": claim["backend_task_id"],
            "model_name": "demo-model",
            "answer_text": "This is your learning path summary.",
            "answer_request_id": f"lp-a-{suffix}",
            "assets": [
                {
                    "asset_type": "mindmap",
                    "asset_url": "https://example.com/path-mindmap.json",
                    "mime_type": "application/json",
                    "title": "7-day mindmap",
                    "sort_no": 1,
                    "meta_json": {"format": "xmind"},
                }
            ],
            "meta_json": {
                "content_type": "learning_path_v1",
                "learning_path": {
                    "title": "7-Day Newton Plan",
                    "goal": "Understand basic mechanics with examples.",
                    "summary_json": {"days": 7, "level": "beginner"},
                    "nodes": [
                        {
                            "node_code": "D1",
                            "title": "Day 1: Force and Motion",
                            "node_type": "lesson",
                            "description": "Read core concepts and examples.",
                            "est_minutes": 30,
                            "sort_no": 1,
                            "content_json": {"material": "text+image"},
                        },
                        {
                            "node_code": "D2",
                            "parent_node_code": "D1",
                            "title": "Day 2: Newton Second Law",
                            "node_type": "practice",
                            "description": "Solve 5 exercise questions.",
                            "est_minutes": 40,
                            "sort_no": 2,
                            "unlock_rule_json": {"after": ["D1"]},
                            "content_json": {"material": "quiz"},
                        },
                    ],
                },
            },
        },
    )
    if not must_ok("5) callback answer with learning_path", answer_status, answer_data):
        return
    print("5) answer message id:", answer_data["data"]["id"])

    path_status, path_data = request_json(
        "GET",
        f"{BASE_URL}/learning-paths/conversations/{conversation_id}/current",
        token=token,
    )
    if not must_ok("6) fetch current learning path", path_status, path_data):
        return
    path_id = path_data["data"]["path"]["id"]
    nodes = path_data["data"]["nodes"]
    first_node_id = nodes[0]["id"]
    print("6) path id:", path_id, "node count:", len(nodes))

    state_status, state_data = request_json(
        "PATCH",
        f"{BASE_URL}/learning-paths/{path_id}/nodes/{first_node_id}/state",
        {
            "state": "done",
            "request_id": f"lp-state-{suffix}",
        },
        token=token,
    )
    if not must_ok("7) update node state", state_status, state_data):
        return
    print("7) node state:", state_data["data"]["state"], "progress:", state_data["data"]["progress_percent"])

    checkin_status, checkin_data = request_json(
        "POST",
        f"{BASE_URL}/learning-paths/{path_id}/checkins",
        {
            "node_id": first_node_id,
            "spent_minutes": 35,
            "note": "Completed day 1 materials.",
            "request_id": f"lp-checkin-{suffix}",
        },
        token=token,
    )
    if not must_ok("8) create check-in", checkin_status, checkin_data):
        return
    print("8) check-in id:", checkin_data["data"]["id"])

    progress_status, progress_data = request_json(
        "GET",
        f"{BASE_URL}/learning-paths/{path_id}/progress",
        token=token,
    )
    if not must_ok("9) fetch progress", progress_status, progress_data):
        return
    print(
        "9) progress:",
        progress_data["data"]["done_nodes"],
        "/",
        progress_data["data"]["total_nodes"],
        "completion=",
        progress_data["data"]["completion_percent"],
    )

    events_status, events_data = request_json(
        "GET",
        f"{BASE_URL}/learning-paths/conversations/{conversation_id}/events?page=1&page_size=10",
        token=token,
    )
    if not must_ok("10) fetch conversation events", events_status, events_data):
        return
    print("10) events count:", events_data["data"]["total"])
    for item in events_data["data"]["items"][:3]:
        print("   -", item["event_type"], "entity:", item["entity_type"], item["entity_id"])


if __name__ == "__main__":
    main()

