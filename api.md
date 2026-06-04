# 服务端接口说明

本文档整理当前服务端的全部自定义接口。
业务接口统一前缀为：

```text
/api/v1
```

当前服务端主要面向三类调用方：

* 前端：负责注册、登录、创建会话、提交问题、查询任务结果、学习路径展示等。
* AI Worker / 后端生成服务：负责领取待处理任务、调用大模型、回调模型结果。
* 系统运维：负责健康检查、配置、数据库初始化与排查。

---

## 1. 系统接口

文件：`main.py`

### 1.1 健康检查

```http
GET /healthz
```

用于检查服务是否正常运行。

---

## 2. 认证接口（前端）

文件：`auth.py`

### 2.1 注册账号

```http
POST /api/v1/auth/register
```

用于前端注册新账号。

### 2.2 登录账号

```http
POST /api/v1/auth/login
```

用于登录并获取 JWT Token。

---

## 3. 会话接口（前端，需 Bearer Token）

文件：`conversations.py`

### 3.1 创建会话

```http
POST /api/v1/conversations
```

### 3.2 分页查询会话列表

```http
GET /api/v1/conversations
```

### 3.3 查询历史会话标题

```http
GET /api/v1/conversations/titles
```

按最近活跃时间返回历史会话标题。

### 3.4 分页查询会话消息

```http
GET /api/v1/conversations/{conversation_id}/messages
```

### 3.5 查询会话全部消息

```http
GET /api/v1/conversations/{conversation_id}/messages/all
```

---

## 4. 消息接口（前端，需 Bearer Token）

文件：`messages.py`

### 4.1 提交问题并创建生成任务

```http
POST /api/v1/messages/question
```

前端提交用户问题后，服务端会：

1. 保存用户问题消息；
2. 创建生成任务；
3. 返回问题消息信息和 `generation_task_id`。

### 4.2 提交回答反馈

```http
POST /api/v1/messages/{message_id}/feedback
```

用于对模型回答提交反馈，可选择触发重新生成。

如果请求中设置：

```json
{
  "regenerate": true
}
```

服务端会创建新的重答任务，并在响应中返回 `regenerate_task_id`。

---

## 5. 任务接口（前端，需 Bearer Token）

文件：`tasks.py`

### 5.1 查询任务详情

```http
GET /api/v1/tasks/{task_id}
```

### 5.2 查询任务结果

```http
GET /api/v1/tasks/{task_id}/result
```

该接口用于前端轮询任务结果，返回内容包括：

* `task`：任务状态；
* `answer_ready`：回答是否已经生成完成；
* `answer_message`：最终回答消息，任务成功后返回。

### 5.3 分页查询任务

```http
GET /api/v1/tasks
```

支持按照以下条件过滤：

* `conversation_id`
* `status`
* `page`
* `page_size`

示例：

```http
GET /api/v1/tasks?conversation_id=1&status=pending&page=1&page_size=20
```

---

## 6. 学习路径接口（前端，需 Bearer Token）

文件：`learning.py`

### 6.1 获取当前学习路径

```http
GET /api/v1/learning-paths/conversations/{conversation_id}/current
```

用于获取某个会话下当前生效的学习路径。

### 6.2 获取学习路径详情

```http
GET /api/v1/learning-paths/{path_id}
```

### 6.3 更新学习节点状态

```http
PATCH /api/v1/learning-paths/{path_id}/nodes/{node_id}/state
```

支持更新节点状态，例如：

* `locked`
* `available`
* `in_progress`
* `done`

### 6.4 学习打卡

```http
POST /api/v1/learning-paths/{path_id}/checkins
```

### 6.5 查询学习进度汇总

```http
GET /api/v1/learning-paths/{path_id}/progress
```

用于查询学习路径完成率、打卡天数等统计信息。

### 6.6 查询会话事件时间线

```http
GET /api/v1/learning-paths/conversations/{conversation_id}/events
```

用于拉取会话事件时间线，包括：

* 学习路径生成；
* 节点状态变化；
* 学习打卡记录。

---

## 7. 后端任务分发接口（AI Worker / 后端服务调用）

文件：`backend.py`

### 7.1 领取待处理任务

```http
POST /api/v1/backend/tasks/claim
```

用于 AI Worker 从服务端领取待处理任务。

支持能力：

* 领取 `pending` 状态任务；
* 重新领取租约过期的 `running` 状态任务；
* 支持任务租约机制，避免任务长期卡死；
* 支持反馈重答任务上下文返回。

### 7.2 任务续租心跳

```http
POST /api/v1/backend/tasks/{task_id}/heartbeat
```

当 AI Worker 仍在处理任务时，可调用该接口延长任务租约。

---

