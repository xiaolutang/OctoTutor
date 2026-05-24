---
version: "1.0"
type: tasks
topic: architecture-cleanup
requirement_cycle: R007-PATCH01
workflow:
  evaluate_provider: local
  mode: auto
status: completed
---

# 架构收敛 — 任务清单

全局约束：
- 不改业务逻辑，不改 API 接口，不改 SSE 事件格式
- 不动 LangGraph StateGraph 编排结构
- 先后端再前端；同端内按依赖层级排序
- ChatService._retrieve 保持私有不改公开
- `_load_conversation_by_id` 必须验证 user_id 归属

---

## 执行顺序

1. ✅ R007-PATCH01-BF001 — LLMGenerator 封装修复（无依赖）
2. ✅ R007-PATCH01-BF002 — 共享工具函数提取（无依赖）
3. ✅ R007-PATCH01-BB001 — conversation_router user_id 隔离（依赖 BF001）
4. ✅ R007-PATCH01-BB002 — conversation_router 重复逻辑消除（依赖 BB001）
5. ✅ R007-PATCH01-BB003 — 后端死代码清理（依赖 BF002）
6. ✅ R007-PATCH01-FB001 — 前端死代码清理（无依赖，可与后端并行）
7. ✅ R007-PATCH01-FF001 — architecture.md 目录修正（无依赖）
8. ✅ 最后 — 全量构建验证

---

## R007-PATCH01-BF001：infra/llm.py — LLMGenerator 封装修复 `⬜ 待处理`

- 文件：`backend/app/infra/llm.py`
- 改动类型：修改
- domain: backend
- task_layer: foundation
- depends_on: []
- priority: 5
- risk_tags: []
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - LLMGenerator.__init__ 新增 `self._api_key` 和 `self._base_url` 属性
  - 新增 `get_chat_model()` 方法返回 `ChatOpenAI(streaming=True)`
  - `graph.py` 中无 `generator._client` 或 `generator._model` 访问
- test_tasks:
  - type: unit
    description: 验证 get_chat_model 返回 ChatOpenAI 实例且参数正确
    scenarios: ["get_chat_model 返回 streaming=True 的 ChatOpenAI", "api_key/base_url/model 与构造参数一致"]
- contract_refs: []
- decision_refs: []
- blocked_files: []

### BF001.1 __init__ 缓存 api_key/base_url `⬜`

在 `__init__` 方法中新增两行：
```python
def __init__(self, api_key: str, base_url: str, model: str) -> None:
    self._api_key = api_key      # 新增
    self._base_url = base_url    # 新增
    self._model = model
    self._client = OpenAI(api_key=api_key, base_url=base_url)
    self._async_client = AsyncOpenAI(api_key=api_key, base_url=base_url)
```

### BF001.2 新增 get_chat_model 方法 `⬜`

```python
def get_chat_model(self):
    """返回 LangChain ChatOpenAI 实例（用于 LangGraph respond 节点）"""
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(
        api_key=self._api_key,
        base_url=self._base_url,
        model=self._model,
        streaming=True,
    )
```

### BF001.3 graph.py 改用 get_chat_model `⬜`

文件：`backend/app/agent/graph.py`

将 create_graph 中第 77-82 行：
```python
chat_model = ChatOpenAI(
    api_key=generator._client.api_key,
    base_url=str(generator._client.base_url),
    model=generator._model,
    streaming=True,
)
```
替换为：
```python
chat_model = generator.get_chat_model()
```

同时删除 `from langchain_openai import ChatOpenAI` import（如无其他引用）。

---

## R007-PATCH01-BF002：共享工具函数提取 `⬜ 待处理`

- 文件：`backend/app/domain/models.py`、`backend/app/rag/context_builder.py`（新建）、`backend/app/agent/graph.py`
- 改动类型：新建 + 修改
- domain: backend
- task_layer: foundation
- depends_on: []
- priority: 4
- risk_tags: []
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - `chunks_to_sources` 只在 domain/models.py 定义
  - `build_numbered_context` 只在 rag/context_builder.py 定义
  - graph.py 和 llm.py 均改为 import 使用
- test_tasks:
  - type: unit
    description: 共享函数与原实现行为一致
    scenarios: ["空 chunks 返回空列表", "正常 chunks 返回正确 SourceReference", "build_numbered_context 格式不变"]
