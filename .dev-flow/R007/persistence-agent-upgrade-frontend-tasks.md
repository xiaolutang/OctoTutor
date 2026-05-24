---
version: "2.0"
type: tasks
topic: persistence-agent-upgrade
requirement_cycle: R007
workflow:
  evaluate_provider: local
  mode: auto
status: archived
---

# Chat — 前端 任务清单

基于设计报告 `analysis/2026-05-22--R007-persistence-agent-upgrade-frontend.md` v4，拆解前端实现任务。

**全局约束**：
- Next.js 16 + React 19，App Router
- 认证：@xlfoundry/auth-sdk-web 的 AuthService
- 现有 parse-sse.ts 不修改（通用解析器，不关心 event type）
- 现有 use-chat-storage.ts 保留作为降级方案
- 现有 chat-input.tsx、source-card.tsx 不修改
- 暂不实现：多对话切换、离线支持、编辑已发送消息、检索降级提示
- saveMessages 策略：终态全部移除，仅 handleStop 保留

---

## 执行顺序

1. ✅ R007-FF002 — 鉴权架构优化（已完成）
2. ✅ R007-FF001 — thinking 事件类型 + 流式 hook（已完成）
3. ✅ R007-FB001 — 思考过程 UI（已完成）
4. ⬜ R007-BB003 — SSE init 事件 + 204 响应修复（后端，无前端依赖）
5. ⬜ R007-FF003 — conversation_id 回传 + useChatController + ChatUI 瘦身（依赖 BB003）

---

## R007-FF002：api-client + auth-context + SharedTokenManager + 删除 route-guard + 删除 api.ts — 鉴权架构优化 `✅ 已完成`

- 文件：`frontend/src/lib/api-client.ts`、`frontend/src/contexts/auth-context.tsx`、`frontend/src/contexts/shared-token-manager.ts`(新建)、`frontend/src/components/route-guard.tsx`(删除)、`frontend/src/chat/api.ts`(删除)、`frontend/src/app/chat/page.tsx`
- domain: ui
- task_layer: foundation
- depends_on: []
- status: completed
- acceptance_criteria:
  - api-client.ts 导出 `registerAuthHandlers({getToken, onUnauthorized})`
  - api-client.ts 401 时调用 `onUnauthorized` 获取新 token 并重试一次
  - SharedTokenManager 并发调用 refreshTokens() 只触发一次网络请求
  - auth-context.tsx 通过 `registerAuthHandlers` 注册
  - auth-context.tsx onUnauthorized catch 块中不含 `service.login()` 调用
  - auth-context.tsx 初始化完成 + 未认证 + 不在白名单 → 自动调用 login()
  - `route-guard.tsx` 已删除
  - `chat/api.ts` 已删除

---

## R007-FF001：types.ts + use-chat-stream.ts — thinking 事件 + conversationId `✅ 已完成`

- 文件：`frontend/src/chat/types.ts`、`frontend/src/chat/use-chat-stream.ts`
- domain: ui
- task_layer: foundation
- depends_on: [R007-FF002]
- status: completed
- acceptance_criteria:
  - `ThinkingStep`、`ApiMessage`、`ConversationResponse` 接口定义
  - `SSECallbacks` 含 `onThinking`
  - `Message` 含 `thinkingSteps`
  - `chatStreamFetch` body 含 `conversation_id`
  - switch 含 `thinking` case

---

## R007-FB001：thinking-process.tsx + message-bubble.tsx — 思考过程 UI `✅ 已完成`

- 文件：`frontend/src/components/thinking-process.tsx`(新建)、`frontend/src/components/message-bubble.tsx`
- domain: ui
- task_layer: ui
- depends_on: [R007-FF001]
- status: completed
- acceptance_criteria:
  - ThinkingProcess 默认折叠，点击展开/折叠
  - 流式中标题显示"思考中..."，完成后显示"思考过程（N 步）"
  - message-bubble 有 thinkingSteps 时渲染 ThinkingProcess

