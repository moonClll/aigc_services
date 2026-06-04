# 学习类应用服务端

这是一个基于 `FastAPI + MySQL` 的服务端项目，主要负责连接前端与后端大模型服务，完成以下工作：

- 用户注册、登录与身份校验
- 会话创建、历史会话查询、消息存储
- 前端提问入库，并生成后端待处理任务
- 后端领取任务、回调答案、回调失败信息
- 用户对回答进行反馈，并触发重新生成
- 学习路径、节点进度、打卡记录、事件时间线存储
- 多模态内容存储，如文本、图片、思维导图等

当前项目已经实现到“学习路径与打卡”这一阶段，适合作为学习类 AI 应用的服务端原型和开发基础。

## 1. 当前功能概览

- 第一阶段：注册、登录、会话创建、问题入库、历史会话查询
- 第二阶段：生成任务跟踪、模型答案回调、多模态资产存储
- 第三阶段：任务查询、失败回调、回答反馈、可选重答
- 第四阶段：后端主动领取任务、任务续租、过期任务重领
- 第五阶段：学习路径落库、节点状态更新、打卡记录、会话事件时间线
- 用户扩展：新注册用户自动分配 mock 名字与头像，登录时一并返回

## 2. 环境要求

- Python `3.10+`
- MySQL `8.x`

建议先在 MySQL 中创建数据库：