## 8. 后端回调接口（AI Worker / 后端服务调用）

文件：`callbacks.py`

### 8.1 回调模型答案

```http
POST /api/v1/callbacks/model-answer
```

用于 AI Worker 将模型成功生成的答案写回服务端。

支持能力：

* 文本答案入库；
* 多模态资产入库，例如图片、思维导图等；
* 反馈重答时覆盖旧答案；
* 当 `meta_json.learning_path` 存在时，自动保存学习路径、节点和初始节点状态。

### 8.2 回调模型失败信息

```http
POST /api/v1/callbacks/model-failure
```

用于 AI Worker 将模型调用失败信息写回服务端。

---

## 9. 鉴权说明

相关文件：

* `deps.py`
* `internal_auth.py`

### 9.1 前端业务接口鉴权

前端业务接口需要携带 JWT Token：

```http
Authorization: Bearer <token>
```

适用接口包括：

* 会话接口；
* 消息接口；
* 任务查询接口；
* 学习路径接口。

### 9.2 后端内部接口鉴权

后端任务接口和回调接口支持内部 Token：

```http
X-Internal-Token: <BACKEND_CALLBACK_TOKEN>
```

当服务端配置了 `BACKEND_CALLBACK_TOKEN` 时，会对该请求头进行强校验。

### 9.3 敏感配置说明

以下敏感配置只能来自 `.env`、本地环境变量或部署平台配置：

* `SECRET_KEY`
* `DATABASE_URL`
* `BACKEND_CALLBACK_TOKEN`
* LLM API Key
* 其他数据库、模型平台、第三方服务密钥

不要将这些敏感配置写入前端代码，也不要提交到 Git 仓库。

---

## 10. 前端提交问题样例

### 10.1 请求

```http
POST /api/v1/messages/question
```

Headers：

```http
Authorization: Bearer <login_access_token>
Content-Type: application/json
```

Request：

```json
{
  "conversation_id": 1,
  "content_text": "我想学习 Python 基础，请生成学习路径",
  "request_id": "front-req-20260506-0001"
}
```

### 10.2 响应

```json
{
  "code": 0,
  "message": "Question accepted",
  "data": {
    "id": 101,
    "conversation_id": 1,
    "role": "user",
    "message_type": "question",
    "content_text": "我想学习 Python 基础，请生成学习路径",
    "request_id": "front-req-20260506-0001",
    "parent_message_id": null,
    "meta_json": null,
    "created_at": "2026-05-06T12:00:00",
    "assets": [],
    "generation_task_id": 42
  }
}
```

---

## 11. 前端轮询任务结果样例

### 11.1 请求

```http
GET /api/v1/tasks/42/result
```

Headers：

```http
Authorization: Bearer <login_access_token>
```

### 11.2 响应：任务未完成

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "task": {
      "id": 42,
      "conversation_id": 1,
      "status": "running",
      "error_message": null
    },
    "answer_ready": false,
    "answer_message": null
  }
}
```

### 11.3 响应：任务已完成

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "task": {
      "id": 42,
      "conversation_id": 1,
      "status": "success",
      "error_message": null
    },
    "answer_ready": true,
    "answer_message": {
      "id": 102,
      "conversation_id": 1,
      "role": "assistant",
      "message_type": "answer",
      "content_text": "{\"learning_path\":{\"title\":\"Python 入门路径\",\"nodes\":[]}}",
      "meta_json": {
        "learning_path": {
          "title": "Python 入门路径",
          "goal": "掌握 Python 基础并能完成小练习",
          "nodes": []
        }
      },
      "assets": []
    }
  }
}
```

前端需要注意：
这里解析的是后端统一包装结构：

```json
{
  "code": 0,
  "message": "ok",
  "data": {}
}
```

不是 LLM 原始响应中的：

```text
choices[0].message.content
```

---

## 12. AI Claim 上下文扩展建议

### 12.1 接口

```http
POST /api/v1/backend/tasks/claim
```

后续版本可以在该接口的响应 `data` 中增加可选字段 `context_json`，用于实现“AI 无状态，后端提供上下文”的一阶段方案。

### 12.2 响应示例

```json
{
  "task_id": 42,
  "backend_task_id": "job-abc",
  "conversation_id": 1,
  "question_message_id": 101,
  "question_text": "我想学习 Python 基础",
  "question_meta_json": {
    "subject": "programming",
    "level": "beginner"
  },
  "context_json": {
    "history_summary": "用户已了解变量和函数的概念",
    "path_context": [
      {
        "node_id": 1,
        "title": "编程入门",
        "question": "如何开始学习编程"
      }
    ],
    "learner_profile": {
      "level": "beginner",
      "goal": "完成基础脚本"
    }
  },
  "frontend_request_id": "front-req-20260506-0001"
}
```