---

## R007-BB003：SSE init 事件 + conversation_router 204 修复 — 后端配合 `⬜ 待处理`

- 文件：`backend/app/chat/stream_router.py`(修改)、`backend/app/chat/conversation_router.py`(修改)
- 改动类型：修改
- domain: backend
- task_layer: foundation
- depends_on: []
- priority: 4
- risk_tags: [network]
- smoke_required: true
- mode: direct
- acceptance_criteria:
  - SSE 流第一个事件为 `event: init\ndata: {"conversation_id":"xxx"}\n\n`
  - `conversation_id` 为后端生成或接收到的 UUID
  - `conversation_router.py` 204 响应使用 `Response(status_code=204)` 无 body
  - 不影响现有 SSE 事件顺序（init → thinking → status → sources → token → done）
- test_tasks:
  - type: unit
    description: SSE init 事件输出
    scenarios: [调用 stream_chat → 第一个 yield 为 event: init 含 conversation_id]
  - type: unit
    description: 204 响应无 body
    scenarios: [新用户 → GET /conversations/current → 204 无 body 无 Content-Length]
- contract_refs: [.dev-flow/R007/analysis/2026-05-22--R007-persistence-agent-upgrade-frontend.md]
- decision_refs: [DEC-conversation-id-sse-init]

### BB003.1 stream_router.py — SSE init 事件 `⬜`

在 `event_generator()` 的 try 块最开头、遍历 graph 之前，yield init 事件：

```python
async def event_generator():
    try:
        # 首个事件：回传 conversation_id 给前端
        yield _sse_frame("init", {"conversation_id": conversation_id})

        async for node_name, node_output in _iter_graph_updates(...):
            ...
```

### BB003.2 conversation_router.py — 204 响应修复 `⬜`

```python
# 修改前
return JSONResponse(status_code=204, content=None)

# 修改后
from starlette.responses import Response
return Response(status_code=204)
```

---

## R007-FF003：conversation_id 回传 + useChatController + ChatUI 瘦身 — 统一聊天控制器 `⬜ 待处理`

- 文件：`frontend/src/chat/controller.ts`(新建)、`frontend/src/chat/use-conversation.ts`(修改)、`frontend/src/chat/use-chat-stream.ts`(修改)、`frontend/src/chat/types.ts`(修改)、`frontend/src/components/chat-ui.tsx`(重构)
- 改动类型：新建 + 修改 + 重构
- domain: ui
- task_layer: ui
- depends_on: [R007-BB003]
- priority: 5
- risk_tags: [network]
- smoke_required: true
- mode: direct
- acceptance_criteria:
  - **conversation_id 管理**：SSE init 事件返回 conversation_id → 前端保存 → 后续发送复用
  - **多轮对话**：退出页面再进入 → 加载历史消息含多轮对话
  - **useChatController**：封装消息列表、conversationId、input、mounted、isStreaming 全部状态
  - **ChatUI 瘦身**：不超过 80 行，只负责渲染，所有业务逻辑委托 controller
  - **onError 保留用户消息**：code:'00000' 时保留 userMsg，aiMsg 标记 error + 文本回填输入框
  - **loadConversation 稳定**：useCallback 包裹，useEffect 不重复触发
  - **SSECallbacks 新增 onInit**：init 事件触发 onInit 回调
- test_tasks:
  - type: unit
    description: conversation_id 从 init 事件获取并保存
    scenarios: [mock init 事件 → onInit 设置 conversationId → 第二次 sendMessage body 含此 ID]
  - type: unit
    description: onError 保留用户消息
    scenarios: [触发 00000 错误 → messages 中 userMsg 仍在 → aiMsg.status = 'error' → input 回填]
  - type: unit
    description: loadConversation 引用稳定
    scenarios: [两次调用 useConversation → loadConversation 引用相同 (===)]
  - type: integration
    description: 多轮对话流程
    scenarios: [发送消息 A → init 返回 conv-1 → 发送消息 B body 含 conv-1 → 退出 → 重新加载 → 看到 A+B]
  - type: unit
    description: ChatUI 行数约束
    scenarios: [chat-ui.tsx 总行数 <= 80]
