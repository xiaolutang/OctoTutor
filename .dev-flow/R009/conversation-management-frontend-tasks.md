---
version: "1.0"
type: tasks
topic: conversation-management-frontend
requirement_cycle: R009
workflow:
  evaluate_provider: local
  mode: auto
status: archived
---

# 多对话管理 — 前端 任务清单

基于 design.md 设计，列出需要创建/修改的具体细节。
全局约束：React Context + useReducer 状态管理，shadcn/ui 组件，ConversationItem 字段保持 snake_case。

---

## 执行顺序

1. ⬜ 任务 1 — shadcn/ui 组件安装（无依赖）
   - ⬜ 1.1 安装 sidebar/popover/alert-dialog/sonner/input
2. ⬜ 任务 2 — chat/types.ts + chat/use-chat-stream.ts — 类型 + SSE title 事件（无依赖）
   - ⬜ 2.1 新增 ConversationItem 等类型
   - ⬜ 2.2 新增 SSE title 事件解析
3. ⬜ 任务 3 — contexts/conversation-context.tsx — 对话状态管理（依赖任务 2）
   - ⬜ 3.1 新建 ConversationContext
   - ⬜ 3.2 新建 chat/use-conversation-list.ts
4. ⬜ 任务 4 — components/chat-layout.tsx — 布局骨架（依赖任务 1）
   - ⬜ 4.1 新建 sidebar + main 布局
5. ⬜ 任务 5 — components/conversation-sidebar.tsx + conversation-item.tsx — 对话列表 UI（依赖任务 3, 4）
   - ⬜ 5.1 新建 conversation-sidebar.tsx
   - ⬜ 5.2 新建 conversation-item.tsx
6. ⬜ 任务 6 — components/conversation-menu.tsx + delete-confirm-dialog.tsx — 三点菜单（依赖任务 3）— 合并到 FB001
   - ⬜ 6.1 内联在 ConversationItemCard 中
   - ⬜ 6.2 内联在 ConversationItemCard 中
7. ⬜ 任务 7 — chat/controller.ts + components/chat-ui.tsx — 集成 ConversationContext（依赖任务 3）
   - ⬜ 7.1 修改 controller.ts — activeId 从 Context 读取
   - ⬜ 7.2 修改 chat-ui.tsx — 自动滚动 + 外部 conversationId
   - ⬜ 7.3 修改 chat/use-conversation.ts — 移除 localStorage
8. ⬜ 任务 8 — app/chat/page.tsx — 页面布局集成（依赖任务 4, 7）
   - ⬜ 8.1 ConversationProvider 包裹 + sidebar + main 布局
9. ⬜ 最后 — 编译验证 + 现有测试通过

---

## R009-FF001：shadcn/ui 组件安装 `✅ 已完成`

- 文件：`frontend/package.json`（修改）、`frontend/components.json`（可能修改）
- 改动类型：配置
- domain: ui
- task_layer: foundation
- depends_on: []
- priority: 5
- risk_tags: []
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - `npx shadcn@latest add sidebar` 成功安装
  - `npx shadcn@latest add popover` 成功安装
  - `npx shadcn@latest add alert-dialog` 成功安装
  - `npx shadcn@latest add sonner` 成功安装
  - `npx shadcn@latest add input` 成功安装
  - `components/ui/` 目录下出现对应组件文件
  - `npm run build` 编译通过
- test_tasks:
  - type: unit
    description: 编译验证
    scenarios: [import所有新组件不报错]
- contract_refs: []
- decision_refs: []
- blocked_files: []

### FF001.1 安装 shadcn/ui 组件 `⬜`

在 `frontend/` 目录下执行：

```bash
npx shadcn@latest add sidebar
npx shadcn@latest add popover
npx shadcn@latest add alert-dialog
npx shadcn@latest add sonner
npx shadcn@latest add input
```

---

## R009-FF002：chat/types.ts + chat/use-chat-stream.ts — 类型 + SSE title 事件 `✅ 已完成`

- 文件：
  - `frontend/src/chat/types.ts`（修改）
  - `frontend/src/chat/use-chat-stream.ts`（修改）
