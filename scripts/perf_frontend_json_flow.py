import argparse
import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from urllib import request
from urllib.error import HTTPError, URLError


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


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    index = int((len(sorted_values) - 1) * p)
    return sorted_values[index]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Frontend JSON flow performance test (question write path)."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument("--username", default="demo")
    parser.add_argument("--password", default="Demo@123456")
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--conversation-shards", type=int, default=20)
    parser.add_argument("--question-text", default="Please explain Newton second law in three points.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    login_status, login_data = post_json(
        f"{args.base_url}/auth/login",
        {"username": args.username, "password": args.password},
    )
    if login_status != 200 or login_data.get("code") != 0:
        print("Login failed:", login_status, login_data)
        return

    token = login_data["data"]["access_token"]

    shard_count = max(1, min(args.conversation_shards, args.requests))
    conversation_ids: list[int] = []
    for shard in range(1, shard_count + 1):
        conv_status, conv_data = post_json(
            f"{args.base_url}/conversations",
            {"title": f"perf-frontend-json-shard-{shard}"},
            token=token,
        )
        if conv_status != 200 or conv_data.get("code") != 0:
            print("Create conversation failed:", conv_status, conv_data)
            return
        conversation_ids.append(conv_data["data"]["id"])

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")

    frontend_payload_template = {
        "conversation_id": "<selected shard conversation id>",
        "content_text": args.question_text,
        "request_id": "perf-front-<run_id>-<seq>",
    }
    print("Frontend payload template:")
    print(json.dumps(frontend_payload_template, ensure_ascii=False, indent=2))

    latencies: list[float] = []
    success = 0
    failed = 0
    failures: list[tuple[int, dict]] = []

    def worker(seq: int) -> tuple[bool, float, int, dict]:
        conversation_id = conversation_ids[(seq - 1) % len(conversation_ids)]
        payload = {
            "conversation_id": conversation_id,
            "content_text": f"{args.question_text} [{seq}]",
            "request_id": f"perf-front-{run_id}-{seq}",
        }
        t0 = time.perf_counter()
        status_code, data = post_json(
            f"{args.base_url}/messages/question",
            payload,
            token=token,
        )
        latency_ms = (time.perf_counter() - t0) * 1000
        ok = status_code == 200 and data.get("code") == 0
        return ok, latency_ms, status_code, data

    start = time.perf_counter()
    try:
        with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
            futures = [executor.submit(worker, i) for i in range(1, args.requests + 1)]
            for future in as_completed(futures):
                ok, latency_ms, status_code, data = future.result()
                latencies.append(latency_ms)
                if ok:
                    success += 1
                else:
                    failed += 1
                    if len(failures) < 5:
                        failures.append((status_code, data))
    except URLError as exc:
        print("Connection error:", exc)
        return

    total_seconds = time.perf_counter() - start
    throughput = success / total_seconds if total_seconds > 0 else 0.0
    avg_latency = statistics.mean(latencies) if latencies else 0.0
    p95_latency = percentile(latencies, 0.95)

    print("\n=== Frontend JSON Perf Summary ===")
    print("total_requests:", args.requests)
    print("concurrency:", args.concurrency)
    print("conversation_shards:", len(conversation_ids))
    print("success:", success)
    print("failed:", failed)
    print("duration_sec:", round(total_seconds, 3))
    print("throughput_rps:", round(throughput, 2))
    print("avg_latency_ms:", round(avg_latency, 2))
    print("p95_latency_ms:", round(p95_latency, 2))

    if failures:
        print("\nSample failures (up to 5):")
        for idx, (status_code, data) in enumerate(failures, start=1):
            print(f"{idx}) status={status_code}, body={json.dumps(data, ensure_ascii=False)}")


if __name__ == "__main__":
    main()