- contract_refs: [.dev-flow/R007/analysis/2026-05-22--R007-persistence-agent-upgrade-frontend.md]
- decision_refs: [DEC-conversation-id-sse-init, DEC-chat-controller, DEC-on-error-keep-user-msg]
- blocked_files: [frontend/src/chat/parse-sse.ts, frontend/src/chat/use-chat-storage.ts, frontend/src/components/chat-input.tsx, frontend/src/components/source-card.tsx]

### FF003.1 types.ts — SSECallbacks 新增 onInit `⬜`

```typescript
export interface SSECallbacks {
  onInit: (conversationId: string) => void;   // 新增
  onStatus: (stage: string, message: string) => void;
  // ... 其余不变
}
```

### FF003.2 use-chat-stream.ts — init 事件处理 `⬜`

switch 新增 init case：

```typescript
case 'init':
  callbacks.onInit((event.data as { conversation_id: string }).conversation_id);
  break;
```

### FF003.3 use-conversation.ts — useCallback 修复 `✅ 已完成`

已在代码中修复：
- `import { useState, useCallback } from 'react'`
- `const loadConversation = useCallback(async () => { ... }, [])`

### FF003.4 controller.ts — 统一聊天控制器 `⬜`

新建 `frontend/src/chat/controller.ts`，从 `chat-ui.tsx` 中提取全部业务逻辑。

职责：
- 管理 messages / input / mounted / isStreaming / conversationId 状态
- 封装 handleSend / handleStop / handleRegenerate / appendAndSend / startSSE
- 初始化时调用 loadConversation()
- SSE 回调处理（onInit / onStatus / onSources / onToken / onThinking / onDone / onError）
- saveMessages 时机控制（仅 handleStop）

接口：

```typescript
interface UseChatControllerReturn {
  // 状态（只读）
  messages: Message[];
  input: string;
  mounted: boolean;
  isStreaming: boolean;
  // 操作
  setInput: (v: string) => void;
  handleSend: () => void;
  handleStop: () => void;
  handleRegenerate: (messageId: string) => void;
}

export function useChatController(): UseChatControllerReturn
```

SSE 回调中 onInit 处理：

```typescript
onInit: (convId: string) => {
  setConversationId(convId);
},
```

onError 处理（保留用户消息）：

```typescript
onError: (error) => {
  if (error.code === '00000') {
    // 保留用户消息，仅标记 AI 为 error + 回填输入框
    updateMsgAndSave(aiMsgId, { status: 'error', error });
    setInput(question);
  } else {
    updateMsgAndSave(aiMsgId, { status: 'error', error }, 'error');
  }
},
```

### FF003.5 chat-ui.tsx — 瘦身为纯渲染组件 `⬜`

重构后 chat-ui.tsx 只保留渲染逻辑：

```typescript
export function ChatUI() {
  const {
    messages, input, mounted, isStreaming,
    setInput, handleSend, handleStop, handleRegenerate,
  } = useChatController();

  if (!mounted) {
    return <div className="...">加载中...</div>;
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 overflow-y-auto px-4 py-6">
        {messages.length === 0 ? (
          <div className="..."><p>输入问题开始对话</p></div>
        ) : (
          messages.map((msg) => (
            <MessageBubble key={msg.id} message={msg} isStreaming={isStreaming} onRegenerate={handleRegenerate} />
          ))
        )}
      </div>
      <ChatInput value={input} onChange={setInput} onSend={handleSend} onStop={handleStop} isStreaming={isStreaming} disabled={isStreaming} />
    </div>
  );
}
```
