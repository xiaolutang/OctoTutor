---
version: "1.0"
type: tasks
topic: code-convergence
requirement_cycle: R015
workflow:
  evaluate_provider: local
  mode: auto
status: archived
---

# R015 代码收敛 — 全栈任务清单

基于 design.md 设计，消除 6 视角 simplify 审查发现的 6 个高置信度共性问题。

全局约束：
- 每项改动均为机械修复，不涉及设计变更
- 不做"暂不实现"章节列出的 5 项内容
- sidebar 的 `pinnedItems`/`normalItems` 保持 filter 不变（不在 FF003 范围内）
- SYSTEM_PROMPT 保留在 llm.py（不合并到 prompts.py）

---

## 执行顺序

1. ⬜ R015-BF001 — llm.py 删除 generate_stream 死代码 + 测试级联清理（无依赖）
2. ⬜ R015-FF002 — createId 提取到 utils（无依赖）
3. ⬜ R015-FF003 — partitionByPinned 工具函数（无依赖）
4. ⬜ R015-FF001 — rehypePlugins 模块常量（无依赖）
5. ⬜ R015-FF004 — ConversationItemCard props 简化（无依赖）
6. ⬜ R015-FF005 — ChatInput disabled 清理（无依赖）

---

## R015-BF001：llm.py 遗留代码清理 `✅ 已完成`

- 文件：`backend/app/infra/llm.py`, `backend/app/domain/protocols.py`, `backend/tests/test_llm_generator_stream.py`, `backend/tests/_helpers.py`, `backend/tests/test_graph_integration.py`, `backend/tests/test_router_auth_integration.py`
- 改动类型：修改 + 删除
- domain: backend
- task_layer: foundation
- depends_on: []
- priority: 5
- risk_tags: []
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - `grep "generate_stream" backend/` 无结果
  - `backend/tests/test_llm_generator_stream.py` 文件不存在
  - `cd backend && python -m pytest` 全部通过
- test_tasks:
  - type: integration
    description: 后端全量测试验证无破坏
    scenarios: ["pytest 全部通过", "无 generate_stream 残留"]
- contract_refs: []
- decision_refs: []
- blocked_files: []

### BF001.1 删除 llm.py generate_stream 方法 `⬜`

删除 `backend/app/infra/llm.py` 行 86-108 的 `generate_stream` 方法。在 `SYSTEM_PROMPT`（行 21）上方补注释：

```python
# SYSTEM_PROMPT 用于非流式 /api/chat 和评估管线
# Agent Graph 使用 agent/prompts.py 的 TEACHING_SYSTEM_PROMPT（不同路径）
SYSTEM_PROMPT = """..."""
```

### BF001.2 删除 protocols.py generate_stream 声明 `⬜`

删除 `backend/app/domain/protocols.py` 行 32 的 `generate_stream` 方法声明。同时移除不再需要的 `from collections.abc import AsyncIterator` import（行 8），但检查 `AsyncIterator` 是否被其他 Protocol 使用。

### BF001.3 删除 test_llm_generator_stream.py `⬜`

整文件删除 `backend/tests/test_llm_generator_stream.py`。

### BF001.4 清理 _helpers.py mock `⬜`

在 `backend/tests/_helpers.py` 的 `make_mock_generator()` 函数中：
1. 删除行 62-64 的 `_stream` 辅助函数定义
2. 删除行 66 的 `gen.generate_stream = _stream`

### BF001.5 清理 test_graph_integration.py mock `⬜`

删除 `backend/tests/test_graph_integration.py` 行 304 的 `gen.generate_stream = AsyncMock()`。

### BF001.6 清理 test_router_auth_integration.py mock `⬜`

在 `backend/tests/test_router_auth_integration.py` 中：
1. 删除行 100-101 的 `async def _fake_stream` 定义
2. 删除行 102 的 `mock_gen.generate_stream = _fake_stream`

---

## R015-FF002：createId 提取到共享 utils `✅ 已完成`

- 文件：`frontend/src/lib/utils.ts`, `frontend/src/chat/controller.ts`, `frontend/src/__tests__/chat/controller-conversation.test.ts`, `frontend/src/__tests__/components/chat-ui.test.tsx`, `frontend/src/__tests__/components/conversation-sidebar.test.tsx`, `frontend/src/__tests__/contexts/conversation-context.test.tsx`
- 改动类型：修改
- domain: ui
- task_layer: foundation
- depends_on: []
- priority: 4
- risk_tags: []
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - `grep -r "function createId" frontend/src` 只在 utils.ts 有结果
  - `cd frontend && npx vitest run` 全部通过
- test_tasks:
  - type: unit
    description: 前端全量测试验证 createId 统一导入
    scenarios: ["vitest 全部通过", "createId 只定义一次"]
