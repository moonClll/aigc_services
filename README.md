# 学习类应用服务端

这是一个基于 `FastAPI + MySQL` 的服务端项目，负责连接前端与 AI 端，完成用户、会话、消息、任务、学习路径和学习进度的存储与流转。

当前项目已经从“AI 端主动来领取任务”的单一拉模式，扩展为：

- 主模式：服务端创建任务后，主动把任务推送给 AI 端
- 兼容模式：AI 端仍然可以通过 `claim` 接口主动领取任务

这样做的好处是：

- 前端提交问题后，服务端可以立即触发 AI 处理，不必等 AI 端轮询
- AI 服务暂时不支持主动接收时，旧的领取模式也还能继续工作
- 推送失败时，任务不会直接丢失，仍可保留给后续补发或领取处理

## 1. 当前功能

- 用户注册、登录、JWT 鉴权
- 新用户自动分配 mock 名字与头像，登录时返回
- 会话创建、历史会话标题查询、消息查询
- 前端提问入库、反馈入库、重答任务创建
- 任务状态管理：`pending / running / success / failed`
- 服务端主动推送任务到 AI 端
- AI 端主动领取任务作为兜底方案
- AI 答案回调、失败回调、多模态资产存储
- 学习路径、节点状态、打卡记录、会话事件时间线

## 2. 环境要求

- Python `3.10+`
- MySQL `8.x`

建议先在 MySQL 中创建数据库：