### 12.3 兼容性要求

AI 端必须兼容 `context_json` 缺失的情况。

也就是说，以下两种情况都应该可以正常处理：

* `context_json` 存在；
* `context_json` 不存在。

### 12.4 安全要求

`context_json` 不得包含任何敏感信息，例如：

* API Key；
* JWT；
* 用户密码；
* 数据库连接串；
* 内部服务密钥；
* 其他不应暴露给 AI Worker 的敏感配置。

---

## 13. AI 成功回调样例

### 13.1 请求

```http
POST /api/v1/callbacks/model-answer
```

Headers：

```http
X-Internal-Token: <BACKEND_CALLBACK_TOKEN，如果后端启用>
Content-Type: application/json
```

Request：

```json
{
  "conversation_id": 1,
  "generation_task_id": 42,
  "backend_task_id": "job-abc",
  "model_name": "Volc-DeepSeek-V3.2",
  "answer_text": "{\"learning_path\":{\"title\":\"Python 入门路径\",\"nodes\":[]}}",
  "answer_request_id": "answer-task-42-001",
  "assets": [],
  "meta_json": {
    "learning_path": {
      "title": "Python 入门路径",
      "goal": "掌握 Python 基础并能完成小练习",
      "nodes": []
    }
  }
}
```

---

## 14. AI 失败回调样例

### 14.1 请求

```http
POST /api/v1/callbacks/model-failure
```

Request：

```json
{
  "conversation_id": 1,
  "generation_task_id": 42,
  "backend_task_id": "job-abc",
  "model_name": "Volc-DeepSeek-V3.2",
  "error_message": "LLM request timeout"
}
```

---

## 15. 当前版本核心能力

### 15.1 账号体系

服务端已支持：

* 用户注册；
* 用户登录；
* JWT 鉴权；
* 账号格式校验；
* 密码强度校验；
* 登录错误提示。

### 15.2 会话管理

服务端已支持：

* 创建会话；
* 查询会话列表；
* 查询历史会话标题；
* 按会话分页查询消息；
* 按会话查询全部消息；
* 支持历史会话访问。

### 15.3 前端提问入库

前端通过 JSON 提交问题后，服务端会：

1. 保存用户问题；
2. 创建生成任务；
3. 将任务状态初始化为 `pending`；
4. 返回 `generation_task_id` 给前端。

### 15.4 后端任务分发

服务端已支持：

* AI Worker 领取任务；
* Worker 心跳续租；
* 过期任务重新领取；
* 防止任务长时间卡死；
* 支持反馈重答任务上下文返回。

### 15.5 模型回调入库

AI Worker 可回调：

* 成功答案；
* 失败信息。

成功答案支持：

* 文本；
* 图片；
* 思维导图；
* 其他多模态资产；
* `meta_json` 元数据；
* 学习路径自动落库。

### 15.6 反馈与重答闭环

服务端已支持：

* 用户对回答进行评价；
* 记录反馈原因和详细说明；
* 根据反馈触发重新生成任务；
* 重答完成后覆盖旧答案；
* 返回新的回答内容；
* 使用 `request_id` 保证反馈重试幂等。

### 15.7 任务查询与前端轮询

前端可通过任务接口：

* 查询任务状态；
* 分页查询任务列表；
* 通过 `/tasks/{id}/result` 一次性获取任务状态、回答是否就绪和最终回答。

### 15.8 学习路径能力

当 AI 回调中的 `meta_json` 包含 `learning_path` 时，服务端会自动保存：

* 学习路径版本；
* 学习路径节点；
* 初始节点状态；
* 学习路径与会话的关联关系。

### 15.9 学习进度与打卡

服务端已支持：

* 节点状态更新；
* 每日学习打卡；
* 学习完成率统计；
* 打卡天数统计；
* 学习路径进度汇总。

### 15.10 会话事件时间线

以下行为会写入事件日志：

* 学习路径生成；
* 节点状态变化；
* 学习打卡。

前端可以按会话拉取事件时间线，用于页面回放和学习轨迹展示。

### 15.11 幂等与一致性

关键写入接口支持 `request_id` 幂等，包括：

* 提交问题；
* 提交反馈；
* 学习打卡。

这样可以减少前端重复提交、网络重试导致的重复数据问题。

### 15.12 基础保障

当前服务端已具备以下基础保障：

* 统一 JSON 响应结构；
* MySQL 持久化；
* `utf8mb4` 字符集支持；
* 健康检查接口；
* 数据库初始化脚本；
* 数据库升级脚本；
* 多份冒烟测试脚本；
* 内部 Token 校验机制。
