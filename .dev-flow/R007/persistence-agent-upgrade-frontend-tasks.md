---
version: "1.0"
type: tasks
topic: persistence-agent-upgrade
requirement_cycle: R007
workflow:
  evaluate_provider: local
  mode: auto
status: planned
---

# Chat — 前端 任务清单

基于设计报告 `analysis/2026-05-22--R007-persistence-agent-upgrade-frontend.md`，拆解前端实现任务。

**全局约束**：
- Next.js 16 + React 19，App Router
- 认证：@xlfoundry/auth-sdk-web 的 AuthService
- 现有 parse-sse.ts 不修改（通用解析器，不关心 event type）
- 现有 use-chat-storage.ts 保留作为降级方案
- 现有 chat-input.tsx、source-card.tsx 不修改
- 暂不实现：思考步骤搜索/过滤、Markdown 渲染、离线支持、多对话切换、编辑已发送消息
- saveMessages 策略：终态全部移除，仅 handleStop + onError(00000) 保留
- conversation_id 管理：首次 loadConversation 获取后存 React 状态，传给 sendMessage

---

## 执行顺序

1. ⬜ R007-FF002 — 鉴权架构优化（无后端依赖）
2. ⬜ R007-FF001 — thinking 事件类型 + 流式 hook（依赖 FF002）
3. ⬜ R007-FB001 — 思考过程 UI（依赖 FF001）
4. ⬜ R007-FB002 — 对话加载 + chat-ui 重构（依赖 FF001 + FB001 + FF002）

---

## R007-FF002：api-client + auth-context + route-guard + 删除 api.ts — 鉴权架构优化 `⬜ 待处理`

- 文件：`frontend/src/lib/api-client.ts`(修改)、`frontend/src/contexts/auth-context.tsx`(修改)、`frontend/src/components/route-guard.tsx`(修改)、`frontend/src/chat/api.ts`(删除)
- 改动类型：修改 + 删除
- domain: ui
- task_layer: foundation
- depends_on: []
- priority: 4
- risk_tags: [auth]
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - api-client.ts 不含 `refreshAndGetToken`、`refreshPromise`、`redirectToLogin`
  - api-client.ts 导出 `registerAuthHandlers({getToken, onUnauthorized})`
  - api-client.ts 401 时调用 `onUnauthorized` 获取新 token 并重试一次
  - auth-context.tsx 不含独立 `new TokenManager()`
  - auth-context.tsx 通过 `registerAuthHandlers` 注册 getToken + onUnauthorized
  - auth-context.tsx 不使用 `window.addEventListener('auth:session-expired')`
  - route-guard.tsx 不调用 `login()`，只判断状态
  - `chat/api.ts` 已删除，无其他文件引用 `API_BASE`
  - 应用登录/登出/401 重试流程正常
- test_tasks:
  - type: unit
    description: api-client registerAuthHandlers 机制
    scenarios: [注册后 401 → onUnauthorized 被调用 → 返回新 token → 重试成功]
  - type: unit
    description: auth-context 单一 AuthService 实例
    scenarios: [验证无 new TokenManager 调用]
  - type: unit
    description: route-guard 不触发 login
    scenarios: [未登录时验证 login 未被调用]
- contract_refs: [.dev-flow/R007/analysis/2026-05-22--R007-persistence-agent-upgrade-frontend.md]
- decision_refs: []
- blocked_files: [frontend/src/chat/parse-sse.ts]

### FF002.1 api-client.ts — 职责收敛 `⬜`

1. 删除：`refreshPromise`、`refreshAndGetToken()`、`redirectToLogin()`、`_resetForTesting()` 中 refreshPromise 相关行
2. 将 `registerGetToken` 替换为 `registerAuthHandlers`：

```typescript
type AuthHandlers = {
  getToken: () => Promise<string | null>;
  onUnauthorized: () => Promise<string | null>; // 返回新 token 或 null
};

let authHandlers: AuthHandlers | null = null;

export function registerAuthHandlers(handlers: AuthHandlers): void {
  authHandlers = handlers;
}
```

3. `fetchWithAuth` 中 401 处理改为：

```typescript
// 4. 401 处理：调用 onUnauthorized 获取新 token + 重试
if (response.status === 401 && !headers.has('X-Retry') && authHandlers) {
  const newToken = await authHandlers.onUnauthorized();
  if (newToken) {
    const retryHeaders = new Headers(init?.headers);
    retryHeaders.set('Authorization', `Bearer ${newToken}`);
    retryHeaders.set('X-Retry', 'true');
    if (init?.body && !retryHeaders.has('Content-Type')) {
      retryHeaders.set('Content-Type', 'application/json');
    }
    return fetch(fullURL, { ...init, headers: retryHeaders });
  }
}
```