- contract_refs: []
- decision_refs: []
- blocked_files: []

### FF002.1 utils.ts 添加 createId `⬜`

在 `frontend/src/lib/utils.ts` 的 `cn()` 函数下方添加：

```typescript
export function createId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
}
```

### FF002.2 controller.ts 改为 import `⬜`

1. 删除 `frontend/src/chat/controller.ts` 行 9-11 的本地 `createId` 函数定义
2. 在文件顶部 import 区添加 `import { createId } from '@/lib/utils';`

### FF002.3 controller-conversation.test.ts 改为 import `⬜`

1. 删除行 22-24 的本地 `createId` 函数定义
2. 在文件顶部添加 `import { createId } from '@/lib/utils';`

### FF002.4 chat-ui.test.tsx 改为 import `⬜`

1. 删除行 45-47 的本地 `createId` 函数定义
2. 在文件顶部添加 `import { createId } from '@/lib/utils';`

### FF002.5 conversation-sidebar.test.tsx 改为 import `⬜`

1. 行 25 的 `id: \`conv-${Math.random().toString(36).slice(2, 8)}\`` 改为 `id: \`conv-${createId()}\``
2. 在文件顶部添加 `import { createId } from '@/lib/utils';`

### FF002.6 conversation-context.test.tsx 改为 import `⬜`

1. 行 26 的 `id: \`conv-${Math.random().toString(36).slice(2, 8)}\`` 改为 `id: \`conv-${createId()}\``
2. 在文件顶部添加 `import { createId } from '@/lib/utils';`

---

## R015-FF003：partitionByPinned 工具函数 `✅ 已完成`

- 文件：`frontend/src/chat/conversation-reducer.ts`
- 改动类型：修改
- domain: ui
- task_layer: foundation
- depends_on: []
- priority: 3
- risk_tags: []
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - conversation-reducer.ts 中无 `items.filter` + `items.filter` 的双重遍历模式
  - `cd frontend && npx vitest run` 全部通过
- test_tasks:
  - type: unit
    description: reducer 单元测试验证 partitionByPinned 等价性
    scenarios: ["vitest 全部通过"]
- contract_refs: []
- decision_refs: []
- blocked_files:
  - frontend/src/components/conversation-sidebar.tsx

### FF003.1 添加 partitionByPinned 函数 `⬜`

在 `frontend/src/chat/conversation-reducer.ts` reducer 函数上方（行 70 前）添加：

```typescript
function partitionByPinned(items: ConversationItem[]) {
  const pinned: ConversationItem[] = [];
  const normal: ConversationItem[] = [];
  for (const item of items) {
    (item.pinned ? pinned : normal).push(item);
  }
  return { pinned, normal };
}
```

### FF003.2 替换 INSERT_NEW 双重 filter `⬜`

行 96-97 改为：

```typescript
const { pinned, normal } = partitionByPinned(state.items);
```

### FF003.3 替换 UPDATE_ITEM 双重 filter `⬜`

行 136 后（`const rest = ...` 之后），行 137-143 的两组 pinned/normal filter 改为：

```typescript
const updated = action.payload;
const rest = state.items.filter((item) => item.id !== updated.id);
const { pinned, normal } = partitionByPinned(rest);
if (updated.pinned) {
  return { ...state, items: [updated, ...pinned, ...normal] };
}
return { ...state, items: [...pinned, updated, ...normal] };
```

---

## R015-FF001：rehypePlugins 模块常量 `✅ 已完成`

- 文件：`frontend/src/components/message-bubble.tsx`
- 改动类型：修改
- domain: ui
- task_layer: foundation
- depends_on: []
- priority: 2
- risk_tags: []
- smoke_required: false
- mode: direct
- status: pending
- acceptance_criteria:
  - message-bubble.tsx 无 JSX 内联 rehypePlugins 数组
  - rehypePlugins 定义在 remarkPlugins 下方作为模块常量
  - `cd frontend && npx vitest run` 全部通过
- test_tasks:
  - type: unit
    description: 消息渲染测试验证
    scenarios: ["vitest 全部通过"]
- contract_refs: []
- decision_refs: []
- blocked_files: []

### FF001.1 添加 rehypePlugins 常量 `⬜`

在行 25 `const remarkPlugins = [remarkMath];` 下方添加：

```typescript
const rehypePlugins = [[rehypeKatex, { throwOnError: false }]] as const;
```

### FF001.2 替换 JSX 内联引用 `⬜`

行 82 的 `rehypePlugins={[[rehypeKatex, { throwOnError: false }]]}` 改为：

```tsx
rehypePlugins={rehypePlugins}
```

---

## R015-FF004：ConversationItemCard props 简化 `✅ 已完成`

