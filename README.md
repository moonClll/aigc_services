# Learning App Service（Phase 1 ~ Phase 5）

当前后端已包含以下功能：

* Phase 1：登录、创建会话、问题存储、历史记录查询
* Phase 2：生成任务跟踪、模型回答回调、多模态资源存储
* Phase 3：任务查询 API、模型失败回调、用户反馈与可选重新生成
* Phase 4：后端任务领取 API，即后端从服务端拉取待处理任务
* Phase 5：学习路径存储、节点进度更新、学习打卡、会话事件时间线

## 1. 环境要求

* Python 3.10+
* MySQL 8.x

创建数据库：

```sql
CREATE DATABASE learning_app CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

## 2. 安装依赖

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 3. 配置环境变量

将 `.env.example` 复制为 `.env`：

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

`BACKEND_CALLBACK_TOKEN` 为可选配置。如果设置了该值，则 `/api/v1/callbacks/*` 接口必须在请求头中携带 `X-Internal-Token`。

`VIVO_APP_KEY` 仅在 `AI_MODE=real` 时需要配置。请不要提交 `.env` 文件，也不要在代码中硬编码密钥。

## 4. 初始化数据库结构

首次初始化：

```bash
python scripts/init_db.py
```

升级到最新阶段所需的数据库结构：

```bash
python scripts/upgrade_phase2.py
```

演示账号：

* 用户名：`demo`
* 密码：`Demo@123456`

## 5. 启动服务

```bash
uvicorn app.main:app --reload
```

* 健康检查：`GET http://127.0.0.1:8000/healthz`
* 接口文档：`http://127.0.0.1:8000/docs`

## 5.1 启动 AI Agent Worker

AI Agent Worker 会消费后端任务，并通过回调接口将结果写回服务端。

Mock 模式是本地联调的默认模式，不会调用真实大模型平台：

```bash
AI_MODE=mock python scripts/runner.py
```

Real 模式会调用 vivo 大模型平台，并需要从环境变量或 `.env` 中读取 `VIVO_APP_KEY`：

```bash
export VIVO_APP_KEY="your-vivo-key"
AI_MODE=real python scripts/runner.py
```

Worker 的处理流程如下：

```text
POST /api/v1/backend/tasks/claim
-> 构造 prompt
-> 调用 mock 或真实 LLM
-> POST /api/v1/callbacks/model-answer
```

如果处理失败，Worker 会调用：

```text
POST /api/v1/callbacks/model-failure
```

后端与 AI 之间的接口契约请参考 `AI_CONTRACT.md`，其中也包含可选字段 `context_json` 的说明。

## 6. 核心 API

### 6.1 登录

`POST /api/v1/auth/login`

如果账号不存在或密码错误，后端返回：

```json
{
  "detail": "\\u8d26\\u6237\\u6216\\u5bc6\\u7801\\u9519\\u8bef"
}
```

### 6.2 注册（前端）

`POST /api/v1/auth/register`

```json
{
  "username": "Alice_001",
  "password": "StrongPass@123",
  "display_name": "Alice"
}
```

规则：

* `username`：长度为 4-20 个字符，必须以字母开头，只允许包含字母、数字和下划线
* `password`：长度为 8-32 个字符，必须同时包含大写字母、小写字母、数字和特殊字符

如果不符合规则，后端会在 `detail.rules` 中返回格式或规则提示。

### 6.3 创建会话

`POST /api/v1/conversations`

### 6.4 提交问题

`POST /api/v1/messages/question`

```json
{
  "conversation_id": 1,
  "content_text": "Please explain Newton's second law",
  "request_id": "req-20260422-0001"
}
```

响应中的 `data` 包含问题消息字段，以及 `generation_task_id`。

### 6.5 查询历史会话标题（前端）

`GET /api/v1/conversations/titles`

返回按最近活跃时间排序的会话标题列表。

### 6.6 查询会话消息（前端）

分页查询：

`GET /api/v1/conversations/{conversation_id}/messages?page=1&page_size=20`

一次性查询全部消息：

`GET /api/v1/conversations/{conversation_id}/messages/all`

### 6.7 模型回答回调（Phase 2）

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

### 6.8 模型失败回调（Phase 3）

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

### 6.9 提交反馈（Phase 3）

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

如果 `regenerate=true`，响应中会包含 `regenerate_task_id`。

重新生成任务会携带反馈元数据，并且可以在回调时覆盖旧回答。

如果前端使用相同的 `request_id` 重试同一条反馈，后端会保持幂等性，并返回相同的 `regenerate_task_id`。

### 6.10 查询任务（Phase 3）

* `GET /api/v1/tasks/{task_id}`
* `GET /api/v1/tasks?conversation_id=1&status=pending&page=1&page_size=20`

任务详情现在包含：

* `answer_message_id`：该任务对应的最终回答消息 ID

每条消息的响应体中都包含 `assets`。

### 6.11 后端领取任务（Phase 4）

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

如果存在可领取任务，后端会收到问题内容和任务 ID。

如果当前没有可领取任务，响应中的 `data` 为 `null`，并且 `message` 为 `No pending task`。

当任务来自反馈后的重新生成时，领取任务的响应中还会包含：

* `replace_answer_message_id`
* `feedback_id`
* `feedback_rating`
* `feedback_reason`
* `feedback_detail`

后端可以使用这些字段，结合反馈上下文重新生成回答。

任务领取 API 支持过期租约的重新领取：

* `pending` 状态的任务可以正常领取
* `running` 状态且 `lease_expires_at` 已过期的任务可以被重新领取

### 6.12 后端心跳（Phase 4）

`POST /api/v1/backend/tasks/{task_id}/heartbeat`

```json
{
  "worker_id": "worker-a",
  "lease_seconds": 300
}
```

该接口用于在后端仍在生成时延长任务租约。

### 6.13 前端轮询任务结果（Phase 4+）

`GET /api/v1/tasks/{task_id}/result`

响应包含：

* `task`：完整任务状态
* `answer_ready`：回答是否已经可用
* `answer_message`：任务成功时的最终回答内容，包含 `assets`

该接口设计用于前端在提交问题或重新生成后轮询任务结果。

### 6.14 学习路径 API（Phase 5）

当 `POST /api/v1/callbacks/model-answer` 的 `meta_json` 中包含 `learning_path` 时，后端会存储带版本号的学习路径和路径节点。

前端 API：

* `GET /api/v1/learning-paths/conversations/{conversation_id}/current`
* `GET /api/v1/learning-paths/{path_id}`
* `PATCH /api/v1/learning-paths/{path_id}/nodes/{node_id}/state`
* `POST /api/v1/learning-paths/{path_id}/checkins`
* `GET /api/v1/learning-paths/{path_id}/progress`
* `GET /api/v1/learning-paths/conversations/{conversation_id}/events`

每次节点状态更新或学习打卡都会写入一条会话事件记录，用于时间线回放。

## 7. 冒烟测试

Phase 1 冒烟测试：

```bash
python scripts/phase1_smoke_test.py
```

Phase 2 冒烟测试：

```bash
python scripts/phase2_smoke_test.py
```

Phase 3 冒烟测试：

```bash
python scripts/phase3_smoke_test.py
```

前端流程冒烟测试，包括注册、登录、历史记录和消息查询：

```bash
python scripts/frontend_flow_smoke_test.py
```

后端任务领取流程冒烟测试：

```bash
python scripts/backend_claim_flow_smoke_test.py
```

反馈重新生成并覆盖旧回答的冒烟测试：

```bash
python scripts/feedback_regenerate_overwrite_smoke_test.py
```

任务结果轮询冒烟测试：

```bash
python scripts/task_result_polling_smoke_test.py
```

学习路径流程冒烟测试：

```bash
python scripts/learning_path_flow_smoke_test.py
```

AI runner mock 流程冒烟测试：

1. 启动后端：

```bash
uvicorn app.main:app --reload
```

2. 在另一个终端启动 Worker：

```bash
AI_MODE=mock AI_POLL_INTERVAL=1 python scripts/runner.py
```

3. 在第三个终端验证端到端流程：

```bash
python scripts/runner_mock_flow_smoke_test.py
```

预期输出中应包含 `answer_ready=true` 和 `learning path title`。

## 8. JSON 性能测试（前端 / 后端）

前端 JSON 写入路径性能测试：

```bash
python scripts/perf_frontend_json_flow.py --requests 500 --concurrency 50 --conversation-shards 50
```

后端 JSON 回调写入路径性能测试：

```bash
python scripts/perf_backend_json_flow.py --requests 500 --concurrency 50 --conversation-shards 50
```

如果启用了回调 token，请传入：

```bash
python scripts/perf_backend_json_flow.py --internal-token your_token_here
```

两个脚本都会打印吞吐量（RPS）、平均延迟、P95 延迟、成功 / 失败数量，并展示测试中使用的 JSON 请求模板。

## 9. 中文乱码排查

如果中文显示为 `????`，请执行：

```sql
source scripts/fix_mysql_utf8mb4.sql;
```

如果问题只出现在 PowerShell 手动请求中，可以在 JSON 中使用 Unicode 转义，例如 `\u8bf7...`，或者直接运行冒烟测试脚本。