4. 删除第 75-77 行的 `redirectToLogin()` 调用（401 重试失败后直接返回 response）
5. 更新文件头注释

### FF002.2 auth-context.tsx — 统一 AuthService `⬜`

1. 删除独立的 `new TokenManager(...)` 实例
2. 统一使用 `AuthService` 实例管理 token
3. 将 `registerGetToken(() => tm.ensureValidToken())` 改为 `registerAuthHandlers`：

```typescript
registerAuthHandlers({
  getToken: async () => {
    try {
      return await authService.getAccessToken();
    } catch {
      return null;
    }
  },
  onUnauthorized: async () => {
    try {
      await authService.refreshToken();
      return await authService.getAccessToken();
    } catch {
      // 刷新失败 → 跳转登录
      authService.login();
      return null;
    }
  },
});
```

4. 删除 `window.addEventListener('auth:session-expired', ...)` 事件监听
5. 401 刷新失败跳转统一由 `onUnauthorized` 回调处理

### FF002.3 route-guard.tsx — 只判断状态不触发跳转 `⬜`

修改为：

```typescript
'use client'

import { type ReactNode } from 'react'
import { useAuth } from '@/contexts/auth-context'

export function RouteGuard({ children }: { children: ReactNode }) {
  const { isInitialized, isAuthenticated } = useAuth()

  if (!isInitialized) {
    return (
      <div className="flex min-h-[calc(100vh-3.5rem)] items-center justify-center">
        <span className="text-sm text-muted-foreground">加载中...</span>
      </div>
    )
  }

  if (!isAuthenticated) {
    return null  // auth-context 统一管理跳转
  }

  return <>{children}</>
}
```

关键改动：删除 `useEffect` + `login()` 调用，删除 `login` 从 `useAuth()` 的解构。

### FF002.4 删除 chat/api.ts `⬜`

1. 删除 `frontend/src/chat/api.ts`
2. 全局搜索确认无其他文件 `import from './api'` 或 `import from '@/chat/api'`

---

## R007-FF001：types.ts + use-chat-stream.ts — thinking 事件 + conversationId `⬜ 待处理`

- 文件：`frontend/src/chat/types.ts`(修改)、`frontend/src/chat/use-chat-stream.ts`(修改)
- 改动类型：修改
- domain: ui
- task_layer: foundation
- depends_on: [R007-FF002]
- priority: 4
- risk_tags: []
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - `ThinkingStep` 接口包含 `text: string` + `index: number`
  - `ApiMessage` 接口包含 id/role/content/status/sources/thinking_steps/created_at
  - `ConversationResponse` 接口包含 conversation_id + messages
  - `SSECallbacks` 新增 `onThinking: (step: ThinkingStep) => void`
  - `Message` 新增 `thinkingSteps?: ThinkingStep[]`
  - `chatStreamFetch` body 包含 `conversation_id`
  - `sendMessage` 接受第三参数 `conversationId?: string`
  - switch 新增 `thinking` case 调用 `onThinking`
- test_tasks:
  - type: unit
    description: chatStreamFetch thinking 事件处理
    scenarios: [mock thinking SSE 事件 → onThinking 被调用，参数含 text + index]
  - type: unit
    description: conversationId 传递
    scenarios: [sendMessage("q", cb, "conv-123") → fetch body 含 conversation_id: "conv-123"]
- contract_refs: []
- decision_refs: []
- blocked_files: [frontend/src/chat/parse-sse.ts]

### FF001.1 types.ts — 新增类型 + 扩展现有接口 `⬜`

在 `SourceReference` 之后新增：

```typescript
/** 思考步骤 — SSE thinking 事件携带 */
export interface ThinkingStep {
  text: string;
  index: number;
}

/** 后端消息格式（role 为 human/ai） */
export interface ApiMessage {
  id: string;
  role: 'human' | 'ai';
  content: string;
  status: 'completed' | 'stopped' | 'error';
  sources?: SourceReference[];
  thinking_steps?: ThinkingStep[];
  created_at: string;
}

/** GET /api/conversations/current 响应体 */
export interface ConversationResponse {
  conversation_id: string;
  messages: ApiMessage[];
}
```

修改 `SSECallbacks` 新增 onThinking：

```typescript
export interface SSECallbacks {
  onStatus: (stage: string, message: string) => void;
  onSources: (sources: SourceReference[]) => void;
  onToken: (token: string) => void;
  onThinking: (step: ThinkingStep) => void;
  onDone: () => void;
  onError: (error: { code: string; message: string; action: string }) => void;
}
```

修改 `Message` 新增 thinkingSteps：

```typescript
export interface Message {
  id: string;
  role: 'user' | 'ai';
  content: string;
  status: MessageStatus;
  sources?: SourceReference[];
  thinkingSteps?: ThinkingStep[];
  error?: { code: string; message: string; action: string };
  timestamp: number;
}
```