- 改动类型：修改
- domain: ui
- task_layer: foundation
- depends_on: []
- priority: 5
- risk_tags: []
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - ConversationItem 接口包含 id/title/pinned/pinned_at/message_count/created_at/updated_at
  - ConversationListState 接口包含 items/cursor/hasMore/isLoading/isInitialized/activeId/isNewConversation
  - SSECallbacks 新增 onTitle 回调
  - use-chat-stream.ts 中 parse SSE 新增 `case 'title'` 处理
  - 现有类型和 SSE 解析不回归
- test_tasks:
  - type: unit
    description: 类型定义和 SSE 解析测试
    scenarios: [ConversationItem 类型完整, SSECallbacks 含onTitle, title事件正确解析]
- contract_refs: [".dev-flow/R009/analysis/2026-05-24--R009-conversation-management-frontend.md"]
- decision_refs: []
- blocked_files: []

### FF002.1 修改 types.ts `⬜`

新增 ConversationItem 和 ConversationListState：

```typescript
// 对话列表项（对应后端 GET /api/conversations 响应，保持 snake_case）
export interface ConversationItem {
  id: string;
  title: string;
  pinned: boolean;
  pinned_at: string | null;
  message_count: number;
  created_at: string;
  updated_at: string;
}

// 对话列表状态
export interface ConversationListState {
  items: ConversationItem[];
  cursor: string | null;
  hasMore: boolean;
  isLoading: boolean;
  isInitialized: boolean;
  activeId: string | null;
  isNewConversation: boolean;
}
```

在 SSECallbacks 中新增：

```typescript
export interface SSECallbacks {
  // ... 现有回调 ...
  onTitle: (conversationId: string, title: string) => void;  // 新增
}
```

### FF002.2 修改 use-chat-stream.ts `⬜`

在 `chatStreamFetch` 的事件分发中新增 `case 'title'`：

```typescript
case 'title':
  const titleData = JSON.parse(data);
  callbacks.onTitle(titleData.conversation_id, titleData.title);
  break;
```

---

## R009-FF003：contexts/conversation-context.tsx — 对话状态管理 `✅ 已完成`

- 文件：
  - `frontend/src/contexts/conversation-context.tsx`（新建）
  - `frontend/src/chat/use-conversation-list.ts`（新建）
- 改动类型：新建
- domain: ui
- task_layer: foundation
- depends_on: [R009-FF002]
- priority: 5
- risk_tags: []
- smoke_required: true
- mode: negotiated
- status: pending
- acceptance_criteria:
  - ConversationProvider 包裹后，子组件可通过 useConversationContext() 获取状态
  - useReducer 管理 items/activeId/isNewConversation/cursor/hasMore/isLoading/isInitialized
  - 初始化时 GET /api/conversations?limit=20 加载列表
  - activeId 存储到 sessionStorage，页面刷新后可恢复
  - switchTo(id) 切换 activeId 并更新 sessionStorage
  - createNew() 设置 activeId=null + isNewConversation=true
  - insertNewConversation(item) 在列表顶部插入新对话
  - updateTitle(id, title) 更新列表中指定对话的标题
  - loadMore() 加载下一页对话
  - removeConversation(id) 从列表移除
  - renameConversation(id, title) 调用 PATCH API
  - pinConversation(id) / unpinConversation(id) 调用 PATCH API
  - deleteConversation(id) 调用 DELETE API
  - deleteConversation(id) 删除当前 activeId 对话后，自动设置 activeId 为列表第一个对话或 null（空态）
- test_tasks:
  - type: unit
    description: ConversationContext 状态管理测试
    scenarios: [初始化加载列表, switchTo切换, createNew设置状态, insertNewConversation插入顶部, updateTitle更新, loadMore分页, deleteConversation移除, 删除当前对话自动切换]
- contract_refs: [".dev-flow/R009/analysis/2026-05-24--R009-conversation-management-frontend.md"]
- decision_refs: []
- blocked_files: []

### FF003.1 新建 conversation-context.tsx `⬜`

