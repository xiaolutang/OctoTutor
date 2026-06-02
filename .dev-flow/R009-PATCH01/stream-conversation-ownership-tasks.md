---
version: "1.0"
type: tasks
topic: stream-conversation-ownership
requirement_cycle: R009-PATCH01
patch_for: R009
workflow:
  evaluate_provider: local
  mode: auto
status: archived
---

# 流式对话 conversation_id 归属校验 — 后端任务清单

基于 `2026-06-01--stream-conversation-ownership-design.md` 设计，补齐 `/api/chat/stream` 使用已有 `conversation_id` 前的用户归属校验。

全局约束：

- 新对话流程不变：不传 `conversation_id` 时仍由后端生成 UUID 并创建 `conversations` 记录。
- 已有对话必须通过 `ConversationRepo.get_by_id(db, conversation_id, user.user_id)` 校验归属。
- 校验失败返回 SSE `error`，不发送 `init`，不调用 `graph.astream`。
- 不新增前端改动，不新增错误码，复用 `ConversationErrorCode.NOT_FOUND = 03901`。
- 当前 active RC 为 R010，且 R010 也涉及 `backend/app/chat/stream_router.py`。执行前必须检查当前文件状态，基于最新代码合并，不得覆盖 R010 已有改动。

---

## 执行顺序

1. ✅ 任务 1 — `stream_router.py` — 已有 conversation_id 归属校验（无依赖）
   - ✅ 1.1 补充 conversation error import
   - ✅ 1.2 在进入 `graph.astream` 前校验已有 conversation 归属
   - ✅ 1.3 归属失败返回 SSE error，不发送 init
   - ✅ 1.4 DB 异常返回内部错误 SSE error
2. ✅ 任务 2 — `test_stream_conversation.py` — stream 归属校验单元/集成测试（依赖任务 1）
   - ✅ 2.1 更新已有 conversation 测试 mock
   - ✅ 2.2 新增归属通过测试
   - ✅ 2.3 新增归属失败测试
   - ✅ 2.4 新增 DB 异常测试
   - ✅ 2.5 确认新对话测试不回归
3. ✅ 任务 3 — `test_sse_integration.py` / 鉴权相关测试 — SSE 回归覆盖（依赖任务 1）
   - ✅ 3.1 更新现有带 `conversation_id` 的 SSE 测试
   - ✅ 3.2 新增或调整越权场景，确认不进入 graph
4. ✅ 任务 4 — `architecture.md` — 记录 stream 归属不变量（依赖任务 1）
   - ✅ 4.1 在权威边界或不变量中补充 stream 使用已有 conversation_id 前必须校验 `id + user_id`
5. ✅ 最后 — 验证路径
   - ⬜ 5.1 运行 targeted tests
   - ⬜ 5.2 如时间允许运行后端全量测试

---

## R009-PATCH01-BB001：stream_router.py — 已有 conversation_id 归属校验 `✅ 已完成`

- 文件：`backend/app/chat/stream_router.py`
- 改动类型：修改
- domain: backend
- task_layer: business
- depends_on: []
- priority: 5
- risk_tags: [security, auth, sse, r010_conflict]
- smoke_required: true
- mode: negotiated
- status: pending
- acceptance_criteria:
  - 不传 `conversation_id` 的新对话流程保持现有行为
  - 传入已有 `conversation_id` 时会调用 `ConversationRepo.get_by_id(db, conversation_id, user.user_id)`
  - `get_by_id` 返回记录时才允许进入 `graph.astream`
  - `get_by_id` 返回 `None` 时返回 SSE `error`，错误码 `03901`
  - `get_by_id` 抛异常时返回 SSE `error`，错误码 `02901`
  - 归属失败或 DB 异常时不发送 `init`
  - 归属失败或 DB 异常时不调用 `graph.astream`
  - 归属失败或 DB 异常时不调用 `ConversationRepo.update_message_stats`
- test_tasks:
  - type: integration
    description: stream endpoint 已有 conversation_id 归属校验
    scenarios: [自己的对话继续成功, 他人的对话返回03901, DB异常返回02901, 新对话不回归]
- contract_refs: []
- decision_refs: []
- blocked_files: []

### BB001.1 补充 import `⬜`

在现有：

```python
from app.chat.errors import ChatErrorCode, make_error
```

基础上补充：

```python
from app.chat.errors import (
    ChatErrorCode,
    ConversationErrorCode,
    make_conversation_error,
    make_error,
)
```

如项目格式偏好单行 import，可按现有 formatter 调整。

### BB001.2 新增已有 conversation 归属校验 `⬜`

在 `conversation_id` / `is_new_conversation` 计算之后，`config` 构造之前新增已有对话分支。

关键骨架：