### FF001.2 use-chat-stream.ts — conversationId + thinking case `⬜`

1. `chatStreamFetch` 新增 `conversationId` 参数，body 加入 `conversation_id`：

```typescript
export function chatStreamFetch(
  question: string,
  callbacks: SSECallbacks,
  abortController: AbortController,
  onSetStreaming: (v: boolean) => void,
  conversationId?: string,  // 新增
) {
  // ...
  body: JSON.stringify({ question, top_k: 10, conversation_id: conversationId ?? null }),
```

2. switch 新增 thinking case：

```typescript
case 'thinking':
  callbacks.onThinking(event.data as ThinkingStep);
  break;
```

3. `useChatStream` hook 的 `sendMessage` 新增第三参数：

```typescript
interface UseChatStreamReturn {
  sendMessage: (question: string, callbacks: SSECallbacks, conversationId?: string) => void;
  stop: () => void;
  isStreaming: boolean;
}

// sendMessage 中传递 conversationId
const sendMessage = useCallback(
  (question: string, callbacks: SSECallbacks, conversationId?: string) => {
    const abortController = new AbortController();
    abortRef.current = abortController;
    setIsStreaming(true);
    chatStreamFetch(question, callbacks, abortController, setIsStreaming, conversationId);
  },
  [],
);
```

4. 更新 import 添加 `ThinkingStep`

---

## R007-FB001：thinking-process.tsx + message-bubble.tsx — 思考过程 UI `⬜ 待处理`

- 文件：`frontend/src/components/thinking-process.tsx`(新建)、`frontend/src/components/message-bubble.tsx`(修改)
- 改动类型：新建 + 修改
- domain: ui
- task_layer: ui
- depends_on: [R007-FF001]
- priority: 3
- risk_tags: []
- smoke_required: false
- mode: direct
- status: pending
- acceptance_criteria:
  - ThinkingProcess 组件渲染思考步骤列表
  - 默认折叠，点击展开/折叠
  - 流式中标题显示"思考中..."，完成后显示"思考过程（N 步）"
  - message-bubble 中 AI 消息有 thinkingSteps 时渲染 ThinkingProcess，无则不渲染
- test_tasks:
  - type: unit
    description: ThinkingProcess 折叠/展开交互
    scenarios: [点击标题 → 列表显示，再点击 → 列表隐藏]
  - type: unit
    description: message-bubble 条件渲染
    scenarios: [有 thinkingSteps → 渲染 ThinkingProcess, 无 → 不渲染]
- contract_refs: []
- decision_refs: []
- blocked_files: []

### FB001.1 thinking-process.tsx — 可折叠思考过程组件 `⬜`

新建组件，props：

```typescript
interface ThinkingProcessProps {
  steps: ThinkingStep[];
  isStreaming?: boolean;  // true 时标题显示"思考中..."
}
```

UI 结构：
- 外层容器：`border rounded-lg` 背景
- 标题栏：点击切换折叠，左侧 ChevronDown/ChevronRight 图标 + 文本
  - isStreaming: "思考中..." + 旋转动画
  - !isStreaming: "思考过程（N 步）"
- 内容区：折叠时隐藏，展开时显示步骤列表
  - 每步：序号圆圈 + 文本描述
- 默认状态：折叠

### FB001.2 message-bubble.tsx — 集成 ThinkingProcess `⬜`

1. 新增 import `ThinkingProcess` 和 `ThinkingStep`
2. 在消息气泡中，如果 `message.thinkingSteps` 非空，渲染 `<ThinkingProcess steps={message.thinkingSteps} isStreaming={message.status === 'generating'} />`
3. 位置：在消息正文（content）上方，sources 下方（或按设计调整）

---

## R007-FB002：use-conversation.ts + chat-ui.tsx — 对话加载 + 重构 `⬜ 待处理`

- 文件：`frontend/src/chat/use-conversation.ts`(新建)、`frontend/src/components/chat-ui.tsx`(修改)
- 改动类型：新建 + 修改
- domain: ui
- task_layer: ui
- depends_on: [R007-FF001, R007-FB001, R007-FF002]
- priority: 5
- risk_tags: [network]
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - 打开页面 → 调用 GET /api/conversations/current → 显示历史消息（含 thinkingSteps）
  - API 返回 204 → 显示空态提示
  - API 失败 → 降级 localStorage loadMessages
  - conversationId 存 React 状态，传给 sendMessage
  - 首次发送 conversationId=null → 后端自动创建
  - onDone 不调用 saveMessages
  - handleRegenerate 不调用 saveMessages
  - handleStop 调用 saveMessages（部分回答兜底）
  - onError(00000) 调用 saveMessages + 撤回 user+ai 消息
  - AI 消息的 onThinking 回调追加到 aiMsg.thinkingSteps
  - message-bubble 正确渲染 thinkingSteps
