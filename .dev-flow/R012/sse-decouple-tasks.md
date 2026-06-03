---
version: "2.0"
type: tasks
topic: sse-decouple
requirement_cycle: R012
workflow:
  evaluate_provider: local
  mode: auto
status: archived
---

# SSE 断连恢复 — 任务清单

核心改动：后端解耦 graph 执行到后台任务 + SSE 重连端点 + 停止端点。前端移除轮询，改用 SSE 重连。

---

## 执行顺序

1. ✅ R012-BB001 — stream_router.py 解耦 graph 执行到后台任务（无依赖）
2. ✅ R012-BB002 — 新增 SSE 重连端点 GET /resume（依赖 BB001）
3. ✅ R012-BB003 — 新增停止端点 POST /chat/stop（依赖 BB001）
4. ✅ R012-FB001 — 前端 SSE 重连 + 移除轮询（依赖 BB001 + BB002）
5. ✅ R012-FB002 — 前端停止按钮适配（依赖 BB003）
6. ⬜ 最后 — E2E 测试验证

---

## R012-BB001：stream_router.py — 解耦 graph 执行到后台任务 `✅ 已完成`

- 文件：`backend/app/chat/stream_router.py`
- 改动类型：修改
- domain: backend
- task_layer: business
- depends_on: []
- priority: 5
- risk_tags: [network, first_use]
- smoke_required: true
- mode: direct
- status: completed
- acceptance_criteria:
  - graph.astream() 在 asyncio.create_task 后台任务中执行
  - SSE generator 从 asyncio.Queue 读取事件
  - 客户端断开后 graph 继续运行直到完成
  - 断连后 update_message_stats 正常执行
  - 断连后新对话标题正常生成
  - 5 分钟超时保护生效
  - _active_graphs 注册表正确维护
  - 正常 SSE 流式推送行为不变
- test_tasks:
  - type: unit
    description: _run_graph 正常完成
    scenarios: ["DONE sentinel 入队", "stats 更新", "标题生成", "注册表清理"]
  - type: unit
    description: _run_graph 异常
    scenarios: ["ERROR sentinel 入队", "stats 不更新", "注册表清理"]
  - type: unit
    description: _run_graph 被取消
    scenarios: ["cancel_event.set() → break", "stats 不更新", "注册表清理"]
  - type: unit
    description: _run_graph 超时
    scenarios: ["5 分钟超时 → 任务结束", "注册表清理"]
- contract_refs: []
- decision_refs: []
- blocked_files: []

### BB001.1 定义数据结构和注册表 `⬜`

```python
from dataclasses import dataclass

@dataclass
class GraphTaskInfo:
    queue: asyncio.Queue
    cancel_event: asyncio.Event
    task: asyncio.Task

_GRAPH_DONE = object()
_GRAPH_ERROR = object()

_active_graphs: dict[str, GraphTaskInfo] = {}
```

### BB001.2 实现 _run_graph 后台任务函数 `⬜`

```python
async def _run_graph(graph, input_state, config, queue, cancel_event,
                     db, conversation_id, user, question, is_new, app_state):
    """后台任务：迭代 graph.astream()，put 事件到 queue"""
    try:
        async with asyncio.timeout(300):
            async for event in graph.astream(input_state, config=config, stream_mode=["updates", "messages"]):
                if cancel_event.is_set():
                    break
                await queue.put(event)
    except TimeoutError:
        logger.warning(...)
    except Exception as e:
        await queue.put(_GRAPH_ERROR)
        return
    else:
        await queue.put(_GRAPH_DONE)

    # 完成后收尾（仅非取消）
    if not cancel_event.is_set():
        try: await update_stats(...); await db.commit()
        except: ...
        if is_new:
            try: title = await generate_title(...); ...
            except: ...
    finally:
        _active_graphs.pop(conversation_id, None)
```

### BB001.3 改写 stream_chat endpoint `⬜`