- contract_refs: []
- decision_refs: []
- blocked_files: []

### BF002.1 domain/models.py 新增 chunks_to_sources `⬜`

在文件末尾添加：
```python
def chunks_to_sources(chunks: list[QueryResult]) -> list[SourceReference]:
    """从检索结果构建引用来源列表"""
    return [
        SourceReference(
            chunk_id=c.chunk_id,
            book=c.metadata.book,
            section=c.metadata.section,
            page_start=c.metadata.page_start,
            page_end=c.metadata.page_end,
        )
        for c in chunks
    ]
```
需新增 import：`from app.rag.models import QueryResult`

### BF002.2 新建 rag/context_builder.py `⬜`

```python
"""RAG context 构建工具"""

from app.rag.models import QueryResult


def build_numbered_context(chunks: list[QueryResult]) -> str:
    """构建带编号标记的 context 文本"""
    parts = []
    for i, chunk in enumerate(chunks, 1):
        parts.append(
            f"[{i}] ({chunk.metadata.book} - {chunk.metadata.section}, "
            f"第{chunk.metadata.page_start}-{chunk.metadata.page_end}页)\n"
            f"{chunk.text}"
        )
    return "\n\n".join(parts)
```

### BF002.3 graph.py 改用共享函数 `⬜`

- 删除 `graph.py` 中的 `_build_numbered_context` 函数（第 50-59 行）
- 新增 import：`from app.rag.context_builder import build_numbered_context`
- 将 `_build_numbered_context(chunks)` 调用改为 `build_numbered_context(chunks)`
- 删除 graph.py 中 _retrieve 闭包内的 SourceReference 列表构建（第 92-101 行）
- 新增 import：`from app.domain.models import chunks_to_sources`（已有 SourceReference import）
- 替换为 `sources = chunks_to_sources(chunks) if chunks else []`

### BF002.4 llm.py 改用共享函数 `⬜`

- 删除 `llm.py` generate 方法中的 SourceReference 列表构建（第 66-75 行）
- 新增 import：`from app.domain.models import chunks_to_sources`
- 替换为 `sources = chunks_to_sources(context_chunks)`
- 删除 `llm.py` 中的 `_build_numbered_context` 方法（如果存在）

---

## R007-PATCH01-BB001：conversation_router.py — user_id 隔离 `⬜ 待处理`

- 文件：`backend/app/chat/conversation_router.py`
- 改动类型：修改
- domain: backend
- task_layer: business
- depends_on: ["R007-PATCH01-BF001"]
- priority: 5
- risk_tags: [auth, security]
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - `_load_conversation_by_id` 接收 user_id 参数，不匹配时返回空列表
  - `_load_from_memory_saver` 按 user_id 过滤
  - `_load_from_postgres_saver` 按 user_id 过滤
  - 不同 user_id 看不到彼此对话
  - MemorySaver metadata 无 user_id 时不过滤（兼容）
- test_tasks:
  - type: integration
    description: user_id 隔离验证
    scenarios: ["用户 A 的对话用户 B 无法加载", "conversation_id 属于他人时返回 204", "无 conversation_id 时只返回当前用户最新对话"]
- contract_refs: []
- decision_refs: []
- blocked_files: []

### BB001.1 _load_conversation_by_id 新增 user_id 验证 `⬜`

函数签名改为：
```python
async def _load_conversation_by_id(checkpointer, conversation_id: str, user_id: str):
```

在获取 messages 后增加归属验证：
- PostgresSaver 路径：`aget` 返回的 checkpoint 中检查 configurable 中的 user_id
- MemorySaver 路径：遍历时检查 meta 中 user_id
- 不匹配 → 返回空列表

### BB001.2 _load_from_memory_saver 按 user_id 过滤 `⬜`

遍历 checkpointer.storage 时，从 `(checkpoint, meta, _parent)` 中提取 user_id：
```python
cp_user_id = meta.get("configurable", {}).get("user_id") if meta else None
if user_id and cp_user_id and cp_user_id != user_id:
    continue
```
metadata 无 user_id 时不过滤（兼容历史数据和开发模式）。

### BB001.3 _load_from_postgres_saver 按 user_id 过滤 `⬜`

`alist` 返回的 CheckpointTuple 中，从 `tuple_item.config` 提取 user_id：
```python
tid_user_id = tuple_item.config.get("configurable", {}).get("user_id")
if user_id and tid_user_id and tid_user_id != user_id:
    continue
```