```sql
CREATE DATABASE learning_app CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

## 3. 安装与配置

安装依赖：

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

配置环境变量，将 `.env.example` 复制为 `.env`，至少包含：

```env
SECRET_KEY=dev-secret-key-change-me
DATABASE_URL=mysql+pymysql://root:123456@127.0.0.1:3306/learning_app?charset=utf8mb4
BACKEND_CALLBACK_TOKEN=
```

说明：

- `DATABASE_URL`：MySQL 连接地址
- `BACKEND_CALLBACK_TOKEN`：后端内部接口校验令牌，可为空；如果设置了，访问 `/api/v1/backend/*` 和 `/api/v1/callbacks/*` 时需要传 `X-Internal-Token`

## 4. 数据库初始化

首次初始化：

```bash
python scripts/init_db.py
```

升级到当前最新数据库结构：

```bash
python scripts/upgrade_phase2.py
```

初始化脚本会创建一个演示账号：

- 用户名：`demo`
- 密码：`Demo@123456`

如果该账号缺少 mock 名字或头像，初始化脚本也会自动补齐。

## 5. 启动服务

```bash
uvicorn app.main:app --reload
```

启动后可访问：

- 健康检查：`GET http://127.0.0.1:8000/healthz`
- Swagger 文档：`http://127.0.0.1:8000/docs`

## 6. 项目文件组织架构

下面是当前项目中最重要的文件结构：

```text
D:\aigc
├─ app
│  ├─ main.py                       # FastAPI 入口
│  ├─ api
│  │  ├─ router.py                 # 总路由注册
│  │  ├─ deps.py                   # 前端鉴权依赖
│  │  ├─ internal_auth.py          # 后端内部接口鉴权
│  │  ├─ serializers.py            # 消息序列化
│  │  └─ routes
│  │     ├─ auth.py                # 注册、登录
│  │     ├─ conversations.py       # 会话与历史消息
│  │     ├─ messages.py            # 提问、反馈
│  │     ├─ tasks.py               # 任务查询、任务结果轮询
│  │     ├─ backend.py             # 后端领取任务、任务续租
│  │     ├─ callbacks.py           # 模型答案/失败回调
│  │     └─ learning.py            # 学习路径、打卡、进度、事件
│  ├─ core
│  │  ├─ config.py                 # 配置读取
│  │  ├─ database.py               # 数据库连接
│  │  ├─ response.py               # 统一响应格式
│  │  ├─ security.py               # JWT、密码哈希
│  │  └─ mock_user_profile.py      # mock 用户名字与头像分配
│  ├─ models
│  │  ├─ user.py                   # 用户表
│  │  ├─ conversation.py           # 会话表
│  │  ├─ message.py                # 消息表
│  │  ├─ message_asset.py          # 消息多模态资产表
│  │  ├─ generation_task.py        # 生成任务表
│  │  ├─ feedback.py               # 回答反馈表
│  │  ├─ learning_path.py          # 学习路径表
│  │  ├─ learning_node.py          # 学习节点表
│  │  ├─ learning_node_state.py    # 学习节点状态表
│  │  ├─ learning_checkin.py       # 打卡记录表
│  │  └─ conversation_event.py     # 会话事件时间线表
│  └─ schemas
│     ├─ auth.py                   # 认证请求/响应模型
│     ├─ conversation.py           # 会话请求/响应模型
│     ├─ message.py                # 消息与回调模型
│     ├─ task.py                   # 任务与反馈模型
│     └─ learning.py               # 学习路径与打卡模型
├─ scripts
│  ├─ init_db.py                   # 初始化数据库与 demo 用户
│  ├─ upgrade_phase2.py            # 数据库升级脚本
│  ├─ phase1_smoke_test.py         # 第一阶段冒烟测试
│  ├─ phase2_smoke_test.py         # 第二阶段冒烟测试
│  ├─ phase3_smoke_test.py         # 第三阶段冒烟测试
│  ├─ frontend_flow_smoke_test.py  # 前端流程测试
│  ├─ backend_claim_flow_smoke_test.py
│  ├─ feedback_regenerate_overwrite_smoke_test.py
│  ├─ task_result_polling_smoke_test.py
│  ├─ learning_path_flow_smoke_test.py
│  ├─ perf_frontend_json_flow.py   # 前端写入压测
│  ├─ perf_backend_json_flow.py    # 后端回调压测
│  ├─ agent_worker.py              # 简单任务 worker
│  ├─ llm_client.py                # LLM 调用封装
│  ├─ runner.py                    # 运行入口脚本
│  └─ runner_mock_flow_smoke_test.py
├─ .env                            # 本地环境配置
├─ .env.example                    # 环境变量示例
├─ AI_CONTRACT.md                  # AI 协议说明
├─ api.md                          # 接口文档草稿
├─ requirements.txt                # Python 依赖
└─ README.md                       # 项目说明
```

如果你后面要继续开发，最常用的入口文件通常是：

- 服务启动入口：[main.py](/D:/aigc/app/main.py)
- 总路由入口：[router.py](/D:/aigc/app/api/router.py)
- 认证接口：[auth.py](/D:/aigc/app/api/routes/auth.py)
- 消息接口：[messages.py](/D:/aigc/app/api/routes/messages.py)
- 学习路径接口：[learning.py](/D:/aigc/app/api/routes/learning.py)

## 7. 核心接口说明

项目业务接口统一前缀为：`/api/v1`

### 7.1 认证接口

#### 登录

`POST /api/v1/auth/login`

成功返回示例：

```json
{
  "code": 0,
  "message": "Login success",
  "data": {
    "access_token": "your-jwt-token",
    "token_type": "bearer",
    "expires_in": 86400,
    "user": {
      "id": 1,
      "username": "demo",
      "display_name": "Luna Reed",
      "avatar_url": "https://api.dicebear.com/9.x/adventurer/svg?seed=LunaReed",
      "status": "active"
    }
  }
}
```

如果账号不存在或密码错误，返回：

```json
{
  "detail": "\\u8d26\\u6237\\u6216\\u5bc6\\u7801\\u9519\\u8bef"
}
```

#### 注册

`POST /api/v1/auth/register`

请求示例：

```json
{
  "username": "Alice_001",
  "password": "StrongPass@123",
  "display_name": "Alice"
}
```

说明：

- `display_name` 当前保留为兼容字段
- 新用户注册后，服务端会自动按用户名从 mock 资料池中分配 `display_name` 和 `avatar_url`
- 注册返回、登录返回都会包含这两个字段

格式规则：

- `username`：4 到 20 位，必须字母开头，只允许字母、数字、下划线
- `password`：8 到 32 位，必须同时包含大写字母、小写字母、数字、特殊字符

### 7.2 会话接口

- `POST /api/v1/conversations`：创建会话
- `GET /api/v1/conversations`：分页查询会话列表
- `GET /api/v1/conversations/titles`：按最近时间返回历史会话标题
- `GET /api/v1/conversations/{conversation_id}/messages`：分页查询会话消息
- `GET /api/v1/conversations/{conversation_id}/messages/all`：查询会话全部消息

### 7.3 消息接口

#### 提交问题

`POST /api/v1/messages/question`

```json
{
  "conversation_id": 1,
  "content_text": "Please explain Newton's second law",
  "request_id": "req-20260422-0001"
}
```

成功后会：

- 保存用户问题到 `messages`
- 创建一条待处理任务到 `generation_tasks`
- 返回 `generation_task_id`

#### 提交反馈

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

说明：

- `regenerate=true` 时会创建新的重答任务
- 重答成功后可以覆盖旧答案
- 同一个 `request_id` 重复提交时，会按幂等逻辑返回同一个结果

### 7.4 任务接口

- `GET /api/v1/tasks/{task_id}`：查询任务详情
- `GET /api/v1/tasks/{task_id}/result`：查询任务状态和最终答案
- `GET /api/v1/tasks?conversation_id=1&status=pending&page=1&page_size=20`：分页查询任务

其中 `GET /api/v1/tasks/{task_id}/result` 的返回里会包含：

- `task`：任务本身的状态
- `answer_ready`：答案是否已生成
- `answer_message`：生成成功后的最终答案

### 7.5 后端任务分发接口

- `POST /api/v1/backend/tasks/claim`：后端领取待处理任务
- `POST /api/v1/backend/tasks/{task_id}/heartbeat`：任务处理中的续租心跳

说明：

- 支持 `pending` 任务正常领取
- 支持处理超时的 `running` 任务重新领取
- 重答任务会额外带上反馈上下文

### 7.6 后端回调接口

#### 模型答案回调

`POST /api/v1/callbacks/model-answer`

支持：

- 文本答案存储
- 多模态资产存储，如图片、思维导图、文件等
- 答案与任务绑定
- 反馈重答时覆盖旧答案
- 当 `meta_json.learning_path` 存在时，自动写入学习路径和节点

#### 模型失败回调

`POST /api/v1/callbacks/model-failure`

用于将任务标记为失败，并记录错误信息。

### 7.7 学习路径接口

当前已支持如下接口：

- `GET /api/v1/learning-paths/conversations/{conversation_id}/current`
- `GET /api/v1/learning-paths/{path_id}`
- `PATCH /api/v1/learning-paths/{path_id}/nodes/{node_id}/state`
- `POST /api/v1/learning-paths/{path_id}/checkins`
- `GET /api/v1/learning-paths/{path_id}/progress`
- `GET /api/v1/learning-paths/conversations/{conversation_id}/events`

用途说明：

- 获取某个会话当前的学习路径
- 查询学习路径中的所有节点
- 更新节点状态，如 `locked / available / in_progress / done`
- 记录用户每日打卡
- 汇总整体学习进度
- 查看会话中的学习行为事件时间线

## 8. 冒烟测试脚本

可以使用以下脚本快速验证功能是否正常：

- `python scripts/phase1_smoke_test.py`
- `python scripts/phase2_smoke_test.py`
- `python scripts/phase3_smoke_test.py`
- `python scripts/frontend_flow_smoke_test.py`
- `python scripts/backend_claim_flow_smoke_test.py`
- `python scripts/feedback_regenerate_overwrite_smoke_test.py`
- `python scripts/task_result_polling_smoke_test.py`
- `python scripts/learning_path_flow_smoke_test.py`
- `python scripts/runner_mock_flow_smoke_test.py`

## 9. 性能测试脚本

前端 JSON 写入链路压测：

```bash
python scripts/perf_frontend_json_flow.py --requests 500 --concurrency 50 --conversation-shards 50
```

后端 JSON 回调链路压测：

```bash
python scripts/perf_backend_json_flow.py --requests 500 --concurrency 50 --conversation-shards 50
```

如果启用了内部回调令牌，可加上：

```bash
python scripts/perf_backend_json_flow.py --internal-token your_token_here
```

脚本会输出：

- 总请求数
- 成功数 / 失败数
- 总耗时
- 吞吐量 `RPS`
- 平均延迟
- `P95` 延迟

## 10. 常见问题

### 10.1 中文变成 `????`

如果 MySQL 中中文内容显示异常，可以执行：

```sql
source scripts/fix_mysql_utf8mb4.sql;
```

如果只是 PowerShell 手动请求时出现乱码，建议：

- 在 JSON 中使用 Unicode 转义，如 `\u8bf7`
- 或直接运行项目自带的冒烟测试脚本进行验证

### 10.2 服务端启动了，但脚本连不上

请确认：

- `uvicorn app.main:app --reload` 已经在运行
- 地址是否为 `http://127.0.0.1:8000`
- 本地防火墙或端口占用没有阻塞

### 10.3 项目里是否留了创建数据库的代码

有，分为两部分：

- 纯 SQL 建库语句在本 README 的“环境要求”部分
- 表结构创建与 demo 用户初始化脚本在 [init_db.py](/D:/aigc/scripts/init_db.py)
- 数据库结构补丁与升级脚本在 [upgrade_phase2.py](/D:/aigc/scripts/upgrade_phase2.py)