```typescript
// contexts/conversation-context.tsx
'use client'

import React, { createContext, useContext, useReducer, useCallback, useEffect } from 'react';
import { ConversationItem, ConversationListState } from '@/chat/types';
import { fetchWithAuth } from '@/lib/api-client';

type ConversationAction =
  | { type: 'SET_LOADING'; payload: boolean }
  | { type: 'INIT_LIST'; payload: { items: ConversationItem[]; cursor: string | null; hasMore: boolean } }
  | { type: 'SET_ACTIVE'; payload: string | null }
  | { type: 'SET_NEW_CONVERSATION'; payload: boolean }
  | { type: 'INSERT_NEW'; payload: ConversationItem }
  | { type: 'UPDATE_TITLE'; payload: { id: string; title: string } }
  | { type: 'APPEND_PAGE'; payload: { items: ConversationItem[]; cursor: string | null; hasMore: boolean } }
  | { type: 'REMOVE_ITEM'; payload: string }
  | { type: 'UPDATE_ITEM'; payload: ConversationItem }

interface ConversationContextValue extends ConversationListState {
  switchTo: (id: string) => void;
  createNew: () => void;
  insertNewConversation: (item: ConversationItem) => void;
  updateTitle: (id: string, title: string) => void;
  loadMore: () => Promise<void>;
  renameConversation: (id: string, title: string) => Promise<void>;
  pinConversation: (id: string) => Promise<void>;
  unpinConversation: (id: string) => Promise<void>;
  deleteConversation: (id: string) => Promise<void>;
}

const ConversationContext = createContext<ConversationContextValue | null>(null);

export function useConversationContext() { ... }
export function ConversationProvider({ children }: { children: React.ReactNode }) { ... }
```

reducer 处理上述 9 种 action。初始化时从 sessionStorage 读取 activeId。

### FF003.2 新建 use-conversation-list.ts `⬜`

封装 API 调用逻辑（供 ConversationContext 使用）：

```typescript
// chat/use-conversation-list.ts
export async function fetchConversationList(cursor?: string, limit = 20): Promise<{...}>
export async function patchConversation(id: string, data: { title?: string; pinned?: boolean }): Promise<ConversationItem>
export async function deleteConversation(id: string): Promise<void>
```

---

## R009-FF004：components/chat-layout.tsx — 布局骨架 `✅ 已完成`

- 文件：`frontend/src/components/chat-layout.tsx`（新建）
- 改动类型：新建
- domain: ui
- task_layer: ui
- depends_on: [R009-FF001]
- priority: 4
- risk_tags: []
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - 左侧 sidebar 固定宽度（w-64），右侧 main 占满剩余空间
  - sidebar 可选折叠（后续优化，当前仅占位）
  - 移动端暂不处理（桌面端优先）
  - `npm run build` 编译通过
- test_tasks:
  - type: unit
    description: 布局渲染测试
    scenarios: [sidebar和main同时渲染, children正确渲染]
- contract_refs: []
- decision_refs: []
- blocked_files: []

### FF004.1 新建 chat-layout.tsx `⬜`

```tsx
// components/chat-layout.tsx
'use client'

import { SidebarProvider } from '@/components/ui/sidebar';

export function ChatLayout({ sidebar, children }: { sidebar: React.ReactNode; children: React.ReactNode }) {
  return (
    <SidebarProvider>
      <div className="flex h-screen">
        <aside className="w-64 border-r">{sidebar}</aside>
        <main className="flex-1 overflow-hidden">{children}</main>
      </div>
    </SidebarProvider>
  );
}
```

---

## R009-FB001：conversation-sidebar.tsx + conversation-item.tsx — 对话列表 UI `✅ 已完成`

- 文件：
  - `frontend/src/components/conversation-sidebar.tsx`（新建）
  - `frontend/src/components/conversation-item-card.tsx`（新建）
- 改动类型：新建
- domain: ui
- task_layer: ui
- depends_on: [R009-FF003, R009-FF004]
- priority: 4
- risk_tags: []
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - 侧边栏顶部显示"新建对话"按钮
  - 列表分置顶区和普通区，置顶区显示"📌 已置顶"标签
  - 每个对话项显示标题 + 时间
  - 当前选中对话高亮
  - hover 对话项显示三点菜单按钮
  - 空列表显示"暂无对话"
  - 滚动到底部触发 loadMore
  - 点击对话项触发 switchTo
  - "新建对话"按钮触发 createNew
  - 正在生成（isStreaming=true）时点击其他对话，提示用户等待
- test_tasks:
  - type: unit
    description: 对话列表 UI 渲染测试
    scenarios: [空列表显示空态, 有数据渲染列表项, 置顶区+普通区, 点击切换, 滚动加载, 新建按钮, 正在生成时点击切换提示等待]
