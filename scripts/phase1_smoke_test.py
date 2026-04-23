import json
from datetime import datetime, timezone
from pathlib import Path
import sys
from urllib import request
from urllib.error import URLError

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import engine

BASE_URL = "http://127.0.0.1:8000/api/v1"
USERNAME = "demo"
PASSWORD = "Demo@123456"
QUESTION_TEXT = "\u8bf7\u7528\u4e00\u4e2a\u751f\u6d3b\u4f8b\u5b50\u89e3\u91ca\u725b\u987f\u7b2c\u4e8c\u5b9a\u5f8b"


def post_json(url: str, payload: dict, token: str | None = None) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = request.Request(url, data=body, headers=headers, method="POST")
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

    request_id = "phase1-smoke-zh-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")

    conv = post_json(
        f"{BASE_URL}/conversations",
        {"title": "phase1 smoke"},
        token=token,
    )
    conv_id = conv["data"]["id"]
    print("2) create conversation:", conv["message"], "id=", conv_id)

    ask = post_json(
        f"{BASE_URL}/messages/question",
        {
            "conversation_id": conv_id,
            "content_text": QUESTION_TEXT,
            "request_id": request_id,
        },
        token=token,
    )
    print("3) submit question:", ask["message"])
    print("   API content_text:", ask["data"]["content_text"])

    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT content_text, HEX(content_text), CHAR_LENGTH(content_text), LENGTH(content_text) "
                "FROM messages WHERE request_id=:rid"
            ),
            {"rid": request_id},
        ).fetchone()

    if row is None:
        print("4) DB check: not found")
        return

    print("4) DB content_text:", row[0])
    print("   HEX(content_text):", row[1])
    print("   CHAR_LENGTH:", row[2], "LENGTH:", row[3])


if __name__ == "__main__":
    main()