```python
@router.post("/chat/stream")
async def stream_chat(...):
    ...  # 校验 + 创建对话（不变）

    queue = asyncio.Queue()
    cancel_event = asyncio.Event()
    task_info = GraphTaskInfo(queue=queue, cancel_event=cancel_event, task=None)
    _active_graphs[conversation_id] = task_info

    task = asyncio.create_task(_run_graph(...))
    task_info.task = task

    async def event_generator():
        yield _sse_frame("init", ...)
        while True:
            if await http_request.is_disconnected(): return
            try: event = await asyncio.wait_for(queue.get(), timeout=5.0)
            except asyncio.TimeoutError: continue
            if event is _GRAPH_DONE: yield "event: done\ndata: null\n\n"; return
            if event is _GRAPH_ERROR: yield _sse_frame("error", ...); return
            async for frame in _map_event_to_sse(event, http_request):
                yield frame

    return StreamingResponse(event_generator(), ...)
```

### BB001.4 补充单元测试 `⬜`

文件：`backend/tests/test_stream_router_graph.py`

---

## R012-BB002：新增 SSE 重连端点 `✅ 已完成`

- 文件：`backend/app/chat/stream_router.py`
- 改动类型：修改
- domain: backend
- task_layer: business
- depends_on: [R012-BB001]
- priority: 4
- risk_tags: [network]
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - GET /chat/stream/resume?conversation_id=xxx 可用
  - 后台任务运行中 → 返回 SSE 流（剩余事件）
  - 后台任务已完成 → 返回 JSON（完整消息）
  - 后台任务不存在且无消息 → 返回 204
  - 归属校验（非本人对话 → 404）
- test_tasks:
  - type: integration
    description: 重连端点集成测试
    scenarios: ["任务运行中重连", "任务已完成返回 JSON", "无对话返回 404"]
- contract_refs: []
- decision_refs: []
- blocked_files: []

### BB002.1 实现 resume_stream 端点 `⬜`

```python
@router.get("/chat/stream/resume")
async def resume_stream(
    conversation_id: str = Query(...),
    http_request: Request = None,
    checkpointer=Depends(get_checkpointer),
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    # 归属校验
    conv = await ConversationRepo.get_by_id(db, conversation_id, user.user_id)
    if not conv: return 404

    task_info = _active_graphs.get(conversation_id)
    if task_info is None:
        # 已完成 → 返回 checkpoint 消息 JSON
        messages = await _load_conversation_by_id(...)
        if not messages: return 204
        return JSONResponse({conversation_id, messages})

    # 仍在运行 → SSE 流
    async def resume_generator():
        # 同 event_generator 逻辑，从 task_info.queue 读取
        ...
    return StreamingResponse(resume_generator(), ...)
```

---

## R012-BB003：新增停止端点 `⬜ 待处理`

- 文件：`backend/app/chat/stream_router.py`, `backend/app/chat/schemas.py`
- 改动类型：修改
- domain: backend
- task_layer: business
- depends_on: [R012-BB001]
- priority: 4
- risk_tags: [network]
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - POST /chat/stop {conversation_id} 设置 cancel_event
  - 后台任务在下一个事件边界停止
  - stats 不更新（用户主动取消）
  - 注册表清理
- test_tasks:
  - type: unit
    description: 停止信号测试
    scenarios: ["cancel_event 设置后后台任务停止", "注册表清理"]
- contract_refs: []
- decision_refs: []
- blocked_files: []

### BB003.1 新增 StopRequest schema `⬜`

```python
# schemas.py
class StopRequest(BaseModel):
    conversation_id: str
```

### BB003.2 实现 stop_chat 端点 `⬜`

```python
@router.post("/chat/stop")
async def stop_chat(body: StopRequest, user: UserContext = Depends(get_current_user)):
    task_info = _active_graphs.get(body.conversation_id)
    if task_info:
        task_info.cancel_event.set()
    return JSONResponse({"status": "ok"})
```

---

## R012-FB001：前端 SSE 重连 + 移除轮询 `✅ 已完成`

- 文件：`frontend/src/chat/controller.ts`, `frontend/src/chat/use-chat-stream.ts`
- 改动类型：修改
- domain: ui
- task_layer: business
- depends_on: [R012-BB001, R012-BB002]
- priority: 4
- risk_tags: []
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - 刷新后检测到未完成 AI 回复 → 发起 GET /chat/stream/resume
  - resume 返回 SSE → 流式显示 token（与正常对话一致）
  - resume 返回 JSON → 直接显示完整回复
  - resume 返回 404/204 → 显示中断提示
  - 移除轮询 useEffect、POLLING_PLACEHOLDER_PREFIX、needsPollingPlaceholder、withPollingPlaceholder
  - 保留占位消息机制（加载时显示"正在检索…"，resume 成功后替换）
