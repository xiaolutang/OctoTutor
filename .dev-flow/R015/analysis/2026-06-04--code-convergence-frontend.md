---
module: code-convergence
version: "1.0"
date: 2026-06-04
tags: [convergence, dedup, cleanup]
type: design_frontend
status: designed
requirement_cycle: R015
source_analysis: 2026-06-04--code-convergence.md
architecture_md_updates: false
---

# R015 代码收敛 — 设计报告

> 关联设计：无独立后端设计（BF001 改动极小，合并在本文档）

## 1. 目标

- 消除跨 Agent 重复发现的 6 个共性问题
- 每项改动均为机械修复，不涉及设计变更
- 全部改动后 271 前端测试 + 后端测试通过

## 2. 现状分析

6 视角 simplify 审查发现 125 个问题，其中 6 个被多个 Agent 独立标记，属于高置信度收敛项。

### 已有基础设施

- `lib/utils.ts`：已有 `cn()` 工具函数，是添加 `createId()` 的自然位置
- `agent/prompts.py`：已有 `TEACHING_SYSTEM_PROMPT`（Agent Graph 使用）
- `remarkPlugins`：已正确提取为模块顶层常量（message-bubble.tsx:25）

## 3. 改动清单

### FF001：rehypePlugins 模块常量

| 文件 | 改动 |
|------|------|
| `frontend/src/components/message-bubble.tsx` | 添加 `rehypePlugins` 常量，JSX 引用 |

```typescript
// 在 remarkPlugins（行 25）下方添加
const rehypePlugins = [[rehypeKatex, { throwOnError: false }]] as const;

// JSX 中改为
rehypePlugins={rehypePlugins}
```

### FF002：createId 提取到 utils

| 文件 | 改动 |
|------|------|
| `frontend/src/lib/utils.ts` | 添加 `createId()` |
| `frontend/src/chat/controller.ts` | 删除本地 `createId`，改为 import |
| 4 个测试文件 | 删除复制的 `createId`，改为 import |

```typescript
// lib/utils.ts 新增
export function createId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
}

// controller.ts 改为
import { createId } from '@/lib/utils';
```

### FF003：partitionByPinned 工具函数

| 文件 | 改动 |
|------|------|
| `frontend/src/chat/conversation-reducer.ts` | 添加 `partitionByPinned`，reducer 内复用 |

```typescript
// conversation-reducer.ts 新增
function partitionByPinned(items: ConversationItem[]) {
  const pinned: ConversationItem[] = [];
  const normal: ConversationItem[] = [];
  for (const item of items) {
    (item.pinned ? pinned : normal).push(item);
  }
  return { pinned, normal };
}
```

INSERT_NEW（行 96-97）改为：
```typescript
const { pinned, normal } = partitionByPinned(state.items);
```

UPDATE_ITEM（行 136-144）改为：
```typescript
const rest = state.items.filter((item) => item.id !== updated.id);
const { pinned, normal } = partitionByPinned(rest);
```

sidebar 的 `pinnedItems`/`normalItems` 是渲染时计算，规模小（<50），暂不改。reducer 是热路径（每次 dispatch 都执行），优先收敛。

### FF004：ConversationItemCard props 简化

| 文件 | 改动 |
|------|------|
| `frontend/src/components/conversation-item-card.tsx` | 合并 onPin/onUnpin 为 onTogglePin |
| `frontend/src/components/conversation-sidebar.tsx` | 提取 cardProps spread + onTogglePin |

```typescript
// conversation-item-card.tsx props 改为
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

```tsx
// conversation-sidebar.tsx 提取公共 props
const cardProps = {
  onSelect: switchTo,
  onRename: renameConversation,
  onTogglePin: (id: string, pinned: boolean) =>
    pinned ? unpinConversation(id) : pinConversation(id),
  onDelete: deleteConversation,
  isStreaming,
};

// pinned 区和普通区都用
<ConversationItemCard key={item.id} item={item} isActive={...} {...cardProps} />
```

### FF005：ChatInput disabled 清理

| 文件 | 改动 |
|------|------|
| `frontend/src/components/chat-input.tsx` | 移除 `disabled` prop |
| `frontend/src/components/chat-ui.tsx` | 移除 `disabled={isStreaming}` |

```typescript
// chat-input.tsx
interface ChatInputProps {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  onStop: () => void;
  isStreaming: boolean;
  // disabled 移除
}