### BB001.4 路由函数传入 user_id `⬜`

`get_current_conversation` 中将 `user.user_id` 传给 `_load_conversation_by_id` 和 `_load_latest_conversation`：
```python
if conversation_id:
    messages = await _load_conversation_by_id(checkpointer, conversation_id, user.user_id)
else:
    conversation_id, messages = await _load_latest_conversation(checkpointer, user.user_id)
```

---

## R007-PATCH01-BB002：conversation_router.py — 重复逻辑消除 `⬜ 待处理`

- 文件：`backend/app/chat/conversation_router.py`
- 改动类型：修改
- domain: backend
- task_layer: business
- depends_on: ["R007-PATCH01-BB001"]
- priority: 3
- risk_tags: []
- smoke_required: false
- mode: direct
- status: pending
- acceptance_criteria:
  - `_extract_latest_messages` 辅助函数统一 MemorySaver 遍历
  - `_load_conversation_by_id` 和 `_load_from_memory_saver` 共用此函数
- test_tasks:
  - type: unit
    description: 验证提取函数行为不变
    scenarios: ["单 namespace 正常", "多 namespace 取最新", "user_id 过滤生效"]
- contract_refs: []
- decision_refs: []
- blocked_files: []

### BB002.1 提取 _extract_latest_messages 辅助函数 `⬜`

新增模块级函数，统一 MemorySaver 的 checkpoint 遍历逻辑：
```python
def _extract_latest_messages(namespaces: dict, user_id: str | None = None) -> list:
    """从 MemorySaver namespaces 提取最新 messages"""
```
逻辑：遍历 namespaces → checkpoints → 按 ts 比较 → user_id 过滤（可选）

### BB002.2 _load_conversation_by_id 改用辅助函数 `⬜`

MemorySaver 分支改为：
```python
if hasattr(checkpointer, "storage"):
    if conversation_id not in checkpointer.storage:
        return []
    return _extract_latest_messages(
        {conversation_id: checkpointer.storage[conversation_id]}, user_id
    )
```

### BB002.3 _load_from_memory_saver 改用辅助函数 `⬜`

替换当前手写遍历为：
```python
return _extract_latest_messages(checkpointer.storage, user_id)
```

---

## R007-PATCH01-BB003：后端死代码清理 `⬜ 待处理`

- 文件：`backend/app/chat/service.py`、`backend/app/agent/nodes.py`、`backend/tests/test_chat_service_stream.py`、`backend/tests/test_agent_nodes.py`
- 改动类型：修改 + 删除
- domain: backend
- task_layer: business
- depends_on: ["R007-PATCH01-BF002"]
- priority: 3
- risk_tags: []
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - `service.py` 中无 `stream_chat` 方法
  - `nodes.py` 中无 `retrieve_node` 和 `respond_node` 函数
  - `test_chat_service_stream.py` 已删除
  - `test_agent_nodes.py` 中无 `respond_node` 引用
  - 现有测试通过
- test_tasks:
  - type: unit
    description: 删除后编译和测试通过
    scenarios: ["pytest tests/ 全部通过", "无 import 错误"]
- contract_refs: []
- decision_refs: []
- blocked_files: []

### BB003.1 删除 ChatService.stream_chat `⬜`

删除 `service.py` 中 `stream_chat` 方法（约第 62-127 行）。

### BB003.2 删除 nodes.py 空壳函数 `⬜`

删除 `nodes.py` 中 `retrieve_node`（第 36-38 行）和 `respond_node`（第 46-48 行）。
保留 `classify_node`、`refuse_node`、`_REFUSE_MESSAGE`。
更新文件顶部 docstring。

### BB003.3 删除 test_chat_service_stream.py `⬜`

整文件删除 `backend/tests/test_chat_service_stream.py`。

### BB003.4 修正 test_agent_nodes.py `⬜`

删除 `respond_node` 的 import 和相关测试类（如有）。
保留 `classify_node`、`refuse_node`、`_REFUSE_MESSAGE` 的测试。

### BB003.5 修正 test_router_auth_integration.py `⬜`

删除或修正其中 `mock_chat_service.stream_chat` 的 mock（如有）。

---

## R007-PATCH01-FB001：前端死代码清理 `⬜ 待处理`

