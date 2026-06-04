---
type: analysis
status: analyzed
requirement_cycle: R016
topic: conversation-security-fix
date: 2026-06-04
---

# 对话安全与初始化修复 — 功能分析

## 概述

新用户首次访问时，右侧聊天区域永远显示"加载中"。根因是后端 `_load_from_postgres_saver` 的 `user_id` 过滤失效，导致跨用户数据泄漏：`/conversations/current` 返回了其他用户的对话数据，而非 204 No Content。前端 catch 块未推进 `isInitialized` 状态，加剧了问题。

本需求修复 3 个相互关联的 bug：
1. 后端数据泄漏（HIGH — 安全漏洞）
2. 前端初始化状态卡死（MEDIUM — 体验阻断）
3. 加载失败无错误提示（LOW — 体验缺陷）

## 一、交互链

### 场景 1：新用户首次访问

**用户故事**：作为新注册用户，我首次打开 OctoTutor，看到空白对话列表和干净的聊天区域，可以开始第一次对话。

1. 用户注册并登录
2. 进入主页面
3. 左侧侧边栏显示"暂无对话"（正确）
4. 右侧聊天区域应显示空状态/欢迎界面
5. 用户点击"新建对话"开始聊天

**当前 bug**：第 4 步，右侧永远显示"加载中..."

```mermaid
flowchart TD
    A[新用户登录] --> B[前端初始化 auth]
    B --> C[fetchConversationList]
    C --> D{返回数据?}
    D -->|空列表| E[INIT_LIST: items=[], isInitialized=true]
    E --> F[SET_ACTIVE: null]
    F --> G[controller: loadConversation null]
    G --> H{GET /conversations/current}
    H -->|应返回 204| I[空状态 UI]
    H -->|BUG: 返回 200 + 他人数据| J[加载异常]
```

### 场景 2：用户加载自己的对话

**用户故事**：作为已有对话的用户，我打开 OctoTutor 时能看到自己的对话列表，点击任一对话能正确加载消息。

1. 用户登录
2. 前端拉取对话列表
3. 选中最近对话
4. `GET /conversations/current?conversation_id=xxx`
5. 后端验证 `user_id` 归属后返回消息
6. 前端渲染消息列表

**当前 bug**：第 5 步归属验证失效（`load_conversation_by_id` 同样从 `config` 读 `user_id`，永远为 `None`）

## 二、逻辑树

### 事件流：新用户访问

| 时刻 | 事件 | 处理 | 产生的新事件 |
|------|------|------|-------------|
| T1 | auth-context 初始化 | 调用 `service.init()`，获取 token | `isInitialized = true` |
| T2 | conversation-context useEffect 触发 | `fetchConversationList()` → `GET /api/conversations` | 返回空列表 |
| T3 | INIT_LIST dispatch | `items=[], isInitialized=true` | `SET_ACTIVE: null` |
| T4 | controller useEffect 触发 | `loadConversation(null)` → `GET /api/conversations/current` | **BUG 在此** |
| T5 | 后端 `_load_from_postgres_saver` | `alist()` 遍历所有 checkpoint，`user_id` 过滤失效 | 返回 200 + 他人数据 |
| T6 | 前端收到非 204 响应 | 尝试解析数据，状态异常 | 可能导致渲染异常 |
| T6' | 前端 catch 块触发 | `SET_LOADING: false` 但未设 `isInitialized: true` | `isInitialized` 永远为 false |
| T7 | controller 检查 `isConvReady` | 检查 `conversation.isInitialized` — false | 不触发 `loadConversation` |
| T8 | chat-ui 检查 `mounted` | false → 显示"加载中..." | 永久卡住 |

### 状态流转

| 实体 | 触发事件 | 前状态 | 后状态 |
|------|---------|--------|--------|
| conversation state | INIT_LIST | `{isInitialized: false, items: []}` | `{isInitialized: true, items: []}` |
| conversation state | catch 块（BUG） | `{isInitialized: true, isLoading: true}` | `{isInitialized: true, isLoading: false}` |
| chat-ui mounted | controller 不触发 | false | false（卡住） |

### Bug 根因分析

**Bug 1：数据泄漏（后端）**

LangGraph PostgresSaver 的 `alist()` 返回的 `CheckpointTuple` 中：
- `config.configurable` 只包含 `thread_id`（核心字段）
- 额外的 configurable 字段（如 `user_id`）被存入 `metadata`

```python
# stream_router.py 保存时 — user_id 放在 configurable
config = {"configurable": {"thread_id": "...", "user_id": "..."}}

# alist() 读取时 — user_id 不在 config 里，在 metadata 里
tuple_item.config["configurable"]  → {"thread_id": "..."}  # 无 user_id
tuple_item.metadata                → {"user_id": "..."}     # user_id 在这里
```

3 处代码都从 `config` 读 `user_id`，永远得到 `None`：
1. `conversation_router.py:112` — `_load_from_postgres_saver`
2. `conversation_utils.py:59` — `load_conversation_by_id`
3. `conversation_utils.py:28` — `extract_latest_messages`（MemorySaver 路径，meta 结构不同，暂不影响）

**Bug 2：前端 catch 块（前端）**

`conversation-context.tsx:88-92`：catch 只设 `SET_LOADING: false`，没有 dispatch `INIT_LIST`（含 `isInitialized: true`）。如果 API 调用失败，`isInitialized` 永远为 false，controller 不会触发 `loadConversation`。

**Bug 3：无错误 UI（前端）**

`chat-ui.tsx:32-38`：只有 `!mounted` → "加载中..."，没有 error/retry 状态。

## 三、功能编号与网络定位

### 本次新增节点

| 编号 | 功能节点 | 前缀含义 | 简介 |
|------|---------|---------|------|
| BB001 | 对话归属校验修复 | 后端业务 | 修复 checkpointer 读取 user_id 的来源（config → metadata），3 处 |
| FF001 | 对话列表初始化容错 | 前端业务 | catch 块 dispatch INIT_LIST 推进 isInitialized |
| FF002 | 聊天区域错误状态 | 前端业务 | 加载失败时显示错误提示 + 重试按钮 |

### 前置依赖

| 依赖节点 | 依赖方式 | 是否已有 |
|----------|---------|---------|
| R009 对话管理 | 共享 conversation_router / conversation_utils | ✅ 已有 |
| R006 认证集成 | 共享 auth middleware / JWT user_id | ✅ 已有 |
| R007 checkpoint 持久化 | 共享 PostgresSaver checkpointer | ✅ 已有 |

### 边界接口

| 接口/协议 | 定义方 | 消费方 | 敏感度 |
|-----------|--------|--------|--------|
| `GET /api/conversations/current` | conversation_router | 前端 controller | HIGH — 涉及用户数据隔离 |
| `GET /api/conversations` | conversation_router | 前端 conversation-context | HIGH — 列表已正确过滤 |
| `CheckpointTuple.metadata["user_id"]` | LangGraph PostgresSaver | conversation_utils | HIGH — 归属校验依赖 |

## 四、结论

- **开发顺序**：BB001（后端安全修复）→ FF001（前端容错）→ FF002（错误 UI）
- **复杂度集中**：BB001 是核心，需确认 `metadata` 字段在不同 LangGraph 版本中的稳定性
- **暂不实现**：邮箱验证（属于 auth-center 项目，记录到 backlog）
- **风险评估**：BB001 是安全漏洞，最高优先级；FF001 是体验阻断，次高优先级
