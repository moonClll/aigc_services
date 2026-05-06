下面是当前服务端全部自定义接口梳理（业务前缀：/api/v1）。

系统接口
文件：main.py

GET /healthz：健康检查。
认证接口（前端）
文件：auth.py

POST /api/v1/auth/register：注册账号。
POST /api/v1/auth/login：登录并获取 JWT。
会话接口（前端，需 Bearer Token）
文件：conversations.py

POST /api/v1/conversations：创建会话。
GET /api/v1/conversations：分页查询会话列表。
GET /api/v1/conversations/titles：按最近时间返回历史会话标题。
GET /api/v1/conversations/{conversation_id}/messages：分页查询会话消息。
GET /api/v1/conversations/{conversation_id}/messages/all：查询会话全部消息。
消息接口（前端，需 Bearer Token）
文件：messages.py

POST /api/v1/messages/question：提交问题并创建生成任务。
POST /api/v1/messages/{message_id}/feedback：提交回答反馈，可触发重答。
任务接口（前端，需 Bearer Token）
文件：tasks.py

GET /api/v1/tasks/{task_id}：查询任务详情。
GET /api/v1/tasks/{task_id}/result：查询任务结果（task + answer_ready + answer_message）。
GET /api/v1/tasks：分页查询任务（支持 conversation_id、status 过滤）。
学习路径接口（前端，需 Bearer Token）
文件：learning.py

GET /api/v1/learning-paths/conversations/{conversation_id}/current：获取当前学习路径。
GET /api/v1/learning-paths/{path_id}：获取学习路径详情。
PATCH /api/v1/learning-paths/{path_id}/nodes/{node_id}/state：更新节点状态。
POST /api/v1/learning-paths/{path_id}/checkins：学习打卡。
GET /api/v1/learning-paths/{path_id}/progress：查询学习进度汇总。
GET /api/v1/learning-paths/conversations/{conversation_id}/events：查询会话事件时间线。
后端任务分发接口（后端服务调用）
文件：backend.py

POST /api/v1/backend/tasks/claim：领取待处理任务。
POST /api/v1/backend/tasks/{task_id}/heartbeat：任务续租心跳。
后端回调接口（后端服务调用）
文件：callbacks.py

POST /api/v1/callbacks/model-answer：回调模型答案（支持多模态资产、重答覆盖、学习路径落库）。
POST /api/v1/callbacks/model-failure：回调模型失败信息。
鉴权说明
文件：deps.py，internal_auth.py

前端业务接口使用 Authorization: Bearer <token>。
后端接口支持 X-Internal-Token；当配置了 BACKEND_CALLBACK_TOKEN 时会强校验。
敏感配置说明：SECRET_KEY、DATABASE_URL、BACKEND_CALLBACK_TOKEN、LLM API Key 等只能来自 .env、local environment 或部署平台配置，不应写入前端代码或提交到仓库。

前端提交问题样例

POST /api/v1/messages/question

Headers:

Authorization: Bearer <login_access_token>
Content-Type: application/json

Request:

```json
{
  "conversation_id": 1,
  "content_text": "我想学习 Python 基础，请生成学习路径",
  "request_id": "front-req-20260506-0001"
}
```

Response:

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

前端轮询任务结果样例

GET /api/v1/tasks/42/result

Headers:

Authorization: Bearer <login_access_token>

Response (未完成):

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

Response (已完成):

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

前端注意：这里解析的是后端统一包装结构 `{code,message,data}`，不是 LLM 原始响应中的 `choices[0].message.content`。

AI claim 上下文扩展建议

POST /api/v1/backend/tasks/claim 的响应 data 可以在后续版本增加可选 `context_json`，用于“AI 无状态，后端提供上下文”的一阶段方案：

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

AI 端必须兼容 `context_json` 缺失。该字段不得包含 API Key、JWT、密码、数据库连接串等敏感信息。

AI 成功回调样例

POST /api/v1/callbacks/model-answer

Headers:

X-Internal-Token: <BACKEND_CALLBACK_TOKEN，如果后端启用>
Content-Type: application/json

Request:

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

AI 失败回调样例

POST /api/v1/callbacks/model-failure

```json
{
  "conversation_id": 1,
  "generation_task_id": 42,
  "backend_task_id": "job-abc",
  "model_name": "Volc-DeepSeek-V3.2",
  "error_message": "LLM request timeout"
}
```

当前版本服务端已具备这些核心功能：

账号体系
注册 + 登录(JWT)，并有账号/密码格式校验和错误提示。

会话管理
创建会话、会话列表、历史会话标题、按会话查询全部消息（支持历史访问）。

前端提问入库
前端问题通过 JSON 提交后，服务端保存消息并创建生成任务（pending）。

后端任务分发
后端可 claim 任务、heartbeat 续租；支持过期任务重领，避免任务卡死。

模型回调入库
支持后端回调成功答案或失败信息；答案可包含文本、图片、思维导图等多模态资产并入库。

反馈与重答闭环
用户可对回答评价并触发重答；服务端记录反馈、创建重答任务、回调后可覆盖旧答案并返回新答案。

任务查询与前端轮询
前端可查询任务状态，也可通过 tasks/{id}/result 一次拿到 任务状态 + answer_ready + 最终答案。

学习路径能力
当回调里带 meta_json.learning_path 时，服务端会自动保存学习路径版本、节点、初始节点状态。

学习进度与打卡
支持节点状态更新（locked/available/in_progress/done）、每日打卡、进度统计（完成率/打卡天数等）。

会话事件时间线
学习路径生成、节点状态变化、打卡都会写入事件日志，前端可按会话拉取时间线。

幂等与一致性
问题、反馈、打卡等关键写入支持 request_id 幂等，减少重复提交导致的脏数据。

基础保障
统一 JSON 响应结构、MySQL 持久化（utf8mb4）、健康检查、升级脚本和多份冒烟测试脚本。