- 文件：`frontend/src/chat/use-chat-storage.ts`、`frontend/src/chat/controller.ts`、`frontend/src/chat/use-conversation.ts`、`frontend/src/__tests__/chat/use-chat-storage.test.ts`、`frontend/src/__tests__/chat/use-conversation.test.ts`、`frontend/src/__tests__/components/chat-ui.test.tsx`
- 改动类型：删除 + 修改
- domain: ui
- task_layer: business
- depends_on: []
- priority: 4
- risk_tags: []
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - `use-chat-storage.ts` 文件不存在
  - `use-chat-storage.test.ts` 文件不存在
  - controller.ts 中无 `saveMessages` 引用
  - controller.ts 中 `updateMsg` 不含 `terminalStatus` 参数
  - use-conversation.ts 不导出 `conversationId` state
  - 前端构建通过
- test_tasks:
  - type: unit
    description: 删除后构建和测试通过
    scenarios: ["npm run build 成功", "无 import 错误"]
- contract_refs: []
- decision_refs: []
- blocked_files: []

### FB001.1 删除 use-chat-storage.ts `⬜`

整文件删除 `frontend/src/chat/use-chat-storage.ts`。

### FB001.2 controller.ts 移除 saveMessages `⬜`

- 删除 `import { saveMessages } from './use-chat-storage'`
- 简化 `updateMsg`：移除 `terminalStatus` 参数和 `if (terminalStatus) { saveMessages(next) }` 分支
- 所有 `updateMsg` 调用处移除第三个参数（`'error'`、`'stopped'`）

改动前：
```typescript
const updateMsg = useCallback(
  (id: string, patch: Partial<Message>, terminalStatus?: MessageStatus) => {
    setMessages((prev) => {
      const next = prev.map((m) => (m.id === id ? { ...m, ...patch } : m));
      if (terminalStatus) { saveMessages(next); }
      return next;
    });
  }, [],
);
```
改动后：
```typescript
const updateMsg = useCallback(
  (id: string, patch: Partial<Message>) => {
    setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, ...patch } : m)));
  }, [],
);
```

需同步修改的调用点：
- `updateMsg(aiMsgId, { status: 'error', error }, 'error')` → `updateMsg(aiMsgId, { status: 'error', error })`
- `updateMsg(aiMsgId, { status: 'stopped' }, 'stopped')` → `updateMsg(aiMsgId, { status: 'stopped' })`

### FB001.3 use-conversation.ts 移除冗余 state `⬜`

- 删除 `useState<string | null>(loadConversationId)` 行
- 删除 `setConversationId(...)` 调用
- 返回值只保留 `{ loadConversation }`

### FB001.4 删除 use-chat-storage.test.ts `⬜`

整文件删除。

### FB001.5 修正 use-conversation.test.ts `⬜`

- 删除 `vi.mock('@/chat/use-chat-storage', ...)` mock
- 删除 `import { loadMessages } from ...` 引用
- 修正 `simulateLoadConversation` 中 catch 块不再返回 localStorage 降级

### FB001.6 修正 chat-ui.test.tsx `⬜`

- 删除 `vi.mock('@/chat/use-chat-storage', ...)` mock
- 删除或重写 `FB002: saveMessages call verification` 测试块

---

## R007-PATCH01-FF001：architecture.md — 目录修正 `⬜ 待处理`

- 文件：`.dev-flow/architecture.md`
- 改动类型：修改
- domain: docs
- task_layer: foundation
- depends_on: []
- priority: 2
- risk_tags: []
- smoke_required: false
- mode: direct
- status: pending
- acceptance_criteria:
  - `services/frontend/` 替换为 `frontend/`
  - `services/backend/` 替换为 `backend/`
  - FORBID-5 补充说明：localStorage 消息缓存已移除
- test_tasks: []
- contract_refs: []
- decision_refs: []
- blocked_files: []

### FF001.1 修正 Monorepo 路径描述 `⬜`

全文替换：
- `services/frontend/` → `frontend/`
- `services/backend/` → `backend/`

涉及行：第 30 行（关键决策）、第 53 行（不变量）

### FF001.2 补充 FORBID-5 说明 `⬜`

第 72 行 "不做前端 LLM 回答缓存" 后补充：`（R007-PATCH01 已移除 localStorage 消息缓存）`
