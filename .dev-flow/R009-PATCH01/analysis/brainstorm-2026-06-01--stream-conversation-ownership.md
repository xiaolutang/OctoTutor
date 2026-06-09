---
requirement_cycle: R009-PATCH01
patch_for: R009
date: 2026-06-01
type: brainstorm
status: concluded
topic: stream-conversation-ownership
---

# 补丁：流式对话 conversation_id 用户归属校验

## 背景

在复盘 R009 多对话管理文章时，发现当前 `/api/chat/stream` 对已有 `conversation_id` 的处理存在安全边界遗漏。

R009 中 `conversation.id = LangGraph thread_id`，列表、更新、删除接口都通过 `id + user_id` 查询 `conversations` 表，能够保证用户只能操作自己的对话元数据。

但流式发送接口当前逻辑是：

```text
conversation_id = body.conversation_id or uuid4()

如果没有 conversation_id：
  创建新 conversation，user_id = 当前用户

如果已有 conversation_id：
  直接作为 LangGraph thread_id 使用
```

也就是说，已有 `conversation_id` 进入 `/api/chat/stream` 时，当前代码没有先确认这条 conversation 是否属于当前登录用户。

## 补丁描述

为 `/api/chat/stream` 增加已有 `conversation_id` 的用户归属校验：

- 新对话：仍由后端生成 UUID，并创建 `conversations` 记录
- 已有对话：先用 `conversation_id + user_id` 查询 `conversations` 表
- 如果对话不存在或不属于当前用户，拒绝本次流式请求
- 只有归属校验通过后，才能把 `conversation_id` 作为 LangGraph `thread_id` 使用

## 影响范围

- 原始 RC：R009
- 补丁 RC：R009-PATCH01
- 主要后端文件：
  - `backend/app/chat/stream_router.py`
  - `backend/app/infra/conversation_repo.py`（如需复用现有 `get_by_id`）
  - `backend/tests/test_stream_conversation.py`
  - `backend/tests/test_sse_integration.py`

## 需要澄清的边界

1. 已有 `conversation_id` 不存在时，应该返回 SSE error 事件，还是直接 HTTP 错误？
2. 对话归属校验失败时，错误码使用现有 conversation 错误码，还是新增 chat stream 错误码？
3. 如果历史 checkpoint 存在但 `conversations` 表记录不存在，是否允许继续对话？

初步倾向：

- stream 接口保持 SSE 协议一致性，返回 SSE `error` 事件更符合现有前端处理方式。
- 归属失败应该统一视为“对话不存在或不可访问”，不要暴露是否存在他人对话。
- `conversations` 表是 R009 之后的业务入口，已有 `conversation_id` 必须有对应业务记录，否则拒绝继续使用。

## 验收方向

- 用户 A 创建对话后，用户 B 使用该 `conversation_id` 调用 `/api/chat/stream` 应失败
- 用户 A 使用自己的 `conversation_id` 继续对话应成功
- 不传 `conversation_id` 的新对话流程不回归
- 失败时不得写入他人的 LangGraph checkpoint
- 失败时不得更新他人的 `conversations.updated_at` 或 `message_count`
