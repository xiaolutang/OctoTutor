---
type: analysis
status: analyzed
requirement_cycle: R015
topic: code-convergence
date: 2026-06-04
---

# R015 代码收敛 — 全项目 simplify 审查发现处理

## 概述

R014 归档后，对全项目执行了一次 6 视角 simplify 并行审查（代码复用/代码质量/效率/架构/测试/设计一致性），共发现 125 个问题（26 HIGH / 52 MEDIUM / 47 LOW）。

本次需求包（R015）的目标：**按优先级处理可直接收敛的问题，将需要重构的问题记录到 backlog**。

处理原则：收敛不是重构。只做高确定性的机械修复，不做架构变更。

## 一、问题分类与处理决策

### 处理方式定义

| 方式 | 含义 | 触发条件 |
|------|------|---------|
| 直接修复 | R015 内完成，不改设计 | 机械替换、死代码清理、工具函数提取 |
| 记录 backlog | 后续独立 RC 处理 | 需要设计变更、架构调整、大规模测试重构 |
| 忽略 | 当前可接受 | 影响极小、改动成本高于收益 |

### 第一批：直接修复（6 项）

均为跨 Agent 重复发现的共性问题，改动确定、影响可控。

#### FF001：rehypePlugins 提取为模块常量

**来源**：Agent 3 MEDIUM, Agent 1 间接

**现状**：`message-bubble.tsx:82` 在 JSX 中 `rehypePlugins={[[rehypeKatex, { throwOnError: false }]]}`，每次渲染创建新数组。而 `remarkPlugins` 已正确提取为模块顶层常量（行 25）。

**改动**：在 `remarkPlugins` 下方添加 `const rehypePlugins = [[rehypeKatex, { throwOnError: false }]] as const;`，JSX 中引用此常量。

**影响**：1 文件 2 行，纯优化，无功能变化。

#### FF002：createId 提取到共享 utils

**来源**：Agent 1 HIGH, Agent 5 HIGH

**现状**：`createId()` 函数在 `controller.ts:9-11` 定义，被 4 个测试文件复制（`controller-conversation.test.ts:23`、`chat-ui.test.tsx:46`、`conversation-context.test.tsx:26`、`conversation-sidebar.test.tsx:25`）。

**改动**：
1. 将 `createId()` 从 `controller.ts` 移到 `lib/utils.ts`
2. `controller.ts` 改为 `import { createId } from '@/lib/utils'`
3. 测试文件改为 `import { createId } from '@/lib/utils'`

**影响**：6 文件，删除 ~20 行重复代码，添加 1 个 import。

#### FF003：partitionByPinned 工具函数

**来源**：Agent 1 HIGH, Agent 2 MEDIUM, Agent 3 LOW（三 Agent 共识）

**现状**：`items.filter(pinned)` + `items.filter(!pinned)` 双重遍历出现在：
- `conversation-reducer.ts:96-97`（INSERT_NEW）
- `conversation-reducer.ts:138-143`（UPDATE_ITEM，两次）
- `conversation-sidebar.tsx:33-34`（每次渲染）

**改动**：在 `conversation-reducer.ts` 中提取 `partitionByPinned(items)` → `{ pinned, normal }`，reducer 内部使用。sidebar 的 useMemo 在 FF004 一起处理。

**影响**：2 文件，减少 6 次 filter 调用为 3 次 partition。

#### FF004：ConversationItemCard props 简化

**来源**：Agent 2 HIGH

**现状**：`conversation-sidebar.tsx:67-78` 和 `84-95` 两处完全相同的 8 个 props 传递。同时 `onPin`/`onUnpin` 可以合并为 `onTogglePin`。

**改动**：
1. sidebar 中提取 `const cardProps = { onSelect: switchTo, onRename: renameConversation, ... }` 然后 spread
2. `ConversationItemCard` 的 `onPin`/`onUnpin` 合并为 `onTogglePin(id: string, pinned: boolean)`

**影响**：2 文件，减少 props 接口复杂度，消除重复传递。

#### BF001：llm.py 遗留代码清理

**来源**：Agent 1 HIGH, Agent 4 MEDIUM（两 Agent 共识）

**现状**：`infra/llm.py:21-30` 定义了 `SYSTEM_PROMPT` 和 `MATH_JUDGE_PROMPT`。当前主流程走 Agent Graph（`agent/prompts.py` 的 `TEACHING_SYSTEM_PROMPT`），llm.py 中这两个 Prompt 只被非流式 `generate()` 和 `generate_stream()` 方法使用。这两个方法是遗留路径（`/api/chat` 非流式端点），Graph 主流程不经过。

**改动**：
1. 确认非流式 `/api/chat` 端点是否还在使用（如果死路由则整体清理）
2. 如果还在用，将 llm.py 的 SYSTEM_PROMPT 改为从 `agent/prompts.py` 导入
3. 删除 `generate_stream` 方法（无调用路径）
4. 删除 `test_llm_generator_stream.py`（整个文件测试 generate_stream）
5. 清理 `_helpers.py`、`test_graph_integration.py`、`test_router_auth_integration.py` 中的 generate_stream mock

**影响**：6 文件（含 1 个整文件删除），消除死代码和失效测试。

#### FF005：ChatInput disabled 冗余 prop

**来源**：Agent 2 HIGH

**现状**：`chat-ui.tsx:65-67` 传入 `isStreaming={isStreaming} disabled={isStreaming}`，两个 prop 始终相同。