```python
conversation_id = body.conversation_id or str(uuid.uuid4())
is_new_conversation = not body.conversation_id

if is_new_conversation:
    conv = Conversation(id=conversation_id, user_id=user.user_id)
    await ConversationRepo.create(db, conv)
    await db.commit()
else:
    try:
        conv = await ConversationRepo.get_by_id(db, conversation_id, user.user_id)
    except Exception:
        logger.exception("[stream] conversation ownership check failed")
        return StreamingResponse(
            _single_error_event(make_error(ChatErrorCode.INTERNAL_ERROR)),
            media_type="text/event-stream",
        )

    if conv is None:
        return StreamingResponse(
            _single_error_event(
                make_conversation_error(ConversationErrorCode.NOT_FOUND)
            ),
            media_type="text/event-stream",
        )
```

说明：

- `_single_error_event` 可以是局部 async generator，也可以提取为私有 helper。
- 如果提取 helper，放在 `stream_router.py` 内，避免新增文件。
- 失败分支必须在 `config` 和 `event_generator()` 启动前返回。

### BB001.3 错误 SSE helper `⬜`

推荐新增私有 helper，避免重复定义局部 generator：

```python
async def _single_error_event(error: dict):
    yield _sse_frame("error", error)
```

放置位置：

- 可放在 `_sse_frame` 附近；
- 或放在 `stream_chat` 前后，但不要影响现有 `_map_event_to_sse`。

### BB001.4 保持新对话行为不变 `⬜`

新对话分支不得引入 `get_by_id`：

```text
body.conversation_id is None
→ ConversationRepo.create
→ db.commit
→ SSE init
→ graph.astream
→ update_message_stats
→ done
→ title（如果生成成功）
```

---

## R009-PATCH01-BB002：test_stream_conversation.py — stream 归属校验测试 `✅ 已完成`

- 文件：`backend/tests/test_stream_conversation.py`
- 改动类型：修改
- domain: backend
- task_layer: business
- depends_on: [R009-PATCH01-BB001]
- priority: 5
- risk_tags: [security, sse]
- smoke_required: true
- mode: negotiated
- status: pending
- acceptance_criteria:
  - 现有已有 conversation 测试通过
  - 新增归属通过测试覆盖 `get_by_id` 返回 Conversation
  - 新增归属失败测试覆盖 `get_by_id` 返回 None
  - 新增 DB 异常测试覆盖 `get_by_id` 抛异常
  - 归属失败和异常测试均断言没有 `init`
  - 归属失败和异常测试均断言不调用 `update_message_stats` / `update`
- test_tasks:
  - type: integration
    description: stream conversation ownership 测试
    scenarios: [existing owned, existing not found, db exception, new conversation regression]
- contract_refs: []
- decision_refs: []
- blocked_files: []

### BB002.1 更新已有 conversation 测试 mock `⬜`

现有传入 `conversation_id` 的测试需要补：

```python
from app.domain.models import Conversation

MockRepo.get_by_id = AsyncMock(
    return_value=Conversation(id="conv-existing-001", user_id="user-123")
)
```

至少覆盖：

- `test_existing_conversation_no_create`
- `test_existing_conversation_no_title_generation`
- 其他带固定 `conversation_id` 的事件顺序 / message_count 测试

### BB002.2 新增归属通过测试 `⬜`

测试名建议：

```python
def test_existing_conversation_checks_ownership_before_stream(self):
```

断言骨架：

```python
MockRepo.get_by_id = AsyncMock(
    return_value=Conversation(id="conv-owned-001", user_id="user-123")
)

resp = client.post(..., json={"question": "...", "conversation_id": "conv-owned-001"})
frames = parse_sse_frames(resp.text)

MockRepo.get_by_id.assert_awaited_once()
assert MockRepo.get_by_id.call_args.args[1] == "conv-owned-001"
assert MockRepo.get_by_id.call_args.args[2] == "user-123"
assert frames[0]["type"] == "init"
assert frames[0]["data"]["conversation_id"] == "conv-owned-001"
MockRepo.create.assert_not_called()
```

### BB002.3 新增归属失败测试 `⬜`

测试名建议：

```python
def test_existing_conversation_not_owned_returns_error_without_stream(self):
```

断言骨架：

```python
MockRepo.get_by_id = AsyncMock(return_value=None)
MockRepo.update_message_stats = AsyncMock()
MockRepo.update = AsyncMock()

resp = client.post(..., json={"question": "...", "conversation_id": "conv-other-user"})
frames = parse_sse_frames(resp.text)

assert resp.status_code == 200
assert frames[0]["type"] == "error"
assert frames[0]["data"]["code"] == "03901"
assert all(f["type"] != "init" for f in frames)
MockRepo.update_message_stats.assert_not_called()
MockRepo.update.assert_not_called()
```

如果测试需要断言 `graph.astream` 未调用，可传入 `mock_graph = MagicMock()`，并设置其 `astream` 为可检测对象。

### BB002.4 新增 DB 异常测试 `⬜`

测试名建议：

```python
def test_existing_conversation_ownership_db_error_returns_internal_error(self):
```

断言骨架：