```sql
CREATE DATABASE learning_app CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

## 3. 安装依赖

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 4. 环境变量配置

将 `.env.example` 复制为 `.env`，至少配置以下内容：

```env
SECRET_KEY=dev-secret-key-change-me
DATABASE_URL=mysql+pymysql://root:123456@127.0.0.1:3306/learning_app?charset=utf8mb4
BACKEND_CALLBACK_TOKEN=
BACKEND_TASK_LEASE_SECONDS=300
AI_SERVICE_PROCESS_URL=
AI_SERVICE_TOKEN=
AI_SERVICE_TIMEOUT_SECONDS=120
AI_SERVICE_MODEL_NAME=local-ai-service
```

字段说明：

- `DATABASE_URL`：MySQL 连接地址
- `BACKEND_CALLBACK_TOKEN`：后端内部接口校验令牌；如果配置了，访问 `/api/v1/backend/*` 和 `/api/v1/callbacks/*` 时必须带 `X-Internal-Token`
- `AI_SERVICE_PROCESS_URL`：AI 服务处理入口，例如 `http://127.0.0.1:8100/ai/process`
- `AI_SERVICE_TOKEN`：服务端主动推送到 AI 服务时携带的内部令牌
- `AI_SERVICE_TIMEOUT_SECONDS`：主动推送请求超时时间
- `AI_SERVICE_MODEL_NAME`：服务端记录用的模型/服务名称

说明：

- 如果 `AI_SERVICE_PROCESS_URL` 为空，服务端不会主动推送任务
- 这时仍然可以使用旧的 `claim` 模式由 AI 端来领取任务

## 5. 数据库初始化

首次初始化：

```bash
python scripts/init_db.py
```

升级到当前最新数据库结构：

```bash
python scripts/upgrade_phase2.py
```

初始化脚本会创建 demo 账号：

- 用户名：`demo`
- 密码：`Demo@123456`

如果 demo 用户缺少 mock 头像或名字，初始化时也会自动补齐。

## 6. 启动服务

```bash
uvicorn app.main:app --reload
```

启动后可访问：

- 健康检查：`GET http://127.0.0.1:8000/healthz`
- Swagger 文档：`http://127.0.0.1:8000/docs`

## 7. 当前任务流转方式

### 7.1 主动推送模式

当前主推荐流程如下：

1. 前端提交问题到 `POST /api/v1/messages/question`
2. 服务端保存问题，并创建 `generation_task`
3. 服务端异步触发主动分发器
4. 分发器把任务推送到 `AI_SERVICE_PROCESS_URL`
5. AI 服务处理后：
   - 如果同步返回成功结果，服务端直接落库答案
   - 如果只是返回已接收，服务端等待 AI 端后续调用回调接口
6. 前端通过 `GET /api/v1/tasks/{task_id}/result` 轮询结果

### 7.2 兼容领取模式

如果 AI 服务仍按旧方案工作，也可以继续使用：

- `POST /api/v1/backend/tasks/claim`
- `POST /api/v1/backend/tasks/{task_id}/heartbeat`

也就是说：

- 新模式适合“服务端主动把任务发给 AI 端”
- 旧模式适合“AI 端自己定时拉取任务”

两种模式兼容。

## 8. 项目文件组织架构

```text
D:\aigc
├─ app
│  ├─ main.py
│  ├─ api
│  │  ├─ router.py
│  │  ├─ deps.py
│  │  ├─ internal_auth.py
│  │  ├─ serializers.py
│  │  └─ routes
│  │     ├─ auth.py
│  │     ├─ conversations.py
│  │     ├─ messages.py
│  │     ├─ tasks.py
│  │     ├─ backend.py
│  │     ├─ callbacks.py
│  │     └─ learning.py
│  ├─ core
│  │  ├─ config.py
│  │  ├─ database.py
│  │  ├─ response.py
│  │  ├─ security.py
│  │  ├─ mock_user_profile.py
│  │  ├─ ai_dispatcher.py
│  │  └─ task_result_service.py
│  ├─ models
│  │  ├─ user.py
│  │  ├─ conversation.py
│  │  ├─ message.py
│  │  ├─ message_asset.py
│  │  ├─ generation_task.py
│  │  ├─ feedback.py
│  │  ├─ learning_path.py
│  │  ├─ learning_node.py
│  │  ├─ learning_node_state.py
│  │  ├─ learning_checkin.py
│  │  └─ conversation_event.py
│  └─ schemas
│     ├─ auth.py
│     ├─ conversation.py
│     ├─ message.py
│     ├─ task.py
│     └─ learning.py
├─ scripts
│  ├─ init_db.py
│  ├─ upgrade_phase2.py
│  ├─ phase1_smoke_test.py
│  ├─ phase2_smoke_test.py
│  ├─ phase3_smoke_test.py
│  ├─ frontend_flow_smoke_test.py
│  ├─ backend_claim_flow_smoke_test.py
│  ├─ feedback_regenerate_overwrite_smoke_test.py
│  ├─ task_result_polling_smoke_test.py
│  ├─ learning_path_flow_smoke_test.py
│  ├─ ai_bridge_local_smoke_test.py
│  ├─ ai_bridge_worker_once.py
│  ├─ ai_bridge_db_verify.py
│  ├─ perf_frontend_json_flow.py
│  └─ perf_backend_json_flow.py
├─ .env
├─ .env.example
├─ api.md
├─ requirements.txt
└─ README.md
```

最常用的入口文件：

- 服务启动入口：[main.py](/D:/aigc/app/main.py)
- 总路由入口：[router.py](/D:/aigc/app/api/router.py)
- 消息入口：[messages.py](/D:/aigc/app/api/routes/messages.py)
- 主动推送逻辑：[ai_dispatcher.py](/D:/aigc/app/core/ai_dispatcher.py)
- 回调入库逻辑：[task_result_service.py](/D:/aigc/app/core/task_result_service.py)

## 9. 核心接口说明

项目业务接口统一前缀为：`/api/v1`

### 9.1 认证接口

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`

说明：

- 新注册用户会自动获得 mock `display_name` 和 `avatar_url`
- 登录返回的 `user` 中会包含这两个字段

### 9.2 会话接口

- `POST /api/v1/conversations`
- `GET /api/v1/conversations`
- `GET /api/v1/conversations/titles`
- `GET /api/v1/conversations/{conversation_id}/messages`
- `GET /api/v1/conversations/{conversation_id}/messages/all`

### 9.3 消息接口

- `POST /api/v1/messages/question`
- `POST /api/v1/messages/{message_id}/feedback`

说明：

- 创建问题任务后，服务端会自动尝试主动推送到 AI 端
- 反馈重答任务也会自动尝试主动推送

### 9.4 任务接口

- `GET /api/v1/tasks/{task_id}`
- `GET /api/v1/tasks/{task_id}/result`
- `GET /api/v1/tasks?conversation_id=1&status=pending&page=1&page_size=20`

其中 `GET /api/v1/tasks/{task_id}/result` 会返回：

- `task`
- `answer_ready`
- `answer_message`

### 9.5 后端任务接口

- `POST /api/v1/backend/tasks/claim`
- `POST /api/v1/backend/tasks/{task_id}/heartbeat`
- `POST /api/v1/backend/tasks/{task_id}/dispatch`

说明：

- `claim`：旧的拉模式接口，AI 端可主动来领取任务
- `heartbeat`：领取后续租
- `dispatch`：手动触发服务端主动补发某个任务到 AI 端

### 9.6 AI 回调接口

- `POST /api/v1/callbacks/model-answer`
- `POST /api/v1/callbacks/model-failure`

说明：

- 支持文本答案、多模态资产、学习路径结构化入库
- 重答任务回调时可覆盖旧答案

### 9.7 学习路径接口

- `GET /api/v1/learning-paths/conversations/{conversation_id}/current`
- `GET /api/v1/learning-paths/{path_id}`
- `PATCH /api/v1/learning-paths/{path_id}/nodes/{node_id}/state`
- `POST /api/v1/learning-paths/{path_id}/checkins`
- `GET /api/v1/learning-paths/{path_id}/progress`
- `GET /api/v1/learning-paths/conversations/{conversation_id}/events`

## 10. 本次改进2026.6.11

服务端主动发送任务给 AI 端：

1. 新增主动分发器  
文件：[ai_dispatcher.py](/D:/aigc/app/core/ai_dispatcher.py)  
作用：任务创建后自动推送到 AI 服务。

2. 新增结果处理服务  
文件：[task_result_service.py](/D:/aigc/app/core/task_result_service.py)  
作用：统一处理答案入库与失败入库，供回调接口和主动推送共用。

3. 提问与重答自动触发推送  
文件：[messages.py](/D:/aigc/app/api/routes/messages.py)  
作用：前端提交问题、反馈重答后，服务端自动异步分发。

4. 增加手动补发接口  
文件：[backend.py](/D:/aigc/app/api/routes/backend.py)  
作用：当 AI 服务恢复后，可以手动重新推送某条任务。

5. 保留旧的领取模式  
文件：[backend.py](/D:/aigc/app/api/routes/backend.py)  
作用：确保旧 AI Worker 仍可继续工作，平滑迁移。

## 11. 联调脚本

使用以下脚本：

- `python scripts/frontend_flow_smoke_test.py`
- `python scripts/task_result_polling_smoke_test.py`
- `python scripts/learning_path_flow_smoke_test.py`
- `python scripts/ai_bridge_local_smoke_test.py`

说明：

- `ai_bridge_local_smoke_test.py` 现在用于验证“服务端主动推送 -> AI 服务 -> 回写结果”整条链路
- `ai_bridge_worker_once.py` 仍可作为旧拉模式桥接脚本保留

## 12. 常见问题

### 12.1 任务创建了，但 AI 没有立刻处理

检查：

- `.env` 中是否配置了 `AI_SERVICE_PROCESS_URL`
- AI 服务是否在对应地址启动
- 如果 AI 服务要求内部令牌，`AI_SERVICE_TOKEN` 是否正确

如果主动推送失败：

- 任务会保留在数据库中
- 继续让 AI 端使用 `claim` 模式领取
- 或手动调用 `POST /api/v1/backend/tasks/{task_id}/dispatch` 重新补发

### 12.2 创建数据库的代码


- [init_db.py](/D:/aigc/scripts/init_db.py)
- [upgrade_phase2.py](/D:/aigc/scripts/upgrade_phase2.py)


