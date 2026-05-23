---
date: 2026-05-22
type: brainstorm
status: concluded
requirement_cycle: R007
topic: 消息持久化 + 对话管理
---

# R007 消息持久化 + 对话管理

## 背景

- R005 RISK-006 标记：localStorage 消息持久化不可靠（断网/换设备/清缓存丢失），R007 解决
- R006 已完成鉴权打通，后端可识别 user_id，为消息持久化提供前置条件
- R005 已预留：useChatStorage hook 封装了存储接口，R007 只需替换实现
- R008 计划引入 LangGraph Agent + 多轮上下文管理

## 已确认结论

### 1. 数据库选型：PostgreSQL（复用现有实例）

- xlfoundryTest 已有 PostgreSQL 在同一 Docker 网络运行
- OctoTutor 直接连上去建独立 database（`octotutor`）即可
- 不需要新容器、不需要改配置、不需要改 xlfoundryTest 任何东西
- R008 引入 LangGraph 时：PostgresSaver 用同一个实例，避免两套数据库并存

### 2. 数据模型

```sql
CREATE TABLE conversations (
    id UUID PRIMARY KEY,
    user_id VARCHAR NOT NULL,
    title VARCHAR NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE messages (
    id UUID PRIMARY KEY,
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    role VARCHAR NOT NULL,             -- 'human' / 'ai'（兼容 LangChain）
    content TEXT NOT NULL,
    sources JSONB,
    status VARCHAR DEFAULT 'completed',
    created_at TIMESTAMP DEFAULT NOW()
);
```

**role 格式**：使用 `human/ai`（非 `user/assistant`），与 LangChain HumanMessage/AIMessage 格式对齐。R008 引入 LangGraph 时零迁移。

### 3. 对话创建：前后端双重防重复

**前端**：点击"新建"按钮立即 disabled，防止连续点击

**后端**：POST /api/conversations 幂等检查——该用户是否已有空对话（无消息）？有则返回已有空对话，没有才创建

### 4. 消息保存时机

- 用户消息：立即 INSERT（保证不丢失）
- AI 回答：流式完成后 INSERT
- 流式中断：INSERT ai message (status='stopped', content=已有内容)
- 流式失败：INSERT ai message (status='error')

### 5. 切换对话：后台继续流式 + 自动保存

用户切换对话时，当前流式在后台继续运行，完成后自动保存到后端。用户切回来看完整回答（从后端加载）。不停流式、不丢内容。

### 6. 多对话 UI 布局

```
┌──────────────────────────────────────────────────┐
│  ┌─────────────┐  ┌──────────────────────────┐  │
│  │  对话列表     │  │  对话区域                 │  │
│  │             │  │                          │  │
│  │ ▶ 三角函数   │  │  用户: 求解 sin(x)=0     │  │
│  │   二次方程   │  │  AI: sin(x)=0 的解是...  │  │
│  │   概率问题   │  │                          │  │
│  │             │  │                          │  │
│  │  [+ 新对话]  │  │  ┌──────────────┐        │  │
│  │             │  │  │ 输入消息...   │        │  │
│  └─────────────┘  └──────────────────────────┘  │
└──────────────────────────────────────────────────┘
```

### 7. 后端 API 设计

```
对话管理（需要鉴权）：
  POST   /api/conversations              创建对话（幂等防重复）
  GET    /api/conversations              获取对话列表（按 updated_at 倒序）
  GET    /api/conversations/{id}/messages 获取某个对话的消息列表
  DELETE /api/conversations/{id}          删除对话

消息写入（内部调用）：
  ChatService.stream_chat() 内部自动保存

SSE 请求变更：
  POST /api/chat/stream Body 新增 conversation_id 字段
  conversation_id = null 时后端自动创建对话
```

### 8. 变更文件清单

```
后端新增：
  app/database.py                  # PostgreSQL 连接管理
  app/message/                     # 消息持久化模块
  alembic/                         # 数据库迁移

后端修改：
  app/main.py                      # 注册 message router + 数据库初始化
  app/chat/service.py              # 集成消息保存
  app/chat/schemas.py              # ChatRequest 新增 conversation_id
  requirements.txt                 # 新增 asyncpg, sqlalchemy, alembic

前端修改：
  src/hooks/use-chat-storage.ts    # 优先后端 API，降级 localStorage
  src/components/chat/chat-ui.tsx  # 新增对话列表侧边栏
  src/types/message.ts             # 新增 Conversation 类型
```

## 不做（留给 R008）

- 不引入 LangChain/LangGraph
- 不做多轮上下文管理（Agent 从 checkpoint 恢复对话状态）
- 不做 Agent 架构重构
