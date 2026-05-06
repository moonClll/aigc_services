# AI Agent Contract

This document is the handoff contract between the FastAPI backend and the AI Agent Worker.

## Architecture

Stage 1 uses a task-based pull model:

```text
Android Frontend -> FastAPI Backend -> AI Agent Worker -> LLM Platform
```

The AI Agent Worker is stateless. It does not store user sessions, conversation memory, API keys, JWTs, passwords, or database credentials. The backend owns conversation storage, task lifecycle, learning path storage, and optional context assembly.

## Backend -> AI: Claim Task

Endpoint:

```text
POST /api/v1/backend/tasks/claim
```

Request:

```json
{
  "worker_id": "worker-a",
  "model_name": "Volc-DeepSeek-V3.2",
  "conversation_id": 1,
  "lease_seconds": 300
}
```

Task available response:

```json
{
  "code": 0,
  "message": "Task claimed",
  "data": {
    "task_id": 42,
    "backend_task_id": "job-abc",
    "conversation_id": 1,
    "question_message_id": 101,
    "question_text": "How do I learn Python?",
    "question_meta_json": {
      "subject": "programming",
      "level": "beginner"
    },
    "context_json": {
      "history_summary": "The learner has completed variables and functions.",
      "path_context": [
        {
          "node_id": 1,
          "title": "Python Basics",
          "question": "How should I start learning Python?"
        }
      ],
      "learner_profile": {
        "level": "beginner",
        "goal": "Build small scripts"
      }
    },
    "frontend_request_id": "front-req-20260506-0001",
    "worker_id": "worker-a",
    "model_name": "Volc-DeepSeek-V3.2",
    "claimed_at": "2026-05-06T12:00:00",
    "lease_expires_at": "2026-05-06T12:05:00",
    "dispatch_attempts": 1
  }
}
```

No task response:

```json
{
  "code": 0,
  "message": "No pending task",
  "data": null
}
```

`context_json` is optional and backward compatible. The AI worker must work when it is missing. Do not put secrets in `context_json`.

## AI -> Backend: Heartbeat

Endpoint:

```text
POST /api/v1/backend/tasks/{task_id}/heartbeat
```

Request:

```json
{
  "worker_id": "worker-a",
  "lease_seconds": 300
}
```

Use the same `worker_id` as the claim request. If `BACKEND_CALLBACK_TOKEN` is configured, include `X-Internal-Token`.

## AI -> Backend: Success Callback

Endpoint:

```text
POST /api/v1/callbacks/model-answer
```

Request:

```json
{
  "conversation_id": 1,
  "generation_task_id": 42,
  "backend_task_id": "job-abc",
  "model_name": "Volc-DeepSeek-V3.2",
  "answer_text": "{\"learning_path\":{\"title\":\"Python Learning Path\",\"nodes\":[]}}",
  "answer_request_id": "answer-task-42-001",
  "assets": [],
  "meta_json": {
    "learning_path": {
      "title": "Python Learning Path",
      "goal": "Learn Python fundamentals and complete beginner exercises.",
      "nodes": [
        {
          "node_code": "step_01",
          "title": "Python Basics",
          "node_type": "lesson",
          "description": "Learn variables, data types, and basic syntax.",
          "est_minutes": 30,
          "sort_no": 1,
          "parent_node_code": null
        }
      ]
    }
  }
}
```

Rules:

- `answer_text` is the JSON string returned by the model.
- `meta_json.learning_path` is required for learning path persistence.
- `answer_request_id` should be unique per successful callback for idempotency.
- If `BACKEND_CALLBACK_TOKEN` is configured, include `X-Internal-Token`.

## AI -> Backend: Failure Callback

Endpoint:

```text
POST /api/v1/callbacks/model-failure
```

Request:

```json
{
  "conversation_id": 1,
  "generation_task_id": 42,
  "backend_task_id": "job-abc",
  "model_name": "Volc-DeepSeek-V3.2",
  "error_message": "LLM request timeout"
}
```

Expected classifications:

| Upstream failure | Error message example |
|---|---|
| 429 / rate limit | `LLM rate limited, retry exhausted` |
| Timeout | `LLM request timeout` |
| 5xx / network unavailable | `LLM upstream error` |
| Invalid JSON | `LLM returned invalid JSON` |

Failure callback must mark the backend task as `failed`, not leave it in `running`.

## Frontend Handoff Notes

Frontend should not call the LLM platform directly. Android should call the backend only:

- `POST /api/v1/messages/question`
- `GET /api/v1/tasks/{task_id}/result`

For Android emulator local backend access, use:

```text
http://10.0.2.2:8000/api/v1
```

Frontend should parse the backend envelope `{code,message,data}`. It should not parse LLM `choices[0].message.content`.

## Security Rules

- Never commit `.env`.
- Never hardcode LLM API keys, JWTs, database passwords, or callback tokens.
- `VIVO_APP_KEY`, `SECRET_KEY`, `DATABASE_URL`, and `BACKEND_CALLBACK_TOKEN` must come from local environment, `.env`, or deployment configuration.
- Use `AI_MODE=mock` until the local backend + AI runner chain passes.
