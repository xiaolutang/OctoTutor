---
requirement_cycle: R007-PATCH01
patch_for: R007
date: 2026-05-24
type: brainstorm
status: concluded
---

# 补丁：架构收敛 — 死代码清理 + 安全隔离 + 封装修复

## 背景

R007（persistence-agent-upgrade）实现完成后，通过 xlfoundry-simplify 6 视角并行审查发现多项架构问题。
问题涵盖安全漏洞（user_id 隔离缺失）、封装违反（graph.py 访问私有属性）、大量死代码、重复逻辑。
这些问题不属于收敛范畴，需作为独立补丁 RC 修复。

## 补丁描述

### P0 安全问题（必须修复）

1. **user_id 隔离缺失** — `conversation_router.py` 的 `_load_from_postgres_saver` 和 `_load_from_memory_saver` 未按 user_id 过滤，任何登录用户可看到所有人对话。
2. **封装违反** — `graph.py:77-82` 直接访问 `generator._client.api_key` 等私有属性，应在 LLMGenerator 上暴露公共接口。

### P1 死代码清理

3. **`ChatService.stream_chat()`** — `service.py:62-127`，无任何路由调用，与 LangGraph 路径完全重叠。
4. **`saveMessages()` / `loadMessages()`** — `use-chat-storage.ts`，写入 localStorage 的消息数据从未被读取（前端已改为从后端 API 加载），违反 architecture.md "不做前端 LLM 回答缓存" 禁止模式。
5. **`retrieve_node` / `respond_node` 空壳** — `nodes.py:36-48`，实际逻辑在 graph.py 闭包中，返回 `{}` 造成误导。
6. **use-conversation 内部 conversationId state** — `use-conversation.ts:58`，set 了但从未被外部消费，controller 有自己的副本。

### P2 重复代码消除

7. **`_build_numbered_context()`** — `graph.py` vs `llm.py` 完全重复。
8. **SourceReference 构建逻辑** — 在 `graph.py`、`service.py`、`llm.py` 三处重复。
9. **MemorySaver 遍历逻辑** — `conversation_router.py` 内 `_load_conversation_by_id` vs `_load_from_memory_saver` 高度重复。

## 影响范围

- 原始 RC：R007
- 补丁 RC：R007-PATCH01
- 后端文件：`graph.py`, `conversation_router.py`, `service.py`, `nodes.py`, `llm.py`
- 前端文件：`use-conversation.ts`, `use-chat-storage.ts`, `controller.ts`
- 架构文档：`architecture.md`（目录结构修正）

## 约束

- 不改业务逻辑，不改 SSE 事件格式，不改 API 接口
- 不动 LangGraph StateGraph 编排结构
- 清理死代码时不引入新行为