- test_tasks:
  - type: integration
    description: E2E 刷新后 SSE 重连
    scenarios: ["发消息 → 刷新 → SSE 重连 → 流式接收", "发消息 → 等完成 → 刷新 → 直接显示"]
- contract_refs: []
- decision_refs: []
- blocked_files: []

### FB001.1 use-chat-stream.ts 新增 resumeStream 函数 `⬜`

```typescript
// 新增 resumeStream 函数，复用 chatStreamFetch 的 SSE 解析逻辑
// 但用 GET 而非 POST，不传 question
export async function resumeStream(
  conversationId: string,
  callbacks: StreamCallbacks,
): Promise<void> {
  const response = await fetchWithAuth(`/chat/stream/resume?conversation_id=${encodeURIComponent(conversationId)}`);
  if (response.headers.get('content-type')?.includes('text/event-stream')) {
    // SSE 流 → 复用 SSE 解析
    await parseSSEStream(response.body, callbacks);
  } else {
    // JSON 响应 → 直接返回完整消息
    const data = await response.json();
    callbacks.onMessagesReady?.(data.messages);
  }
}
```

### FB001.2 controller.ts 移除轮询，新增 SSE 重连 useEffect `⬜`

```typescript
// 替换轮询 useEffect 为 SSE 重连
useEffect(() => {
    if (!mounted || !activeId || isStreaming) return;
    const currentMessages = messagesRef.current;
    if (currentMessages.length === 0) return;

    const lastMsg = currentMessages[currentMessages.length - 1];
    if (lastMsg.role !== 'ai' || !['generating', 'retrieving'].includes(lastMsg.status)) return;
    if (Date.now() - lastMsg.timestamp > 180_000) return;

    // SSE 重连
    resumeStream(activeId, {
        onStatus: (stage) => updateMsg(placeholderId, { status: stage }),
        onToken: (token) => updateMsg(placeholderId, { content: messagesRef.current.find(m => m.id === placeholderId)?.content + token }),
        onDone: () => updateMsg(placeholderId, { status: 'done' }),
        onError: (error) => updateMsg(placeholderId, { status: 'error', error }),
        onMessagesReady: (messages) => setMessages(messages),
    });
}, [mounted, isStreaming, activeId]);
```

### FB001.3 移除轮询相关代码 `⬜`

移除：
- `POLLING_PLACEHOLDER_PREFIX` 常量
- `needsPollingPlaceholder()` 函数
- `withPollingPlaceholder()` 函数
- `loadWithPlaceholder()` 函数
- 轮询 useEffect
- init useEffect 和 switchHandler 中的 `loadWithPlaceholder` 调用

保留：
- 占位消息的创建（但改用不同方式：不靠 POLLING_PREFIX 识别）

---

## R012-FB002：前端停止按钮适配 `✅ 已完成`

- 文件：`frontend/src/chat/use-chat-stream.ts`
- 改动类型：修改
- domain: ui
- task_layer: business
- depends_on: [R012-BB003]
- priority: 3
- risk_tags: []
- smoke_required: false
- mode: direct
- status: pending
- acceptance_criteria:
  - stop() 调用前先发 POST /chat/stop
  - POST /chat/stop 失败不阻断 abort
- test_tasks:
  - type: unit
    description: stop() 调用 POST /chat/stop 后 abort
    scenarios: ["正常停止：先 POST 后 abort", "POST 失败仍执行 abort"]
- contract_refs: []
- decision_refs: []
- blocked_files: []

### FB002.1 stop() 增加 POST /chat/stop 调用 `⬜`

```typescript
const stop = useCallback(async () => {
    if (conversationIdRef.current) {
        try {
            await fetchWithAuth('/chat/stop', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ conversation_id: conversationIdRef.current }),
            });
        } catch { /* 失败不阻断 */ }
    }
    abortControllerRef.current?.abort();
}, []);
```