- contract_refs: [".dev-flow/R009/analysis/2026-05-24--R009-conversation-management-frontend.md"]
- decision_refs: []
- blocked_files: []

### FB001.1 新建 conversation-sidebar.tsx `⬜`

```tsx
// components/conversation-sidebar.tsx
'use client'

export function ConversationSidebar() {
  // 从 useConversationContext() 获取 items/activeId/switchTo/createNew/loadMore/hasMore
  // 从 useChatController 或 context 获取 isStreaming（判断是否允许切换）
  // 滚动容器，onScroll 检测到底部 → loadMore()
  // 渲染：新建按钮 + 置顶区(ConversationItem[]) + 普通区(ConversationItem[])
}
```

### FB001.2 新建 conversation-item-card.tsx `⬜`

```tsx
// components/conversation-item-card.tsx
'use client'

// 注意：组件命名为 ConversationItemCard，避免与 types.ts 的 ConversationItem 接口同名冲突
export function ConversationItemCard({ item, isActive, onSelect }: {
  item: ConversationItem;
  isActive: boolean;
  onSelect: (id: string) => void;
}) {
  // 显示标题 + 相对时间（如"3分钟前"）
  // hover 时显示三点菜单按钮（ConversationMenu）
  // isActive 时高亮背景
}
```

---

## R009-FB002：conversation-menu.tsx + delete-confirm-dialog.tsx — 三点菜单 `✅ 已完成`（合并到 FB001）

- 文件：
  - `frontend/src/components/conversation-menu.tsx`（新建）
  - `frontend/src/components/delete-confirm-dialog.tsx`（新建）
- 改动类型：新建
- domain: ui
- task_layer: ui
- depends_on: [R009-FF003]
- priority: 4
- risk_tags: []
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - 三点按钮点击弹出 Popover 菜单
  - 菜单包含：重命名、置顶/取消置顶、删除（红色文字）
  - 重命名：点击后标题变为 input，Enter/blur 提交，Esc 取消
  - 置顶：调用 pinConversation，成功后列表更新
  - 置顶超限：toast 提示"最多置顶 5 条对话"
  - 取消置顶：调用 unpinConversation
  - 删除：弹出 AlertDialog 确认，确认后调用 deleteConversation
  - 使用 shadcn/ui Popover + AlertDialog + Sonner
- test_tasks:
  - type: unit
    description: 三点菜单交互测试
    scenarios: [菜单弹出, 重命名提交, 重命名取消, 置顶操作, 取消置顶, 删除确认, 删除取消]
- contract_refs: [".dev-flow/R009/analysis/2026-05-24--R009-conversation-management-frontend.md"]
- decision_refs: []
- blocked_files: []

### FB002.1 新建 conversation-menu.tsx `⬜`（内联在 ConversationItemCard）

```tsx
// components/conversation-menu.tsx
'use client'

import { Popover, PopoverTrigger, PopoverContent } from '@/components/ui/popover';
import { toast } from 'sonner';

export function ConversationMenu({ item, onRenameStart }: {
  item: ConversationItem;
  onRenameStart: () => void;
}) {
  // Popover 触发器：MoreHorizontal (lucide-react) 图标
  // 内容：重命名 / 置顶或取消置顶 / 删除（红色）
  // 置顶时检查上限，超限 toast 提示
  // 删除打开 DeleteConfirmDialog
}
```

### FB002.2 新建 delete-confirm-dialog.tsx `⬜`（内联在 ConversationItemCard）

```tsx
// components/delete-confirm-dialog.tsx
'use client'

import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog';

export function DeleteConfirmDialog({ open, onOpenChange, onConfirm }: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
}) {
  // "确定删除这条对话？删除后不可恢复。"
  // 取消 / 确认删除（红色按钮）
}
```

---

## R009-FB003：controller.ts + chat-ui.tsx + use-conversation.ts — 集成 ConversationContext `✅ 已完成`

- 文件：
  - `frontend/src/chat/controller.ts`（修改）
  - `frontend/src/components/chat-ui.tsx`（修改）
  - `frontend/src/chat/use-conversation.ts`（修改）