**改动**：移除 `disabled` prop，ChatInput 内部统一使用 `isStreaming` 控制禁用。

**影响**：2 文件（chat-ui.tsx + chat-input.tsx），净减 1 个 prop。

### 第二批：记录 backlog（需设计变更）

| 问题 | 来源 | 记录理由 |
|------|------|---------|
| appendToken 逐 token 全量重渲染 | Agent 3 HIGH | 需拆分流式状态为独立 state，架构级改动 |
| scrollIntoView 每 token 触发 | Agent 3 MEDIUM | 需 RAF 节流或 IntersectionObserver |
| _active_graphs 无过期清理 | Agent 3 HIGH | 需设计定期清理策略 |
| summarize/rewrite 串行可并行 | Agent 3 MEDIUM | Graph 拓扑变更 |
| 测试中复制源码逻辑（9 处） | Agent 5 HIGH × 9 | 大规模测试重构，需提取纯函数 |
| 无效/冗余测试删除 | Agent 5 MEDIUM × 7 | 需逐个评估测试价值 |
| AuthContext value useMemo | Agent 3 MEDIUM | 影响面较大 |
| ConversationItemCard memo | Agent 3 LOW | 需评估回调引用稳定性 |
| cn() 全局替换 | Agent 2 MEDIUM × 9 | 机械但量大，优先级低 |

### 第三批：忽略（当前可接受）

| 问题 | 理由 |
|------|------|
| BM25 静态索引启动加载 | architecture.md 已标注为设计决策 |
| to_thread 同步 retrieve | 当前并发量低，改造为 async 成本高 |
| fetchWithAuth async getToken | 开销极小（微任务调度） |
| handleScroll 无节流 | 计算轻量，列表小 |
| RRF fusion sorted | 结果集 <20，O(n log n) 可忽略 |
| load_conversation_by_id 全量反序列化 | LangGraph checkpoint 机制限制 |
| SSE 5 秒断连检测 | 合理的超时值 |

## 二、逻辑树

### 事件流：代码收敛处理

| 时刻 | 事件 | 处理 | 产生的新事件 |
|------|------|------|-------------|
| T0 | simplify 6 Agent 完成 | 汇总 125 个发现 | 问题清单 |
| T1 | 按收敛原则分类 | P0 直接修复 / P1 backlog / P2 忽略 | 分类结果 |
| T2 | 执行 FF001-BF001 | 6 个收敛项逐个修复 | 代码变更 |
| T3 | 运行测试 | `npm test` + `pytest` | 通过/失败 |
| T4 | 记录 backlog | 剩余问题写入 backlog.md | backlog 条目 |
| T5 | 归档 R015 | summary + config 更新 | 归档完成 |

### 状态流转

| 实体 | 触发事件 | 前状态 | 后状态 |
|------|---------|--------|--------|
| 问题清单 | T1 分类 | 未分类 | P0/P1/P2 |
| FF001-FF005, BF001 | T2 修复 | pending | completed |
| backlog.md | T4 记录 | 无条目 | 9 条待办 |
| R015 | T5 归档 | active | archived |

## 三、功能编号与网络定位

### 本次新增节点

| 编号 | 功能节点 | 前缀含义 | 简介 |
|------|---------|---------|------|
| FF001 | rehypePlugins 常量提取 | 前端基础 | 消除渲染时数组重建 |
| FF002 | createId 共享函数 | 前端基础 | 消除 5 处重复 ID 生成 |
| FF003 | partitionByPinned 工具函数 | 前端基础 | 消除 reducer/sidebar 重复 filter |
| FF004 | ConversationItemCard props 简化 | 前端业务 | 合并 onPin/onUnpin + spread props |
| FF005 | ChatInput disabled 清理 | 前端业务 | 移除冗余 disabled prop |
| BF001 | llm.py 遗留代码清理 | 后端基础 | 删除死 generate_stream + 测试文件级联清理 |

### 前置依赖

| 依赖节点 | 依赖方式 | 是否已有 |
|----------|---------|---------|
| lib/utils.ts | 函数定义 | 已有（cn 函数） |
| agent/prompts.py | Prompt 定义 | 已有（TEACHING_SYSTEM_PROMPT） |
| chat-input.tsx | isStreaming prop | 已有 |

### 边界接口

| 接口/协议 | 定义方 | 消费方 | 敏感度 |
|-----------|--------|--------|--------|
| createId() | lib/utils.ts | controller.ts + 4 个测试文件 | 低 |
| partitionByPinned(items) | conversation-reducer.ts | reducer 内部 + sidebar | 低 |
| onTogglePin(id, pinned) | ConversationItemCard | conversation-sidebar | 低 |

## 四、结论

- **开发顺序**：FF002（createId）→ FF003（partitionByPinned）→ FF004（props 简化）→ FF005（disabled 清理）→ FF001（rehypePlugins）→ BF001（llm.py 清理）。先做前端基础（工具函数），再做前端业务（组件），最后做后端。
- **复杂度集中**：FF004 的 onPin/onUnpin 合并涉及接口变更，需要同步改 ConversationItemCard 内部逻辑和 sidebar 的调用方式。
- **暂不实现**：appendToken 热路径优化、scrollIntoView 节流、测试重构、Graph 并行化等 9 项，记录 backlog 后续处理。
- **architecture.md 影响**：无。本次收敛不涉及架构约束变更。
