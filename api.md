# 服务端接口说明

本文档整理当前服务端全部主要接口。

统一业务前缀：

```text
/api/v1
```

## 1. 系统接口

文件：[main.py](/D:/aigc/app/main.py)

- `GET /healthz`

## 2. 认证接口

文件：[auth.py](/D:/aigc/app/api/routes/auth.py)

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`

说明：

- 注册后会自动补充 mock `display_name` 和 `avatar_url`
- 登录返回中会包含 `user.display_name` 和 `user.avatar_url`

## 3. 会话接口

文件：[conversations.py](/D:/aigc/app/api/routes/conversations.py)

- `POST /api/v1/conversations`
- `GET /api/v1/conversations`
- `GET /api/v1/conversations/titles`
- `GET /api/v1/conversations/{conversation_id}/messages`
- `GET /api/v1/conversations/{conversation_id}/messages/all`

## 4. 消息接口

文件：[messages.py](/D:/aigc/app/api/routes/messages.py)

- `POST /api/v1/messages/question`
- `POST /api/v1/messages/{message_id}/feedback`

说明：

- 创建问题任务后会自动尝试主动推送到 AI 服务
- 反馈重答任务也会自动尝试主动推送

## 5. 任务接口

文件：[tasks.py](/D:/aigc/app/api/routes/tasks.py)

- `GET /api/v1/tasks/{task_id}`
- `GET /api/v1/tasks/{task_id}/result`
- `GET /api/v1/tasks`

## 6. 学习路径接口

文件：[learning.py](/D:/aigc/app/api/routes/learning.py)

- `GET /api/v1/learning-paths/conversations/{conversation_id}/current`
- `GET /api/v1/learning-paths/{path_id}`
- `PATCH /api/v1/learning-paths/{path_id}/nodes/{node_id}/state`
- `POST /api/v1/learning-paths/{path_id}/checkins`
- `GET /api/v1/learning-paths/{path_id}/progress`
- `GET /api/v1/learning-paths/conversations/{conversation_id}/events`

## 7. AI 任务分发接口

文件：[backend.py](/D:/aigc/app/api/routes/backend.py)

- `POST /api/v1/backend/tasks/claim`
- `POST /api/v1/backend/tasks/{task_id}/heartbeat`
- `POST /api/v1/backend/tasks/{task_id}/dispatch`

说明：

- `claim`：兼容旧的 AI 主动领取模式
- `dispatch`：服务端主动补发某条任务到 AI 服务

## 8. AI 回调接口

文件：[callbacks.py](/D:/aigc/app/api/routes/callbacks.py)

- `POST /api/v1/callbacks/model-answer`
- `POST /api/v1/callbacks/model-failure`

## 9. 当前推荐链路

推荐使用：

1. 前端调用 `POST /api/v1/messages/question`
2. 服务端创建任务后自动推送到 `AI_SERVICE_PROCESS_URL`
3. AI 服务处理后：
   - 同步返回结果，由服务端直接落库
   - 或异步调用 `/api/v1/callbacks/model-answer`
4. 前端通过 `GET /api/v1/tasks/{task_id}/result` 查询结果

兼容兜底链路：

1. 前端调用 `POST /api/v1/messages/question`
2. AI Worker 调用 `POST /api/v1/backend/tasks/claim`
3. AI Worker 调用回调接口返回结果

