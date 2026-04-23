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


def post_json(url: str, payload: dict, token: str | None = None) -> tuple[int, dict]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
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
    if not must_ok("1) login", login_status, login_data):
        return
    token = login_data["data"]["access_token"]

    conv_status, conv_data = post_json(
        f"{BASE_URL}/conversations",
        {"title": "task-result-polling-smoke"},
        token=token,
    )
    if not must_ok("2) create conversation", conv_status, conv_data):
        return
    conversation_id = conv_data["data"]["id"]
    print("2) conversation id:", conversation_id)

    ask_status, ask_data = post_json(
        f"{BASE_URL}/messages/question",
        {
            "conversation_id": conversation_id,
            "content_text": "Please explain with one practical example.",
            "request_id": f"task-result-q-{suffix}",
        },
        token=token,
    )
    if not must_ok("3) submit question", ask_status, ask_data):
        return
    first_task_id = ask_data["data"]["generation_task_id"]
    print("3) first task id:", first_task_id)

    claim1_status, claim1_data = post_json(
        f"{BASE_URL}/backend/tasks/claim",
        {"worker_id": "worker-poll", "model_name": "demo-model", "conversation_id": conversation_id},
    )
    if not must_ok("4) claim first task", claim1_status, claim1_data):
        return
    claim1 = claim1_data["data"]

    poll1_status, poll1_data = get_json(f"{BASE_URL}/tasks/{first_task_id}/result", token=token)
    if not must_ok("5) poll first task before callback", poll1_status, poll1_data):
        return
    print(
        "5) before callback:",
        poll1_data["data"]["task"]["status"],
        "answer_ready=",
        poll1_data["data"]["answer_ready"],
    )

    answer1_status, answer1_data = post_json(
        f"{BASE_URL}/callbacks/model-answer",
        {
            "conversation_id": conversation_id,
            "generation_task_id": claim1["task_id"],
            "backend_task_id": claim1["backend_task_id"],
            "model_name": "demo-model",
            "answer_text": "Old answer from first generation.",
            "answer_request_id": f"task-result-a1-{suffix}",
            "assets": [],
        },
    )
    if not must_ok("6) callback first answer", answer1_status, answer1_data):
        return
    old_answer_id = answer1_data["data"]["id"]
    print("6) old answer message id:", old_answer_id)

    poll2_status, poll2_data = get_json(f"{BASE_URL}/tasks/{first_task_id}/result", token=token)
    if not must_ok("7) poll first task after callback", poll2_status, poll2_data):
        return
    print(
        "7) after callback:",
        poll2_data["data"]["task"]["status"],
        "answer_ready=",
        poll2_data["data"]["answer_ready"],
        "answer_message_id=",
        poll2_data["data"]["answer_message"]["id"] if poll2_data["data"]["answer_message"] else None,
    )

    feedback_status, feedback_data = post_json(
        f"{BASE_URL}/messages/{old_answer_id}/feedback",
        {
            "rating": "dislike",
            "reason": "not detailed",
            "detail": "please regenerate and improve practical details",
            "request_id": f"task-result-fb-{suffix}",
            "regenerate": True,
        },
        token=token,
    )
    if not must_ok("8) submit feedback regenerate", feedback_status, feedback_data):
        return
    regen_task_id = feedback_data["data"]["regenerate_task_id"]
    print("8) regenerate task id:", regen_task_id)

    claim2_status, claim2_data = post_json(
        f"{BASE_URL}/backend/tasks/claim",
        {"worker_id": "worker-poll", "model_name": "demo-model", "conversation_id": conversation_id},
    )
    if not must_ok("9) claim regenerate task", claim2_status, claim2_data):
        return
    claim2 = claim2_data["data"]
    print("9) claim replace answer id:", claim2["replace_answer_message_id"])

    poll3_status, poll3_data = get_json(f"{BASE_URL}/tasks/{regen_task_id}/result", token=token)
    if not must_ok("10) poll regenerate task before callback", poll3_status, poll3_data):
        return
    print(
        "10) before regenerate callback:",
        poll3_data["data"]["task"]["status"],
        "answer_ready=",
        poll3_data["data"]["answer_ready"],
    )

    answer2_status, answer2_data = post_json(
        f"{BASE_URL}/callbacks/model-answer",
        {
            "conversation_id": conversation_id,
            "generation_task_id": claim2["task_id"],
            "backend_task_id": claim2["backend_task_id"],
            "model_name": "demo-model",
            "answer_text": "New overwritten answer after feedback.",
            "answer_request_id": f"task-result-a2-{suffix}",
            "assets": [],
        },
    )
    if not must_ok("11) callback regenerate answer", answer2_status, answer2_data):
        return

    poll4_status, poll4_data = get_json(f"{BASE_URL}/tasks/{regen_task_id}/result", token=token)
    if not must_ok("12) poll regenerate task after callback", poll4_status, poll4_data):
        return

    answer_message = poll4_data["data"]["answer_message"]
    print(
        "12) regenerate done:",
        poll4_data["data"]["task"]["status"],
        "answer_message_id=",
        answer_message["id"] if answer_message else None,
    )
    print("13) final answer text:", answer_message["content_text"] if answer_message else None)


if __name__ == "__main__":
    main()

