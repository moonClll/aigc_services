# AI Agent 对接契约

本文档用于说明 FastAPI 后端与 AI Agent Worker 之间的对接约定。

## 架构说明

第一阶段采用“任务制拉取模型”：

```text
Android 前端 -> FastAPI 后端 -> AI Agent Worker -> LLM 平台
```

AI Agent Worker 是无状态模块。它不存储用户 session、对话记忆、API Key、JWT、密码或数据库凭据。会话存储、任务生命周期、学习路径落库，以及可选上下文组装，都由后端负责。

## 后端 -> AI：领取任务

接口：

```text
POST /api/v1/backend/tasks/claim
```

请求示例：

```json
{
  "worker_id": "worker-a",
  "model_name": "Volc-DeepSeek-V3.2",
  "conversation_id": 1,
  "lease_seconds": 300
}
```

有任务时的响应示例：

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

无任务时的响应示例：

```json
{
  "code": 0,
  "message": "No pending task",
  "data": null
}
```

说明：

- `context_json` 是可选字段，并且向后兼容。
- 后端暂时不传 `context_json` 时，AI Worker 也必须正常工作。
- `context_json` 只能放学习上下文、历史摘要、路径上下文等非敏感信息，不能放 API Key、JWT、密码、数据库连接串等敏感内容。

## AI -> 后端：任务心跳

接口：

```text
POST /api/v1/backend/tasks/{task_id}/heartbeat
```

请求示例：

```json
{
  "worker_id": "worker-a",
  "lease_seconds": 300
}
```

说明：

- `worker_id` 必须和领取任务时使用的 `worker_id` 保持一致。
- 如果后端配置了 `BACKEND_CALLBACK_TOKEN`，请求需要携带 `X-Internal-Token`。

## AI -> 后端：成功回调

接口：

```text
POST /api/v1/callbacks/model-answer
```

请求示例：

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

规则：

- `answer_text` 是模型返回的 JSON 字符串。
- `meta_json.learning_path` 用于后端解析并持久化学习路径。
- `answer_request_id` 应尽量保证每次成功回调唯一，用于幂等处理。
- 如果后端配置了 `BACKEND_CALLBACK_TOKEN`，请求需要携带 `X-Internal-Token`。

## AI -> 后端：失败回调

接口：

```text
POST /api/v1/callbacks/model-failure
```

请求示例：

```json
{
  "conversation_id": 1,
  "generation_task_id": 42,
  "backend_task_id": "job-abc",
  "model_name": "Volc-DeepSeek-V3.2",
  "error_message": "LLM request timeout"
}
```

建议错误分类：

| 上游失败类型 | `error_message` 示例 |
|---|---|
| 429 / 限流 | `LLM rate limited, retry exhausted` |
| 超时 | `LLM request timeout` |
| 5xx / 网络不可用 | `LLM upstream error` |
| 非法 JSON | `LLM returned invalid JSON` |

失败回调后，后端应将任务标记为 `failed`，不能让任务长期停留在 `running`。

## 给前端的对接提醒

前端不应该直接调用 LLM 平台。Android 前端只需要调用后端：

- `POST /api/v1/messages/question`
- `GET /api/v1/tasks/{task_id}/result`

Android 模拟器访问本机后端时，base URL 使用：

```text
http://10.0.2.2:8000/api/v1
```

前端应解析后端统一响应结构 `{code,message,data}`，不要解析 LLM 原始响应里的 `choices[0].message.content`。

## 安全规则

- 不要提交 `.env`。
- 不要硬编码 LLM API Key、JWT、数据库密码或 callback token。
- `VIVO_APP_KEY`、`SECRET_KEY`、`DATABASE_URL`、`BACKEND_CALLBACK_TOKEN` 必须来自本地环境变量、`.env` 或部署平台配置。
- 本地联调必须先使用 `AI_MODE=mock`，等后端 + AI runner 链路通过后，再切换真实模型模式。
