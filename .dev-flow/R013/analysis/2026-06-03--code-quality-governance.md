---
type: analysis
status: analyzed
requirement_cycle: R013
topic: code-quality-governance
date: 2026-06-03
---

# 代码质量治理 — 三轮 simplify 残留问题修复

## 概述

三轮 simplify 审查共修复 10 项收敛问题，残留 5 项超出收敛范围的重构级问题。本 RC 负责处理其中 4 项（第 5 项 isStreaming 双源状态经评估为架构合理设计，不处理）。

这些问题不涉及用户可见功能变化，全部是内部代码质量改进：测试真实性、模块边界合规、代码去重。

## 一、交互链

无用户可见交互。全部是开发者侧改动。

## 二、逻辑树

### 修复项一览

| # | 问题 | 影响范围 | 风险 |
|---|------|---------|------|
| 1 | 测试复制 reducer 已分歧 | 前端测试 | 测试通过但真实行为可能不一致 |
| 2 | SSE switch-case 重复 | 前端 use-chat-stream.ts | 维护成本，修改一处容易遗漏另一处 |
| 3 | 跨路由私有函数导入 | 后端 stream_router.py | conversation_router 重构时意外破坏 |
| 4 | 测试重实现逻辑 | 前端 controller-race-condition.test.ts | 零耦合，完全无法检测真实 bug |

### 事件流：各修复项的处理逻辑

#### 问题 1：测试复制 reducer

| 时刻 | 事件 | 处理 | 产生的新事件 |
|------|------|------|-------------|
| 1 | conversation-context.tsx 无法直接 import（依赖 auth-context → auth-sdk-web broken symlink） | 提取 reducer + types + initialState 到独立文件 `conversation-reducer.ts` | conversation-context.tsx import reducer |
| 2 | 测试文件 import 真实 reducer | 测试断言验证真实行为 | INSERT_NEW 分区逻辑、REMOVE_ITEM 自动切换、UPDATE_ITEM 重排序被覆盖 |

分歧详情：
- **INSERT_NEW**: 测试用 `[payload, ...items]`，真实代码区分 `pinned/normal` 分区
- **REMOVE_ITEM**: 测试只 `filter`，真实代码额外计算 `newActiveId` + `storeActiveId`
- **UPDATE_ITEM**: 测试只 `map` 替换，真实代码按 pinned 状态重排序

#### 问题 2：SSE switch-case 重复

| 时刻 | 事件 | 处理 | 产生的新事件 |
|------|------|------|-------------|
| 1 | chatStreamFetch 和 resumeStream 各有一套事件分发 switch | 提取 `handleSSEEvent(event, callbacks)` 共享函数 | 两处调用共享函数，各自补充特有事件（init/title） |

注意：两处回调接口不同（`SSECallbacks` vs `ResumeCallbacks`）。共享函数只处理公共事件（status/sources/thinking/token/done/error），init/title 由 chatStreamFetch 额外处理。

#### 问题 3：跨路由私有函数导入

| 时刻 | 事件 | 处理 | 产生的新事件 |
|------|------|------|-------------|
| 1 | stream_router.py 导入 conversation_router 的 `_load_conversation_by_id` 和 `_to_api_message` | 提取到 `app/chat/conversation_utils.py` 共享模块 | stream_router 和 conversation_router 均从共享模块 import |

#### 问题 4：测试重实现逻辑

| 时刻 | 事件 | 处理 | 产生的新事件 |
|------|------|------|-------------|
| 1 | controller-race-condition.test.ts 手写模拟函数，零 import | 用 `renderHook` + mock 依赖测试真实 `useChatController` | init useEffect（含 needsResumePlaceholder）、SSE 重连逻辑被真实覆盖 |

前提：需 mock `useChatStream`、`useConversation`、`useAuth`、`useConversationContext` 四个依赖。

## 三、功能编号与网络定位

### 本次新增节点

| 编号 | 功能节点 | 前缀含义 | 简介 |
|------|---------|---------|------|
| FF001 | Reducer 提取 | 前端基础 | 将 conversationReducer 提取为独立模块，解除对 auth-context 的编译依赖 |
| FF002 | SSE 事件分发去重 | 前端基础 | 提取共享 handleSSEEvent 函数 |
| BF001 | 对话工具函数提取 | 后端基础 | 将 _load_conversation_by_id 和 _to_api_message 提取到共享模块 |
| FF003 | Controller 测试重写 | 前端基础 | 用 renderHook 测试真实 useChatController |

### 前置依赖

| 依赖节点 | 依赖方式 | 是否已有 |
|----------|---------|---------|
| conversation-context.tsx | 重构源（FF001 从中提取） | 已有 |
| use-chat-stream.ts | 重构源（FF002 从中提取） | 已有 |
| conversation_router.py | 重构源（BF001 从中提取） | 已有 |
| vitest + @testing-library/react | 测试框架（FF003 需要 renderHook） | 已有 |

### 边界接口

| 接口/协议 | 定义方 | 消费方 | 敏感度 |
|-----------|--------|--------|--------|
| conversationReducer | conversation-reducer.ts（新） | conversation-context.tsx, test | 低（纯函数） |
| handleSSEEvent | use-chat-stream.ts 内部 | chatStreamFetch, resumeStream | 低（内部函数） |
| load_conversation_by_id | conversation_utils.py（新） | stream_router, conversation_router | 中（数据库访问） |
| to_api_message | conversation_utils.py（新） | stream_router, conversation_router | 低（数据转换） |

## 四、结论

- **开发顺序**：BF001 → FF001 → FF002 → FF003（先后端再前端，先基础再业务）
- **复杂度集中**：FF003（测试重写）需要 mock 4 个依赖 + renderHook，工作量最大
- **暂不实现**：isStreaming 双源状态（LOW，架构合理）
- **风险评估**：BF001 和 FF001 是纯提取/移动，风险最低；FF002 有少量逻辑适配；FF003 工作量最大但只改测试不改源码
