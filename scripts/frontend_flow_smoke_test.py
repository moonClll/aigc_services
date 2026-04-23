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
    with request.urlopen(req, timeout=30) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def main() -> None:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    username = f"User_{run_id[-8:]}"
    password = "StrongPass@123"

    try:
        register_status, register_data = post_json(
            f"{BASE_URL}/auth/register",
            {
                "username": username,
                "password": password,
                "display_name": "Frontend Smoke",
            },
        )
    except URLError as exc:
        print("Cannot connect to API server.")
        print("Please start server first: uvicorn app.main:app --reload")
        print("Current target:", BASE_URL)
        print("Original error:", exc)
        return

    print("1) register:", register_status, register_data.get("message"))

    wrong_login_status, wrong_login_data = post_json(
        f"{BASE_URL}/auth/login",
        {"username": username, "password": "WrongPass@123"},
    )
    print("2) wrong login status:", wrong_login_status)
    print("   wrong login detail:", wrong_login_data.get("detail"))

    login_status, login_data = post_json(
        f"{BASE_URL}/auth/login",
        {"username": username, "password": password},
    )
    print("3) login:", login_status, login_data.get("message"))
    token = login_data["data"]["access_token"]

    conv1_status, conv1_data = post_json(
        f"{BASE_URL}/conversations",
        {"title": "History A"},
        token=token,
    )
    conv2_status, conv2_data = post_json(
        f"{BASE_URL}/conversations",
        {"title": "History B"},
        token=token,
    )
    print("4) create conversations:", conv1_status, conv2_status)

    conv1_id = conv1_data["data"]["id"]
    conv2_id = conv2_data["data"]["id"]

    q1_status, q1_data = post_json(
        f"{BASE_URL}/messages/question",
        {
            "conversation_id": conv1_id,
            "content_text": "Question in A",
            "request_id": f"front-flow-q1-{run_id}",
        },
        token=token,
    )
    q2_status, q2_data = post_json(
        f"{BASE_URL}/messages/question",
        {
            "conversation_id": conv2_id,
            "content_text": "Question in B",
            "request_id": f"front-flow-q2-{run_id}",
        },
        token=token,
    )
    print("5) submit questions:", q1_status, q2_status)

    # Add one answer to conversation A so messages/all returns multi-turn data.
    post_json(
        f"{BASE_URL}/callbacks/model-answer",
        {
            "conversation_id": conv1_id,
            "generation_task_id": q1_data["data"]["generation_task_id"],
            "backend_task_id": f"front-flow-back-{run_id}",
            "model_name": "demo-model",
            "answer_text": "Answer for A",
            "answer_request_id": f"front-flow-a1-{run_id}",
            "assets": [],
        },
    )

    titles_status, titles_data = get_json(f"{BASE_URL}/conversations/titles", token=token)
    print("6) titles:", titles_status, "count=", titles_data["data"]["total"])
    print("   first two titles:", [item["title"] for item in titles_data["data"]["items"][:2]])

    all_status, all_data = get_json(
        f"{BASE_URL}/conversations/{conv1_id}/messages/all",
        token=token,
    )
    print("7) messages/all:", all_status, "total=", all_data["data"]["total"])
    for item in all_data["data"]["items"]:
        print("   -", item["id"], item["role"], item["message_type"], item["content_text"])


if __name__ == "__main__":
    main()

