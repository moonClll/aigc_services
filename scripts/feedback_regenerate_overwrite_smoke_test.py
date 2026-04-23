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

    if login_status != 200 or login_data.get("code") != 0:
        print("Login failed:", login_status, login_data)
        return
    token = login_data["data"]["access_token"]

    conv_status, conv_data = post_json(
        f"{BASE_URL}/conversations",
        {"title": "feedback-regenerate-overwrite"},
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
            "content_text": "Original question",
            "request_id": f"regen-q-{suffix}",
        },
        token=token,
    )
    if ask_status != 200 or ask_data.get("code") != 0:
        print("Question failed:", ask_status, ask_data)
        return

    claim1_status, claim1_data = post_json(
        f"{BASE_URL}/backend/tasks/claim",
        {"worker_id": "worker-a", "model_name": "demo-model", "conversation_id": conversation_id},
    )
    if claim1_status != 200 or claim1_data.get("code") != 0 or claim1_data.get("data") is None:
        print("Claim1 failed:", claim1_status, claim1_data)
        return
    claim1 = claim1_data["data"]
    print("2) first claim task:", claim1["task_id"])

    answer1_status, answer1_data = post_json(
        f"{BASE_URL}/callbacks/model-answer",
        {
            "conversation_id": conversation_id,
            "generation_task_id": claim1["task_id"],
            "backend_task_id": claim1["backend_task_id"],
            "model_name": "demo-model",
            "answer_text": "Old answer",
            "answer_request_id": f"regen-a1-{suffix}",
            "assets": [],
        },
    )
    if answer1_status != 200 or answer1_data.get("code") != 0:
        print("Answer1 failed:", answer1_status, answer1_data)
        return
    answer_message_id = answer1_data["data"]["id"]
    print("3) old answer message id:", answer_message_id)

    fb_status, fb_data = post_json(
        f"{BASE_URL}/messages/{answer_message_id}/feedback",
        {
            "rating": "dislike",
            "reason": "not accurate",
            "detail": "please regenerate with better explanation",
            "request_id": f"regen-fb-{suffix}",
            "regenerate": True,
        },
        token=token,
    )
    if fb_status != 200 or fb_data.get("code") != 0:
        print("Feedback failed:", fb_status, fb_data)
        return
    regen_task_id = fb_data["data"]["regenerate_task_id"]
    print("4) feedback accepted, regenerate task:", regen_task_id)

    claim2_status, claim2_data = post_json(
        f"{BASE_URL}/backend/tasks/claim",
        {"worker_id": "worker-a", "model_name": "demo-model", "conversation_id": conversation_id},
    )
    if claim2_status != 200 or claim2_data.get("code") != 0 or claim2_data.get("data") is None:
        print("Claim2 failed:", claim2_status, claim2_data)
        return
    claim2 = claim2_data["data"]
    print(
        "5) second claim task:",
        claim2["task_id"],
        "replace_answer_message_id:",
        claim2["replace_answer_message_id"],
        "feedback_rating:",
        claim2["feedback_rating"],
    )

    answer2_status, answer2_data = post_json(
        f"{BASE_URL}/callbacks/model-answer",
        {
            "conversation_id": conversation_id,
            "generation_task_id": claim2["task_id"],
            "backend_task_id": claim2["backend_task_id"],
            "model_name": "demo-model",
            "answer_text": "New overwritten answer",
            "answer_request_id": f"regen-a2-{suffix}",
            "assets": [],
        },
    )
    if answer2_status != 200 or answer2_data.get("code") != 0:
        print("Answer2 failed:", answer2_status, answer2_data)
        return
    print("6) overwrite callback message id:", answer2_data["data"]["id"])

    history_status, history_data = get_json(
        f"{BASE_URL}/conversations/{conversation_id}/messages/all",
        token=token,
    )
    if history_status != 200:
        print("History failed:", history_status, history_data)
        return
    print("7) messages total:", history_data["data"]["total"])
    for item in history_data["data"]["items"]:
        print("   -", item["id"], item["role"], item["message_type"], item["content_text"])


if __name__ == "__main__":
    main()

