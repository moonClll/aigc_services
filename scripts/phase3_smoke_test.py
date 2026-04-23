import json
from datetime import datetime, timezone
from pathlib import Path
import sys
from urllib import request
from urllib.error import URLError

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
) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if internal_token:
        headers["X-Internal-Token"] = internal_token
    req = request.Request(url, data=body, headers=headers, method="POST")
    with request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_json(url: str, token: str) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    req = request.Request(url, headers=headers, method="GET")
    with request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> None:
    try:
        login = post_json(
            f"{BASE_URL}/auth/login",
            {"username": USERNAME, "password": PASSWORD},
        )
    except URLError as exc:
        print("Cannot connect to API server.")
        print("Please start server first: uvicorn app.main:app --reload")
        print("Current target:", BASE_URL)
        print("Original error:", exc)
        return

    token = login["data"]["access_token"]
    suffix = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")

    conv = post_json(
        f"{BASE_URL}/conversations",
        {"title": "phase3 smoke"},
        token=token,
    )
    conversation_id = conv["data"]["id"]
    print("1) conversation:", conversation_id)

    ask = post_json(
        f"{BASE_URL}/messages/question",
        {
            "conversation_id": conversation_id,
            "content_text": "phase3 question",
            "request_id": f"phase3-question-{suffix}",
        },
        token=token,
    )
    question_id = ask["data"]["id"]
    task_id = ask["data"]["generation_task_id"]
    print("2) question task:", task_id)

    fail = post_json(
        f"{BASE_URL}/callbacks/model-failure",
        {
            "conversation_id": conversation_id,
            "generation_task_id": task_id,
            "backend_task_id": f"phase3-back-job-fail-{suffix}",
            "model_name": "demo-model",
            "error_message": "upstream timeout",
        },
    )
    print("3) failure callback status:", fail["data"]["status"])

    ask2 = post_json(
        f"{BASE_URL}/messages/question",
        {
            "conversation_id": conversation_id,
            "content_text": "phase3 second question",
            "request_id": f"phase3-question2-{suffix}",
        },
        token=token,
    )
    question2_id = ask2["data"]["id"]
    task2_id = ask2["data"]["generation_task_id"]

    answer = post_json(
        f"{BASE_URL}/callbacks/model-answer",
        {
            "conversation_id": conversation_id,
            "generation_task_id": task2_id,
            "backend_task_id": f"phase3-back-job-ok-{suffix}",
            "model_name": "demo-model",
            "answer_text": "phase3 answer text",
            "answer_request_id": f"phase3-answer-{suffix}",
            "assets": [],
        },
    )
    answer_id = answer["data"]["id"]
    print("4) answer message:", answer_id, "parent:", answer["data"]["parent_message_id"])

    feedback = post_json(
        f"{BASE_URL}/messages/{answer_id}/feedback",
        {
            "rating": "dislike",
            "reason": "not clear",
            "detail": "need simpler explanation",
            "request_id": f"phase3-feedback-{suffix}",
            "regenerate": True,
        },
        token=token,
    )
    print("5) feedback id:", feedback["data"]["id"], "regen_task:", feedback["data"]["regenerate_task_id"])

    task_detail = get_json(f"{BASE_URL}/tasks/{task2_id}", token=token)
    print("6) task detail status:", task_detail["data"]["status"])

    task_list = get_json(
        f"{BASE_URL}/tasks?conversation_id={conversation_id}&page=1&page_size=10",
        token=token,
    )
    print("7) tasks in conversation:", task_list["data"]["total"])
    for item in task_list["data"]["items"]:
        print("   -", item["id"], item["status"], item["question_message_id"])


if __name__ == "__main__":
    main()