- 文件：`frontend/src/components/conversation-item-card.tsx`, `frontend/src/components/conversation-sidebar.tsx`, `frontend/src/__tests__/components/conversation-item-card.test.tsx`
- 改动类型：修改
- domain: ui
- task_layer: business
- depends_on: []
- priority: 2
- risk_tags: []
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - ConversationItemCardProps 无 onPin/onUnpin，有 onTogglePin
  - sidebar 无重复 props 传递，使用 cardProps spread
  - `cd frontend && npx vitest run` 全部通过
- test_tasks:
  - type: unit
    description: 组件测试验证 props 接口变更
    scenarios: ["vitest 全部通过", "onTogglePin 替代 onPin/onUnpin"]
- contract_refs: []
- decision_refs: []
- blocked_files: []

### FF004.1 重构 ConversationItemCard props 接口 `⬜`

`frontend/src/components/conversation-item-card.tsx`：

1. props 接口改为：

```typescript
interface ConversationItemCardProps {
  item: ConversationItem;
  isActive: boolean;
  onSelect: (id: string) => void;
  onRename: (id: string, title: string) => Promise<void>;
  onTogglePin: (id: string, pinned: boolean) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
  isStreaming: boolean;
}
```

2. 组件解构：`onPin, onUnpin` → `onTogglePin`
3. 行 190-201 的 pin toggle 按钮逻辑改为：

```tsx
onClick={async () => {
  setMenuOpen(false);
  try {
    await onTogglePin(item.id, item.pinned);
  } catch (err) {
    const msg = err instanceof Error ? err.message : (item.pinned ? '取消置顶失败' : '置顶失败');
    toast.error(msg);
  }
}}
```

### FF004.2 sidebar 提取 cardProps + spread `⬜`

`frontend/src/components/conversation-sidebar.tsx`：

1. 在 `const scrollRef = ...` 之后添加：

```typescript
const cardProps = {
  onSelect: switchTo,
  onRename: renameConversation,
  onTogglePin: (id: string, pinned: boolean) =>
    pinned ? unpinConversation(id) : pinConversation(id),
  onDelete: deleteConversation,
  isStreaming,
};
```

2. 置顶区（行 68-78）和普通区（行 85-95）的 ConversationItemCard 都改为：

```tsx
<ConversationItemCard
  key={item.id}
  item={item}
  isActive={activeId === item.id}
  {...cardProps}
/>
```

### FF004.3 更新 conversation-item-card.test.tsx 测试描述 `⬜`

`frontend/src/__tests__/components/conversation-item-card.test.tsx`：

1. 行 330 `it('对未置顶的 item 点击置顶应调用 onPin', ...)` 改为 `it('对未置顶的 item 点击置顶应调用 onTogglePin', ...)`
2. 行 355 `it('对已置顶的 item 点击取消置顶应调用 onUnpin', ...)` 改为 `it('对已置顶的 item 点击取消置顶应调用 onTogglePin', ...)`

注：测试使用纯函数策略（`handlePinToggle`），不直接 mock 组件 props，无需改动逻辑。

---

## R015-FF005：ChatInput disabled 清理 `✅ 已完成`

- 文件：`frontend/src/components/chat-input.tsx`, `frontend/src/components/chat-ui.tsx`
- 改动类型：修改
- domain: ui
- task_layer: business
- depends_on: []
- priority: 1
- risk_tags: []
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - `grep "disabled" frontend/src/components/chat-input.tsx` 无结果（不含 CSS class 中的 disabled）
  - ChatInputProps 接口无 `disabled` 字段
  - `cd frontend && npx vitest run` 全部通过
- test_tasks:
  - type: unit
    description: 输入组件测试验证
    scenarios: ["vitest 全部通过"]
- contract_refs: []
- decision_refs: []
- blocked_files: []

### FF005.1 移除 chat-input.tsx disabled prop `⬜`

`frontend/src/components/chat-input.tsx`：

1. 接口移除 `disabled?: boolean`（行 11）
2. 组件解构移除 `disabled = false`（行 20）
3. 行 36 `if (!isStreaming && !disabled && value.trim())` → `if (!isStreaming && value.trim())`
4. 行 50 `disabled={disabled}` → `disabled={isStreaming}`
5. 行 64 `disabled={isStreaming || !value.trim() || disabled}` → `disabled={isStreaming || !value.trim()}`

### FF005.2 移除 chat-ui.tsx disabled 传递 `⬜`

`frontend/src/components/chat-ui.tsx` 行 67 删除 `disabled={isStreaming}`。

最终 ChatInput 调用：

```tsx
<ChatInput
  value={input}
  onChange={setInput}
  onSend={handleSend}
  onStop={handleStop}
  isStreaming={isStreaming}
/>
```