```python
MockRepo.get_by_id = AsyncMock(side_effect=RuntimeError("db down"))

resp = client.post(..., json={"question": "...", "conversation_id": "conv-db-error"})
frames = parse_sse_frames(resp.text)

assert frames[0]["type"] == "error"
assert frames[0]["data"]["code"] == "02901"
assert all(f["type"] != "init" for f in frames)
MockRepo.update_message_stats.assert_not_called()
```

### BB002.5 新对话不回归 `⬜`

现有新对话测试需要补充断言：

```python
MockRepo.get_by_id.assert_not_called()
```

确保新对话不会误走已有 conversation 校验。

---

## R009-PATCH01-BB003：SSE 集成 / 鉴权回归测试 `✅ 已完成`

- 文件：
  - `backend/tests/test_sse_integration.py`
  - `backend/tests/test_router_auth_integration.py`（如需）
- 改动类型：修改
- domain: backend
- task_layer: business
- depends_on: [R009-PATCH01-BB001]
- priority: 4
- risk_tags: [sse, auth, regression]
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - `test_sse_integration.py` 中所有传入 `conversation_id` 的测试补齐 `ConversationRepo.get_by_id` mock 或测试数据
  - SSE 端到端测试仍保持 `init/status/sources/token/done/title/error` 协议兼容
  - 鉴权测试确认未登录请求仍被鉴权层拦截，不进入归属校验
- test_tasks:
  - type: integration
    description: SSE 端到端和鉴权回归
    scenarios: [existing conversation with ownership, unauthenticated request, invalid ownership error]
- contract_refs: []
- decision_refs: []
- blocked_files: []

### BB003.1 更新带 conversation_id 的 SSE 测试 `⬜`

检查 `backend/tests/test_sse_integration.py` 中所有请求体包含：

```json
{"conversation_id": "..."}
```

的测试，补齐：

```python
with patch("app.chat.stream_router.ConversationRepo") as MockRepo:
    MockRepo.get_by_id = AsyncMock(return_value=Conversation(id=..., user_id="user-123"))
```

避免新增归属校验后，原回归测试误走 03901 分支。

### BB003.2 鉴权优先级回归 `⬜`

确认未登录 / 无效 token 请求仍由鉴权层拒绝，不进入 `ConversationRepo.get_by_id`。

如现有 `test_router_auth_integration.py` 已覆盖 `/api/chat/stream`，只需运行验证；如未覆盖，可新增最小断言。

---

## R009-PATCH01-BD001：architecture.md — stream 归属不变量 `✅ 已完成`

- 文件：`.dev-flow/architecture.md`
- 改动类型：修改
- domain: docs
- task_layer: foundation
- depends_on: [R009-PATCH01-BB001]
- priority: 3
- risk_tags: [architecture, security]
- smoke_required: false
- mode: direct
- status: pending
- acceptance_criteria:
  - `architecture.md` 记录 `/api/chat/stream` 使用已有 `conversation_id` 前必须校验归属
  - 记录位置在“权威边界”或“不变量”
  - 文案明确校验条件是 `conversations.id + user_id`
  - 不改变其他 R010 架构结论
- test_tasks:
  - type: unit
    description: 文档检查
    scenarios: [包含stream归属校验不变量]
- contract_refs: []
- decision_refs: []
- blocked_files: []

### BD001.1 补充架构不变量 `⬜`

建议在“不变量”中追加：

```text
- /api/chat/stream 使用已有 conversation_id 前必须通过 conversations 表按 id + user_id 校验归属；校验失败不得进入 LangGraph thread_id。
```

如放在“权威边界”，文案可调整为：

```text
- Backend 是 conversation_id 归属校验边界；/api/chat/stream 不信任客户端传入的 conversation_id，必须按 id + user_id 校验后才能进入 LangGraph。
```

---

## R009-PATCH01-BV001：验证路径 `✅ 已完成`

- 文件：无固定文件
- 改动类型：验证
- domain: backend
- task_layer: business
- depends_on: [R009-PATCH01-BB002, R009-PATCH01-BB003, R009-PATCH01-BD001]
- priority: 5
- risk_tags: [security, regression]
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - targeted tests 通过
  - 无语法错误
  - 如运行后端全量测试，记录结果
- test_tasks:
  - type: integration
    description: targeted pytest
    scenarios: [stream_conversation, sse_integration, router_auth]
- contract_refs: []
- decision_refs: []
- blocked_files: []

### BV001.1 运行 targeted tests `⬜`

建议执行：

```bash
cd backend
python -m pytest tests/test_stream_conversation.py -v
python -m pytest tests/test_sse_integration.py -v
python -m pytest tests/test_router_auth_integration.py -v
```

### BV001.2 后端全量测试 `⬜`

如时间允许执行：

```bash
cd backend
python -m pytest -v
```

如果全量测试因当前 R010 未完成导致失败，需要在 evidence 中区分：

- 本补丁相关失败
- R010 当前开发态失败
- 环境问题
