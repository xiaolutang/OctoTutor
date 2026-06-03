---
module: code-quality-frontend
version: "1.0"
date: 2026-06-03
tags: [refactoring, frontend, testing]
type: design_frontend
status: designed
requirement_cycle: R013
source_analysis: 2026-06-03--code-quality-governance.md
architecture_md_updates: false
---

# 前端代码质量治理 — 设计报告

> 3 项前端重构：Reducer 提取、SSE 去重、Controller 测试重写

## 1. 目标

- FF001: 将 conversationReducer 提取为独立模块，解除测试对 auth-context 的编译依赖
- FF002: 提取 SSE 事件分发共享函数，消除 60 行重复 switch-case
- FF003: 用 renderHook 重写 controller-race-condition.test.ts，测试真实代码

## 2. 现状

### FF001: Reducer 嵌入 Provider 组件

`conversation-context.tsx` 的 `conversationReducer`、`ConversationAction` 类型、`initialState` 都定义在组件文件内。测试文件因 auth-sdk-web broken symlink 无法 import，被迫复制 reducer。复制版已 3 处分歧。

### FF002: SSE 事件分发重复

`use-chat-stream.ts` 中 `chatStreamFetch`（99-130行）和 `resumeStream`（209-229行）各有一套 SSE 事件 switch。公共事件（status/sources/thinking/token/done/error）逻辑完全一致。

### FF003: 测试零耦合

`controller-race-condition.test.ts` 手写模拟函数验证自己，真实 `useChatController` 的 init useEffect（含 needsResumePlaceholder）和 SSE 重连逻辑完全未覆盖。

## 3. 项目结构

```
frontend/src/
├── chat/
│   ├── conversation-reducer.ts    # 新建（FF001）：从 context 提取
│   └── use-chat-stream.ts         # 修改（FF002）：提取 handleSSEEvent
├── contexts/
│   └── conversation-context.tsx   # 修改（FF001）：从 reducer.ts import
└── __tests__/
    └── chat/
        └── controller-race-condition.test.ts  # 重写（FF003）
```

## 4. 具体改动

### FF001: conversation-reducer.ts（新建）

从 conversation-context.tsx 移入：
- `ConversationAction` 类型
- `ConversationListState` 类型（已在 types.ts，可 re-export）
- `conversationReducer` 函数
- `initialState` 常量
- `STORAGE_KEY` 常量
- `getStoredActiveId` / `storeActiveId` 辅助函数

conversation-context.tsx 改为 `import { conversationReducer, initialState, ... } from '@/chat/conversation-reducer'`

conversation-context.test.tsx 改为 `import { conversationReducer, initialState } from '@/chat/conversation-reducer'`，删除复制的 reducer 和类型。

测试用例需更新以匹配真实行为：
- INSERT_NEW：验证 pinned/normal 分区
- REMOVE_ITEM：验证 activeId 自动切换
- UPDATE_ITEM：验证重排序

### FF002: handleSSEEvent 提取

提取签名：
```typescript
type BaseSSECallbacks = {
  onStatus: (stage: string, message: string) => void;
  onSources: (sources: SourceReference[]) => void;
  onToken: (token: string) => void;
  onThinking: (step: ThinkingStep) => void;
  onDone: () => void;
  onError: (error: { code: string; message: string; action: string }) => void;
};

function handleSSEEvent(event: { type: string; data: unknown }, callbacks: BaseSSECallbacks): void
```

chatStreamFetch 在调用 handleSSEEvent 后额外处理 init/title。
resumeStream 只调用 handleSSEEvent（无 init/title）。

### FF003: 测试重写

用 `@testing-library/react` 的 `renderHook` 测试真实 `useChatController`。

需要 mock 的依赖：
- `useChatStream` → mock sendMessage/stop/isStreaming
- `useConversation` → mock loadConversation
- `useAuth` → mock isInitialized
- `useConversationContext` → mock activeId/isNewConversation/etc.

关键测试场景：
- Auth + Conv 未就绪时不加载消息
- Auth + Conv 就绪后加载消息
- 加载后 needsResumePlaceholder 追加 AI 占位消息
- activeId 切换时重新加载
- SSE 重连触发条件
- 新对话清空消息

## 5. 验收标准

| 验收条件 | 验收方式 |
|----------|----------|
| conversation-reducer.ts 独立存在 | 文件检查 |
| conversation-context.tsx 从 reducer.ts import | grep 检查 |
| 测试 import 真实 reducer 而非复制 | grep 检查 |
| handleSSEEvent 提取成功 | 函数签名检查 |
| use-chat-stream.ts 无重复 switch-case | 代码审查 |
| controller-race-condition.test.ts 使用 renderHook | grep 检查 |
| 前端 259 测试全部通过 | `npx vitest run` |
