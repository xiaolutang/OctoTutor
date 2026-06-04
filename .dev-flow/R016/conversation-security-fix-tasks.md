---
version: "1.0"
type: tasks
topic: conversation-security-fix
requirement_cycle: R016
workflow:
  evaluate_provider: local
  mode: auto
status: planned
---

# 对话安全与初始化修复 — 任务清单

基于 analysis + design 修复 3 个 bug：后端数据泄漏、前端 catch 块、前端错误 UI。

全局约束：
- 后端改动限于 `conversation_router.py` 和 `conversation_utils.py`，不动 stream_router.py
- 前端改动限于 `conversation-context.tsx` 和 `chat-ui.tsx`
- 先修后端安全漏洞，再修前端

---

## 执行顺序

1. ⬜ R016-BB001 — 后端 checkpoint user_id 过滤修复（无依赖）
2. ⬜ R016-FF001 — 前端 conversation-context catch 块容错（无依赖，可与 BB001 并行）
3. ⬜ R016-FF002 — 前端 chat-ui 错误状态 UI（依赖 FF001）

---

## R016-BB001：checkpoint user_id 归属校验修复 `✅ 已完成`

- 文件：`backend/app/chat/conversation_router.py` + `backend/app/chat/conversation_utils.py`
- 改动类型：修改
- domain: backend
- task_layer: foundation
- depends_on: []
- priority: 5
- risk_tags: [security]
- smoke_required: true
- mode: direct
- status: completed
- acceptance_criteria:
  - `_load_from_postgres_saver` 从 metadata 正确读取 user_id 并过滤，新用户遍历无匹配 checkpoint 时返回 (None, [])
  - `load_conversation_by_id` 从 metadata 正确读取 user_id 做归属校验，非本人对话返回空列表
  - 新用户 GET /api/conversations/current 返回 204
  - 已有对话功能不受影响（回归）
- test_tasks:
  - type: unit
    description: 验证 metadata 中 user_id 的实际 key 结构
    scenarios: ["在 _load_from_postgres_saver 加临时日志打印 tuple_item.metadata 内容，确认 key"]
  - type: integration
    description: 新用户无法获取他人对话
    scenarios: ["新用户 GET /conversations/current 返回 204", "新用户 GET /conversations/current?conversation_id=他人ID 返回 204 或空"]
  - type: integration
    description: 已有用户正常获取自己的对话
    scenarios: ["用户 GET /conversations/current?conversation_id=自己的ID 返回 200 + 消息"]
- contract_refs: []
- decision_refs: []
- blocked_files: ["backend/app/chat/stream_router.py"]

### BB001.1 验证 metadata key `⬜`

在 `_load_from_postgres_saver` 中加临时日志，打印前 3 条 `tuple_item.metadata` 的完整内容，确认 user_id 的实际 key。可能的情况：
- `metadata.get("user_id")` — 扁平结构
- `metadata.get("configurable", {}).get("user_id")` — 嵌套结构（MemorySaver 同款）

确认后删除日志。

### BB001.2 修复 `_load_from_postgres_saver` `⬜`

文件：`backend/app/chat/conversation_router.py:112`

```python
# 旧（BUG）
tid_user_id = tuple_item.config.get("configurable", {}).get("user_id")

# 新 — key 根据 BB001.1 验证结果填写
tid_user_id = tuple_item.metadata.get("user_id")  # 或 metadata.get("configurable", {}).get("user_id")
if tid_user_id and tid_user_id != user_id:
    continue
```

### BB001.3 修复 `load_conversation_by_id` `⬜`

文件：`backend/app/chat/conversation_utils.py:59`

```python
# 旧（BUG）
cp_user_id = tuple_item.config.get("configurable", {}).get("user_id")

# 新 — key 与 BB001.2 一致
cp_user_id = tuple_item.metadata.get("user_id")
```

---

## R016-FF001：conversation-context catch 块容错 `✅ 已完成`

- 文件：`frontend/src/contexts/conversation-context.tsx`
- 改动类型：修改
- domain: ui
- task_layer: foundation
- depends_on: []
- priority: 4
- risk_tags: []
- smoke_required: true
- mode: direct
- status: completed
- acceptance_criteria:
  - fetchConversationList 失败时，catch 块 dispatch INIT_LIST 推进 isInitialized=true
  - 初始化失败后 controller 能正常触发 loadConversation
  - 初始化成功时行为不变
- test_tasks:
  - type: unit
    description: catch 块 dispatch 验证
    scenarios: ["fetchConversationList 抛异常后 state.isInitialized === true"]
- contract_refs: []
- decision_refs: []
- blocked_files: []

### FF001.1 catch 块补 INIT_LIST dispatch `⬜`

文件：`frontend/src/contexts/conversation-context.tsx:88-92`

```typescript
// 旧（BUG）
} catch {
  if (!cancelled) {
    dispatch({ type: 'SET_LOADING', payload: false });
  }
}

// 新 — dispatch INIT_LIST 推进 isInitialized
} catch {
  if (!cancelled) {
    dispatch({ type: 'INIT_LIST', payload: { items: [], cursor: null, hasMore: false } });
    dispatch({ type: 'SET_ACTIVE', payload: null });
  }
}
```

INIT_LIST 已包含 `isLoading: false` + `isInitialized: true`，无需额外 SET_LOADING。

---

## R016-FF002：chat-ui 错误状态 UI `✅ 已完成`

- 文件：`frontend/src/components/chat-ui.tsx`
- 改动类型：修改
- domain: ui
- task_layer: ui
- depends_on: [R016-FF001]
- priority: 3
- risk_tags: []
- smoke_required: false
- mode: direct
- status: completed
- acceptance_criteria:
  - loadConversation 失败时 chat-ui 显示错误提示 + 重试按钮
  - 正常加载和空状态不受影响
- test_tasks:
  - type: unit
    description: 错误状态渲染
    scenarios: ["loadError=true 时显示错误提示和重试按钮"]
- contract_refs: []
- decision_refs: []
- blocked_files: []

### FF002.1 controller 暴露 error 状态 `⬜`

文件：`frontend/src/chat/controller.ts`

在 loadConversation catch 中设置 error 状态，通过 useChatController 暴露 `loadError` 和 `retryLoad`。

逻辑步骤：
1. 新增 state: `loadError: string | null`
2. loadConversation catch 中 `setLoadError("加载失败")`
3. loadConversation 成功时 `setLoadError(null)`
4. 导出 `loadError` 和 `retryLoad`（retryLoad = 重新调用 loadConversation）

### FF002.2 chat-ui 新增 error 分支 `⬜`

文件：`frontend/src/components/chat-ui.tsx:32-38`

在 `!mounted` 和 `loadError` 之间加判断：

```typescript
if (loadError) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 text-muted-foreground">
      <p>{loadError}</p>
      <button onClick={retryLoad} className="...">重试</button>
    </div>
  );
}
```

渲染优先级：`loadError` > `!mounted`（加载中）> 正常渲染
