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
QUESTION_TEXT = "\u8bf7\u5206\u4e09\u70b9\u89e3\u91ca\u725b\u987f\u7b2c\u4e8c\u5b9a\u5f8b"
ANSWER_TEXT = "\u725b\u987f\u7b2c\u4e8c\u5b9a\u5f8b\u53ef\u4ee5\u7528\u516c\u5f0f F=ma \u8868\u793a\u3002"


def post_json(url: str, payload: dict, token: str | None = None, internal_token: str | None = None) -> dict:
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
    print("1) login:", login["message"])

    suffix = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    question_request_id = f"phase2-question-{suffix}"
    answer_request_id = f"phase2-answer-{suffix}"
    backend_task_id = f"backend-job-{suffix}"

    conv = post_json(f"{BASE_URL}/conversations", {"title": "phase2 smoke"}, token=token)
    conv_id = conv["data"]["id"]
    print("2) conversation:", conv_id)

    ask = post_json(
        f"{BASE_URL}/messages/question",
        {
            "conversation_id": conv_id,
            "content_text": QUESTION_TEXT,
            "request_id": question_request_id,
        },
        token=token,
    )
    question_id = ask["data"]["id"]
    task_id = ask["data"]["generation_task_id"]
    print("3) question accepted, message_id=", question_id, "task_id=", task_id)

    callback = post_json(
        f"{BASE_URL}/callbacks/model-answer",
        {
            "conversation_id": conv_id,
            "generation_task_id": task_id,
            "backend_task_id": backend_task_id,
            "model_name": "demo-model",
            "answer_text": ANSWER_TEXT,
            "answer_request_id": answer_request_id,
            "assets": [
                {
                    "asset_type": "image",
                    "asset_url": "https://example.com/figure.png",
                    "mime_type": "image/png",
                    "title": "sample image",
                    "sort_no": 1,
                    "meta_json": {"width": 1280, "height": 720},
                },
                {
                    "asset_type": "mindmap",
                    "asset_url": "https://example.com/mindmap.json",
                    "mime_type": "application/json",
                    "title": "sample mindmap",
                    "sort_no": 2,
                    "meta_json": {"format": "xmind"},
                },
            ],
        },
    )
    answer_id = callback["data"]["id"]
    print("4) callback stored, answer_id=", answer_id)
    print("   returned assets:", len(callback["data"]["assets"]))

    history = get_json(
        f"{BASE_URL}/conversations/{conv_id}/messages?page=1&page_size=50",
        token=token,
    )
    print("5) history total:", history["data"]["total"])
    for item in history["data"]["items"]:
        print(
            "   -",
            "id=", item["id"],
            "role=", item["role"],
            "type=", item["message_type"],
            "assets=", len(item.get("assets", [])),
        )


if __name__ == "__main__":
    main()