- 改动类型：修改
- domain: ui
- task_layer: ui
- depends_on: [R009-FF003]
- priority: 5
- risk_tags: []
- smoke_required: true
- mode: negotiated
- status: pending
- acceptance_criteria:
  - controller.ts 中 activeConversationId 从 ConversationContext 读取
  - SSE init 回调中调用 insertNewConversation
  - SSE title 回调中调用 updateTitle
  - chat-ui.tsx 接收外部 conversationId prop
  - 发送消息后自动滚动到底部
  - 切换对话后自动滚动到底部
  - 流式生成时持续自动滚动
  - use-conversation.ts 不再使用 localStorage，从参数接收 conversationId
  - 现有对话功能（流式/重新生成/停止）不回归
- test_tasks:
  - type: integration
    description: 对话交互集成测试
    scenarios: [新建对话SSE流程, 切换对话加载历史, 标题自动更新, 自动滚动, 重新生成正常, 停止生成正常]
- contract_refs: [".dev-flow/R009/analysis/2026-05-24--R009-conversation-management-frontend.md"]
- decision_refs: []
- blocked_files: []

### FB003.1 修改 controller.ts `⬜`

关键改动：
1. 移除内部 `conversationId` 状态管理，改为从 ConversationContext 获取 activeId
2. `handleSend` 中使用 activeId（可能为 null，null 时 SSE 不传 conversation_id）
3. SSECallbacks 新增 `onTitle` 回调，调用 `updateTitle`
4. SSECallbacks `onInit` 回调中，如果是新对话，调用 `insertNewConversation`

```typescript
// 改动要点
const { activeId, isNewConversation, insertNewConversation, updateTitle } = useConversationContext();

const startSSE = (question: string) => {
  // conversationId = activeId (可能为 null)
  sendMessage({
    question,
    conversationId: activeId,
    onInit: (id) => {
      if (isNewConversation) {
        insertNewConversation({ id, title: '新对话', ... });
      }
    },
    onTitle: (convId, title) => {
      updateTitle(convId, title);
    },
    // ... 其他回调不变
  });
};
```

### FB003.2 修改 chat-ui.tsx `⬜`

1. 添加自动滚动逻辑：
   - 发送消息后 scroll to bottom
   - 切换对话加载历史后 scroll to bottom
   - 流式 token 到达时 scroll to bottom（仅当用户已在底部时跟随）
2. 不再内部管理 conversationId，从 props 或 context 获取

```typescript
// 自动滚动 ref
const messagesEndRef = useRef<HTMLDivElement>(null);

useEffect(() => {
  messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
}, [messages.length, isStreaming]);
```

### FB003.3 修改 use-conversation.ts `⬜`

1. 移除 `loadConversationId()` / `saveConversationId()` localStorage 逻辑
2. `useConversation` hook 改为接收 `conversationId: string` 参数（不再从 localStorage 读取）
3. 保持 `loadConversation(conversationId)` 的 API 调用逻辑不变

---

## R009-FB004：app/chat/page.tsx — 页面布局集成 `✅ 已完成`

- 文件：`frontend/src/app/chat/page.tsx`（修改）
- 改动类型：修改
- domain: ui
- task_layer: ui
- depends_on: [R009-FF004, R009-FB003]
- priority: 4
- risk_tags: []
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - 页面布局为 sidebar + main，左侧 ConversationSidebar，右侧 ChatUI
  - ConversationProvider 包裹整个页面
  - 页面加载时初始化对话列表
  - `npm run build` 编译通过
  - 现有 /chat 路由功能不回归
- test_tasks:
  - type: integration
    description: 页面集成测试
    scenarios: [页面渲染侧边栏+对话区, 初始化加载列表, 编译通过]
- contract_refs: []
- decision_refs: []
- blocked_files: []

### FB004.1 ConversationProvider 包裹 + 布局 `⬜`

```tsx
// app/chat/page.tsx
'use client'

import { ConversationProvider } from '@/contexts/conversation-context';
import { ChatLayout } from '@/components/chat-layout';
import { ConversationSidebar } from '@/components/conversation-sidebar';
import { ChatUI } from '@/components/chat-ui';

export default function ChatPage() {
  return (
    <ConversationProvider>
      <ChatLayout
        sidebar={<ConversationSidebar />}
      >
        <ChatUI />
      </ChatLayout>
    </ConversationProvider>
  );
}
```

移除原来的直接渲染 `<ChatUI />`。