- test_tasks:
  - type: integration
    description: 页面加载 → API 返回历史消息
    scenarios: [mock 200 响应 → 渲染历史消息含 thinkingSteps]
  - type: integration
    description: API 失败降级 localStorage
    scenarios: [mock fetch 抛异常 → loadMessages 被调用]
  - type: unit
    description: saveMessages 调用验证
    scenarios: [onDone 不调用, handleStop 调用, onError(00000) 调用]
- contract_refs: [.dev-flow/R007/analysis/2026-05-22--R007-persistence-agent-upgrade-frontend.md]
- decision_refs: []
- blocked_files: [frontend/src/chat/parse-sse.ts, frontend/src/chat/use-chat-storage.ts]

### FB002.1 use-conversation.ts — 对话加载 hook `⬜`

新建 hook，职责：API 加载对话 + conversationId 管理 + role/status/thinkingSteps 映射 + 降级

```typescript
interface UseConversationReturn {
  conversationId: string | null;
  loadConversation: () => Promise<{ messages: Message[]; fromCache: boolean }>;
}

export function useConversation(): UseConversationReturn {
  const [conversationId, setConversationId] = useState<string | null>(null);

  const loadConversation = async () => {
    try {
      const response = await fetchWithAuth('/conversations/current');
      if (response.status === 204) {
        return { messages: [], fromCache: false };
      }
      const data: ConversationResponse = await response.json();
      setConversationId(data.conversation_id);
      // role 映射: human → user, status 映射: completed → done
      const mapped = data.messages.map(apiMsg => ({
        id: apiMsg.id,
        role: apiMsg.role === 'human' ? 'user' as const : 'ai' as const,
        content: apiMsg.content,
        status: mapApiStatus(apiMsg.status),
        sources: apiMsg.sources,
        thinkingSteps: apiMsg.thinking_steps,
        timestamp: new Date(apiMsg.created_at).getTime(),
      }));
      return { messages: mapped, fromCache: false };
    } catch {
      // 降级到 localStorage
      const cached = loadMessages();
      return { messages: cached ?? [], fromCache: true };
    }
  };

  return { conversationId, loadConversation };
}

function mapApiStatus(status: string): MessageStatus {
  switch (status) {
    case 'completed': return 'done';
    case 'stopped': return 'stopped';
    case 'error': return 'error';
    default: return 'done';
  }
}
```

### FB002.2 chat-ui.tsx — 集成 conversationId + 调整 saveMessages `⬜`

修改 `ChatUI` 组件：

1. 新增状态和 hook：

```typescript
const { conversationId, loadConversation } = useConversation();
const [isLoadingHistory, setIsLoadingHistory] = useState(true);
```

2. 初始化 useEffect 改为调用 `loadConversation()`：

```typescript
useEffect(() => {
  loadConversation().then(({ messages, fromCache }) => {
    setMessages(messages);
    setMounted(true);
    setIsLoadingHistory(false);
    if (fromCache && messages.length > 0) {
      setConversationId(null); // localStorage 无 conversationId
    }
  });
}, []);
```

3. `appendAndSend` 中 `startSSE` 传入 `conversationId`：

```typescript
sendMessage(question, callbacks, conversationId ?? undefined);
```

4. SSE callbacks 新增 `onThinking`：

```typescript
onThinking: (step) => {
  setMessages(prev => prev.map(m =>
    m.id === aiMsg.id
      ? { ...m, thinkingSteps: [...(m.thinkingSteps ?? []), step] }
      : m
  ));
},
```

5. saveMessages 调用调整：

| 调用点 | 改动 |
|--------|------|
| appendAndSend（发送时） | 删除 saveMessages 调用 |
| updateMsgAndSave（终态 onDone） | 删除 saveMessages 调用 |
| handleStop | **保留** saveMessages 调用 |
| handleRegenerate | 删除 saveMessages 调用 |
| onError(00000) | **保留** saveMessages 调用 |

6. 新增 loading 占位：`isLoadingHistory` 时显示骨架屏或加载提示
7. 如果 conversationId 从 SSE 响应中获取不到（设计决定前端不通过 SSE 获取），则首次发送时传 null，后续继续传 null（后端用 user_id 关联）

### FB002.3 chat-ui.tsx — 删除编辑相关代码 `⬜`

删除 `handleEdit` / `handleEditConfirm` 相关逻辑（PostgresSaver append-only 不支持编辑已发送消息）。删除 `editingId` 状态。message-bubble 中不再渲染编辑按钮。

注意：此项如果当前代码中无编辑功能则跳过（需检查实际代码确认）。
