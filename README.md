# Learning App Service (Phase 1 ~ Phase 5)

This backend now includes:

- Phase 1: login, conversation creation, question storage, history query
- Phase 2: generation task tracking, model answer callback, multi-modal assets
- Phase 3: task query APIs, model failure callback, user feedback with optional regenerate
- Phase 4: backend task claim API (backend pulls pending tasks from service)
- Phase 5: learning path storage, node progress updates, check-ins, conversation event timeline

## 1. Prerequisites

- Python 3.10+
- MySQL 8.x

Create database:

```sql
CREATE DATABASE learning_app CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

## 2. Install dependencies

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 3. Configure environment

Copy `.env.example` to `.env`:

```env
SECRET_KEY=dev-secret-key-change-me
DATABASE_URL=mysql+pymysql://root:123456@127.0.0.1:3306/learning_app?charset=utf8mb4
BACKEND_CALLBACK_TOKEN=
AI_MODE=mock
VIVO_APP_KEY=
VIVO_API_URL=https://api-ai.vivo.com.cn/v1/chat/completions
AI_MODEL=Volc-DeepSeek-V3.2
AI_TIMEOUT=60
AI_MAX_RETRIES=3
AI_WORKER_ID=worker-a
AI_POLL_INTERVAL=5
```

`BACKEND_CALLBACK_TOKEN` is optional. If set, `/api/v1/callbacks/*` must include header `X-Internal-Token`.
`VIVO_APP_KEY` is required only when `AI_MODE=real`. Do not commit `.env` or hardcode keys.

## 4. Initialize schema

First-time setup:

```bash
python scripts/init_db.py
```

Upgrade schema for latest phase:

```bash
python scripts/upgrade_phase2.py
```

Demo account:

- Username: `demo`
- Password: `Demo@123456`

## 5. Start server

```bash
uvicorn app.main:app --reload
```

- Health: `GET http://127.0.0.1:8000/healthz`
- Docs: `http://127.0.0.1:8000/docs`

## 5.1 Start AI Agent Worker

The AI Agent Worker consumes backend tasks and writes results back through callbacks.

Mock mode is the default for local integration and does not call the LLM platform:

```bash
AI_MODE=mock python scripts/runner.py
```

Real mode calls the vivo LLM platform and requires `VIVO_APP_KEY` from the environment or `.env`:

```bash
export VIVO_APP_KEY="your-vivo-key"
AI_MODE=real python scripts/runner.py
```

The worker flow is:

```text
POST /api/v1/backend/tasks/claim
-> build prompt
-> mock or real LLM call
-> POST /api/v1/callbacks/model-answer
```

If processing fails, the worker calls:

```text
POST /api/v1/callbacks/model-failure
```

See `AI_CONTRACT.md` for the backend/AI contract, including optional `context_json`.

## 6. Core API

### 6.1 Login

`POST /api/v1/auth/login`

If account does not exist or password is incorrect, backend returns:

```json
{
  "detail": "\\u8d26\\u6237\\u6216\\u5bc6\\u7801\\u9519\\u8bef"
}
```

### 6.2 Register (Frontend)

`POST /api/v1/auth/register`

```json
{
  "username": "Alice_001",
  "password": "StrongPass@123",
  "display_name": "Alice"
}
```

Rules:

- `username`: 4-20 chars, starts with a letter, only letters/numbers/underscore
- `password`: 8-32 chars, must include uppercase + lowercase + digit + special char

If rules fail, backend returns format/rule hints in `detail.rules`.

### 6.3 Create conversation

`POST /api/v1/conversations`

### 6.4 Submit question

`POST /api/v1/messages/question`

```json
{
  "conversation_id": 1,
  "content_text": "Please explain Newton's second law",
  "request_id": "req-20260422-0001"
}
```

Response `data` includes question message fields plus `generation_task_id`.

### 6.5 List history conversation titles (Frontend)

`GET /api/v1/conversations/titles`

Returns conversation titles ordered by latest activity time.

### 6.6 Query conversation messages (Frontend)

Paginated:

`GET /api/v1/conversations/{conversation_id}/messages?page=1&page_size=20`

All messages in one call:

`GET /api/v1/conversations/{conversation_id}/messages/all`

### 6.7 Model answer callback (Phase 2)

`POST /api/v1/callbacks/model-answer`

```json
{
  "conversation_id": 1,
  "generation_task_id": 123,
  "backend_task_id": "job-abc",
  "model_name": "gpt-4o-mini",
  "answer_text": "F = ma ...",
  "answer_request_id": "answer-req-001",
  "assets": [
    {
      "asset_type": "image",
      "asset_url": "https://example.com/figure.png",
      "mime_type": "image/png",
      "title": "figure",
      "sort_no": 1,
      "meta_json": {"width": 1280, "height": 720}
    },
    {
      "asset_type": "mindmap",
      "asset_url": "https://example.com/mindmap.json",
      "mime_type": "application/json",
      "title": "mindmap",
      "sort_no": 2,
      "meta_json": {"format": "xmind"}
    }
  ],
  "meta_json": {"latency_ms": 1200}
}
```

### 6.8 Model failure callback (Phase 3)

`POST /api/v1/callbacks/model-failure`

```json
{
  "conversation_id": 1,
  "generation_task_id": 123,
  "backend_task_id": "job-abc",
  "model_name": "gpt-4o-mini",
  "error_message": "upstream timeout"
}
```

### 6.9 Submit feedback (Phase 3)

`POST /api/v1/messages/{message_id}/feedback`

```json
{
  "rating": "dislike",
  "reason": "not clear",
  "detail": "need simpler explanation",
  "request_id": "feedback-req-001",
  "regenerate": true
}
```

If `regenerate=true`, response includes `regenerate_task_id`.
The regenerate task carries feedback metadata and can overwrite the old answer on callback.
If frontend retries the same feedback `request_id`, backend keeps idempotency and returns the same `regenerate_task_id`.

### 6.10 Query tasks (Phase 3)

- `GET /api/v1/tasks/{task_id}`
- `GET /api/v1/tasks?conversation_id=1&status=pending&page=1&page_size=20`

Task details now include:

- `answer_message_id`: direct mapping to the final answer message for this task

Each message payload includes `assets`.

### 6.11 Backend claim task (Phase 4)

`POST /api/v1/backend/tasks/claim`

```json
{
  "worker_id": "worker-a",
  "model_name": "gpt-4o-mini",
  "backend_task_id": "job-custom-001",
  "conversation_id": 1,
  "lease_seconds": 300
}
```

If a task is available, backend receives question payload and task IDs.  
If no task is available, response `data` is `null` and message is `No pending task`.

When task comes from feedback regenerate, claim response also includes:

- `replace_answer_message_id`
- `feedback_id`
- `feedback_rating`
- `feedback_reason`
- `feedback_detail`

Backend can use these fields to regenerate answer with feedback context.

The claim API supports stale lease re-claiming:

- pending tasks can be claimed normally
- running tasks with expired `lease_expires_at` can be re-claimed

### 6.12 Backend heartbeat (Phase 4)

`POST /api/v1/backend/tasks/{task_id}/heartbeat`

```json
{
  "worker_id": "worker-a",
  "lease_seconds": 300
}
```

This extends task lease while backend is still generating.

### 6.13 Frontend task result polling (Phase 4+)

`GET /api/v1/tasks/{task_id}/result`

Response includes:

- `task`: full task status
- `answer_ready`: whether answer is available
- `answer_message`: final answer payload (includes assets) when task succeeds

This endpoint is designed for frontend polling after submit/regenerate.

### 6.14 Learning path APIs (Phase 5)

When `POST /api/v1/callbacks/model-answer` includes `meta_json.learning_path`, backend stores a versioned learning path and nodes.

Frontend APIs:

- `GET /api/v1/learning-paths/conversations/{conversation_id}/current`
- `GET /api/v1/learning-paths/{path_id}`
- `PATCH /api/v1/learning-paths/{path_id}/nodes/{node_id}/state`
- `POST /api/v1/learning-paths/{path_id}/checkins`
- `GET /api/v1/learning-paths/{path_id}/progress`
- `GET /api/v1/learning-paths/conversations/{conversation_id}/events`

Each node state/check-in update writes a conversation event record for timeline replay.

## 7. Smoke tests

Phase 1 smoke test:

```bash
python scripts/phase1_smoke_test.py
```

Phase 2 smoke test:

```bash
python scripts/phase2_smoke_test.py
```

Phase 3 smoke test:

```bash
python scripts/phase3_smoke_test.py
```

Frontend flow smoke test (register/login/history/messages):

```bash
python scripts/frontend_flow_smoke_test.py
```

Backend claim flow smoke test:

```bash
python scripts/backend_claim_flow_smoke_test.py
```

Feedback regenerate overwrite smoke test:

```bash
python scripts/feedback_regenerate_overwrite_smoke_test.py
```

Task result polling smoke test:

```bash
python scripts/task_result_polling_smoke_test.py
```

Learning path flow smoke test:

```bash
python scripts/learning_path_flow_smoke_test.py
```

AI runner mock flow smoke test:

1. Start backend:

```bash
uvicorn app.main:app --reload
```

2. In another terminal, start worker:

```bash
AI_MODE=mock AI_POLL_INTERVAL=1 python scripts/runner.py
```

3. In a third terminal, verify the end-to-end flow:

```bash
python scripts/runner_mock_flow_smoke_test.py
```

Expected output includes `answer_ready=true` and `learning path title`.

## 8. JSON performance tests (frontend/backend)

Frontend JSON write-path perf test:

```bash
python scripts/perf_frontend_json_flow.py --requests 500 --concurrency 50 --conversation-shards 50
```

Backend JSON callback write-path perf test:

```bash
python scripts/perf_backend_json_flow.py --requests 500 --concurrency 50 --conversation-shards 50
```

If callback token is enabled, pass:

```bash
python scripts/perf_backend_json_flow.py --internal-token your_token_here
```

Both scripts print throughput (RPS), average latency, P95 latency, success/failure count, and show JSON payload templates used in the test.

## 9. Troubleshooting Chinese text

If Chinese text appears as `????`, run:

```sql
source scripts/fix_mysql_utf8mb4.sql;
```

If issue appears only in PowerShell manual requests, use Unicode escapes (`\u8bf7...`) in JSON or run the smoke test scripts.
