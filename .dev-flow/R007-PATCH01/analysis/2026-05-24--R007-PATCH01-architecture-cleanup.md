---
type: analysis
status: analyzed
requirement_cycle: R007-PATCH01
patch_for: R007
topic: architecture-cleanup
date: 2026-05-24
---

# 架构收敛 — 死代码清理 + 安全隔离 + 封装修复

## 概述

R007 实现完成后，通过 6 视角 simplify 审查发现 9 项架构问题。
本补丁修复安全漏洞（user_id 隔离缺失）、封装违反（graph.py 访问私有属性）、
4 处死代码、3 处重复逻辑。不改变业务行为，不改 API 接口，不改 SSE 事件格式。

## 一、交互链

本补丁不引入新用户交互，修复的是系统内部行为。核心场景：

### 场景 1：用户 A 看不到用户 B 的对话

**用户故事**：作为登录用户，我刷新页面后只能看到自己的对话，以便保护隐私。

**当前行为**：`_load_latest_conversation` 遍历所有 thread 不按 user_id 过滤，用户 A 可能看到用户 B 的对话。

**修复后**：查询时按 `config.configurable.user_id` 过滤，确保只返回当前用户的对话。

### 场景 2：graph 重构不崩溃

**用户故事**：作为开发者，我修改 LLMGenerator 内部实现后 graph 不会崩溃。

**当前行为**：`graph.py` 直接访问 `generator._client.api_key` 等私有属性，改内部实现就崩。

**修复后**：LLMGenerator 暴露公共方法 `get_chat_model()` 返回 ChatOpenAI 实例。

## 二、逻辑树

### 事件流：用户加载对话历史

| 时刻 | 事件 | 处理 | 产生的新事件 |
|------|------|------|-------------|
| T1 | 前端 GET /api/conversations/current | conversation_router 接收请求 | — |
| T2 | get_current_user 解析 JWT | 提取 user_id | — |
| T3 | _load_conversation_by_id 或 _load_latest | **按 user_id 过滤**查询 checkpointer | — |
| T4 | 返回 200 + {messages} 或 204 | 前端渲染消息列表 | — |

**当前 T3 的问题**：
- MemorySaver 路径：遍历全部 `checkpointer.storage`，不检查 thread 的 user_id
- PostgresSaver 路径：`alist(None, limit=100)` 不传 user_id，加载全局 100 条 checkpoint

**修复后 T3**：
- MemorySaver 路径：从 checkpoint metadata 中读取 user_id，过滤非当前用户的 thread
- PostgresSaver 路径：在 config 中传入 user_id，或过滤后返回

### 事件流：graph 创建 LLM 客户端

| 时刻 | 当前行为 | 修复后 |
|------|---------|--------|
| startup | `graph.py` 访问 `generator._client.api_key` | 调用 `generator.get_chat_model()` |
| startup | 构建新 `ChatOpenAI(api_key=..., base_url=..., model=...)` | 直接使用返回的 ChatOpenAI |

### 状态流转：无新状态

本补丁不引入新实体或新状态，仅修复查询过滤和清理代码。

## 三、功能编号与网络定位

### 本次新增节点

| 编号 | 功能节点 | 前缀含义 | 简介 |
|------|---------|---------|------|
| BF001 | LLMGenerator 公共接口 | 后端基础 | 暴露 `get_chat_model()` 方法，返回 ChatOpenAI 实例 |
| BF002 | 共享工具函数提取 | 后端基础 | 提取 `_build_numbered_context()` 和 `chunks_to_sources()` 到公共位置 |
| BB001 | conversation_router user_id 隔离 | 后端业务 | 按 user_id 过滤对话查询，确保用户隔离 |
| BB002 | conversation_router 重复逻辑消除 | 后端业务 | 统一 MemorySaver/PostgresSaver 遍历逻辑 |
| BB003 | 后端死代码清理 | 后端业务 | 删除 ChatService.stream_chat()、nodes.py 空壳 |
| FB001 | 前端死代码清理 | 前端业务 | 删除 use-chat-storage.ts、use-conversation.ts 冗余 state |
| FF001 | architecture.md 目录结构修正 | 前端基础 | 更新 Monorepo 路径描述 |

### 前置依赖

| 依赖节点 | 依赖方式 | 是否已有 |
|----------|---------|---------|
| R007 graph.py create_graph | 修改 BF001 处的 LLMGenerator 调用 | 是 |
| R007 conversation_router | 修改 BB001/BB002 处的查询逻辑 | 是 |
| R007 controller.ts | 修改 FB001 处的 import | 是 |
| R007 use-chat-storage.ts | 删除整个文件 | 是 |

### 边界接口

| 接口/协议 | 定义方 | 消费方 | 敏感度 |
|-----------|--------|--------|--------|
| `LLMGenerator.get_chat_model()` | BF001 (infra/llm.py) | graph.py | 中 — 新增公共方法 |
| `chunks_to_sources(chunks)` | BF002 (domain/models.py 或新 utils) | graph.py, service.py, llm.py | 低 — 提取已有逻辑 |
| `_find_latest_messages(storage, user_id)` | BB002 (conversation_router.py 内部) | _load_conversation_by_id, _load_latest | 低 — 内部重构 |

### 涉及的 architecture.md 变更

| 变更点 | 当前值 | 修正为 |
|--------|--------|--------|
| INV-1 Monorepo 路径 | `services/frontend/ + services/backend/` | `frontend/ + backend/` |
| FORBID-5 前端 LLM 缓存 | "不做前端 LLM 回答缓存" | 补充说明：localStorage 消息缓存已移除 |

## 四、结论

### 开发顺序

```
BF001 (LLMGenerator 公共接口) → BB001 (user_id 隔离)
BF002 (共享工具提取)          → BB002 (重复逻辑消除)
                             → BB003 (后端死代码清理)
                             → FB001 (前端死代码清理)
                             → FF001 (architecture.md 修正)
```

- BF001 和 BF002 无依赖可并行
- BB001 依赖 BF001（如果 get_chat_model 需要 user_id 相关配置）
- BB003、FB001、FF001 互相独立可并行

### 复杂度集中

1. **BB001 user_id 隔离** — MemorySaver 路径需要从 checkpoint 元数据中获取 user_id，而 MemorySaver 不像 PostgresSaver 那样有 configurable.user_id。需要确认 MemorySaver checkpoint 元数据中是否包含 user_id。如果不包含，MemorySaver 路径的隔离需要不同策略。
2. **BB002 重复逻辑消除** — conversation_router 中 MemorySaver 路径直接遍历 storage dict，绕过了 LangGraph 的公开 API。消除重复的同时需要决定是否保留 MemorySaver 特殊路径。

### 暂不实现

| 功能 | 理由 |
|------|------|
| conversation_router 完全统一用 aget/alist | MemorySaver 的 aget 行为与 PostgresSaver 不同，贸然统一可能引入 bug |
| 旧 `/api/chat` 路径的 prompt 统一 | 旧路径是否保留是产品决策，不属于架构清理 |
| main.py lifespan 并行化初始化 | 性能优化，不属于架构清理 |
| controller.ts onToken 性能优化（ref 累积） | 性能优化，当前功能正确 |