// 内部所有 disabled 引用改为 isStreaming
// 行 36: if (!isStreaming && value.trim())
// 行 50: disabled={isStreaming}
// 行 64: disabled={isStreaming || !value.trim()}
```

### BF001：llm.py 遗留代码清理

| 文件 | 改动 |
|------|------|
| `backend/app/infra/llm.py` | 删除 `generate_stream` 方法 + 补注释 |
| `backend/app/domain/protocols.py` | 删除 `generate_stream` Protocol 方法 |
| `backend/tests/test_llm_generator_stream.py` | 整文件删除（全部测试 generate_stream） |
| `backend/tests/_helpers.py` | 移除 `make_mock_generator` 中的 `generate_stream` mock |
| `backend/tests/test_graph_integration.py` | 移除 `generate_stream = AsyncMock()` |
| `backend/tests/test_router_auth_integration.py` | 移除 `generate_stream = _fake_stream` |

调用分析：
- `generate()`：被 `chat/service.py:33` 和 `evaluation/eval_runner.py:660` 使用 → **保留**
- `generate_stream()`：**无调用者** → 删除死代码
- `SYSTEM_PROMPT`/`MATH_JUDGE_PROMPT`：被 `generate()` 的 `_build_messages()` 使用 → **保留**（与 Agent Graph 的 TEACHING_SYSTEM_PROMPT 服务不同路径）

测试文件影响分析：
- `test_llm_generator_stream.py`：整个文件测试 generate_stream，全部测试用例失效 → **删除整个文件**
- `_helpers.py:66`：`make_mock_generator()` 中 `gen.generate_stream = _stream` → 删除该行
- `test_graph_integration.py:304`：`gen.generate_stream = AsyncMock()` → 删除该行
- `test_router_auth_integration.py:102`：`mock_gen.generate_stream = _fake_stream` → 删除该行 + 相关 `_fake_stream` 辅助函数

```python
# llm.py: 删除 generate_stream 方法（行 86-108）
# 补注释说明 SYSTEM_PROMPT 与 Agent Graph TEACHING_SYSTEM_PROMPT 的关系
SYSTEM_PROMPT = """..."""  # 用于非流式 /api/chat 和评估管线

# protocols.py: 删除 generate_stream 声明（行 32）

# test_llm_generator_stream.py: 整文件删除

# _helpers.py: 删除第 66 行 gen.generate_stream = _stream
# _stream 辅助函数（行 62-64）也一并删除

# test_graph_integration.py: 删除第 304 行 gen.generate_stream = AsyncMock()

# test_router_auth_integration.py: 删除第 102 行 mock_gen.generate_stream = _fake_stream
# 检查 _fake_stream 定义是否还被其他地方使用，如无则一并删除
```

## 4. 项目结构

无新增文件。改动文件 13 个（含 1 个删除）：

```
frontend/src/
├── lib/utils.ts                              # FF002: 添加 createId
├── chat/controller.ts                        # FF002: import createId
├── chat/conversation-reducer.ts              # FF003: partitionByPinned
├── components/message-bubble.tsx             # FF001: rehypePlugins 常量
├── components/chat-input.tsx                 # FF005: 移除 disabled
├── components/chat-ui.tsx                    # FF005: 移除 disabled 传递
├── components/conversation-item-card.tsx      # FF004: onTogglePin
├── components/conversation-sidebar.tsx        # FF004: cardProps spread
└── __tests__/*.test.ts(x)                    # FF002: import createId

backend/app/
├── infra/llm.py                              # BF001: 删 generate_stream
└── domain/protocols.py                       # BF001: 删 generate_stream 声明

backend/tests/
├── test_llm_generator_stream.py              # BF001: 整文件删除
├── _helpers.py                               # BF001: 移除 generate_stream mock
├── test_graph_integration.py                 # BF001: 移除 generate_stream mock
└── test_router_auth_integration.py           # BF001: 移除 generate_stream mock
```

## 5. 技术决策

| 决策 | 方案 | 理由 |
|------|------|------|
| sidebar 的 pinnedItems/normalItems 不用 partitionByPinned | 保留 filter | sidebar 渲染时规模小，useMemo 收益不大，减少跨组件耦合 |
| SYSTEM_PROMPT 保留在 llm.py | 不合并到 prompts.py | 两条路径（非流式 ChatService vs Agent Graph）使用不同 prompt 策略，强行合并会引入依赖 |
| generate_stream 从 Protocol 也删除 | 一并清理 | Protocol 是接口约束，实现已删除则接口也应删除 |

## 6. 验收标准

| 验收条件 | 验收方式 |
|----------|---------|
| 271 前端测试全部通过 | `cd frontend && npx vitest run` |
| 后端测试全部通过 | `cd backend && python -m pytest` |
| rehypePlugins 引用稳定 | 检查 message-bubble.tsx 无内联数组 |
| createId 无重复定义 | `grep -r "function createId" frontend/src` 只在 utils.ts |
| disabled prop 已移除 | `grep "disabled" frontend/src/components/chat-input.tsx` 无结果 |
| generate_stream 已删除 | `grep "generate_stream" backend/` 无结果（含 app 和 tests） |
| test_llm_generator_stream.py 已删除 | 文件不存在 |

## 7. 暂不实现

| 功能 | 理由 |
|------|------|
| appendToken 热路径优化 | 需拆分流式状态，架构级改动 |
| scrollIntoView RAF 节流 | 需设计节流策略 |
| 测试重构（导入真实函数） | 大规模改动，独立 RC 处理 |
| cn() 全局替换 | 机械但量大，优先级低 |
| ConversationItemCard memo | 需评估回调稳定性 |
