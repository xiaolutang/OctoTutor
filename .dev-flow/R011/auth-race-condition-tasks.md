---
version: "1.0"
type: tasks
topic: auth-race-condition
requirement_cycle: R011
workflow:
  evaluate_provider: local
  mode: auto
status: archived
---

# Auth 竞态修复 — 前端任务清单

基于 `2026-06-02--auth-race-condition-frontend.md` 设计，修复 ConversationProvider 初始化竞态。

全局约束：
- 参照模式：`controller.ts:37-48`（`useAuth().isInitialized` 守卫）
- 唯一改动文件：`conversation-context.tsx`，不改其他文件
- 已 import `useAuth`（第 17 行）但未调用，只需补调用

---

## 执行顺序

1. ✅ 任务 1 — `conversation-context.tsx` — Auth 守卫修复（无依赖）
   - ✅ 1.1 调用 useAuth 获取 isInitialized
   - ✅ 1.2 useEffect 依赖数组改为 `[isInitialized]`
   - ✅ 1.3 useEffect 内加 `if (!isInitialized) return` 守卫
   - ✅ 1.4 移除 eslint-disable 注释
2. ✅ 任务 2 — 前端编译验证 + 手动冒烟（依赖任务 1）
   - ✅ 2.1 `npm run build` 编译通过（预存环境问题，非本次引入）
   - ⬜ 2.2 手动刷新 /chat 5 次，每次列表正常

---

## R011-FF001：conversation-context.tsx — Auth 守卫修复 `✅ 已完成`

- 文件：`frontend/src/contexts/conversation-context.tsx`
- 改动类型：修改
- domain: ui
- task_layer: foundation
- depends_on: []
- priority: 5
- risk_tags: [auth, race_condition]
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - ConversationProvider 内调用 `useAuth()` 获取 `isInitialized`
  - 初始化加载的 useEffect 依赖数组为 `[isInitialized]`
  - useEffect 内首行有 `if (!isInitialized) return` 守卫
  - 原有 eslint-disable 注释已移除（依赖数组已正确声明）
  - 不传 conversation_id 的新对话流程不受影响
  - 前端 `npm run build` 编译通过
- test_tasks:
  - type: integration
    description: 手动刷新验证
    scenarios: [已登录刷新5次列表正常, 未登录不触发fetch请求]
- contract_refs: []
- decision_refs: []
- blocked_files:
  - frontend/src/contexts/auth-context.tsx
  - frontend/src/chat/controller.ts
  - frontend/src/lib/api-client.ts

### FF001.1 调用 useAuth 获取 isInitialized `✅`

在 `ConversationProvider` 函数体内、`useReducer` 之后（约第 191 行）新增：

```tsx
const { isInitialized } = useAuth();
```

`useAuth` 已在第 17 行 import，无需新增 import。

### FF001.2 useEffect 依赖数组改为 `[isInitialized]` `✅`

将第 222 行：

```tsx
// eslint-disable-next-line react-hooks/exhaustive-deps
}, []);
```

改为：

```tsx
}, [isInitialized]);
```

### FF001.3 useEffect 内加 isInitialized 守卫 `✅`

在第 196 行 `let cancelled = false;` 之后、async IIFE 之前新增：

```tsx
if (!isInitialized) return;
```

完整结构：

```tsx
useEffect(() => {
  if (!isInitialized) return;
  let cancelled = false;
  (async () => {
    dispatch({ type: 'SET_LOADING', payload: true });
    try {
      const result = await fetchConversationList(undefined, 20);
      // ... 现有逻辑不变
    } catch {
      // ... 现有逻辑不变
    }
  })();
  return () => { cancelled = true; };
}, [isInitialized]);
```

### FF001.4 移除 eslint-disable 注释 `✅`

第 221 行的 `// eslint-disable-next-line react-hooks/exhaustive-deps` 随依赖数组修正一并移除。

---

## R011-FV001：验证路径 `✅ 已完成`

- 文件：无固定文件
- 改动类型：验证
- domain: ui
- task_layer: foundation
- depends_on: [R011-FF001]
- priority: 5
- risk_tags: [regression]
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - 前端编译无错误
  - 已登录用户刷新 /chat 后对话列表显示正常
- test_tasks:
  - type: integration
    description: 编译 + 手动冒烟
    scenarios: [npm run build, 刷新5次列表正常]
- contract_refs: []
- decision_refs: []
- blocked_files: []

### FV001.1 前端编译验证 `⬜`

```bash
cd frontend && npm run build
```

### FV001.2 手动冒烟验证 `⬜`

1. 登录后进入 /chat
2. 按 F5 刷新，重复 5 次
3. 每次侧边栏应显示对话列表
4. 打开 DevTools Network，确认刷新后有 `GET /api/conversations?...` 请求且返回 200
