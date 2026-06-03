---
version: "1.0"
type: tasks
topic: code-quality-governance
requirement_cycle: R013
workflow:
  evaluate_provider: local
  mode: auto
status: archived
---

# 代码质量治理 — 任务清单

全局约束：纯重构任务，不改变任何用户可见行为。

---

## 执行顺序

1. ✅ BF001 — 提取对话工具函数到共享模块（无依赖）
2. ✅ FF001 — 提取 conversationReducer 到独立文件（无依赖）
3. ✅ FF002 — 提取 SSE 事件分发共享函数（无依赖）
4. ✅ FF003 — 重写 controller-race-condition 测试（依赖 FF001）

---

## R013-BF001：提取对话工具函数到 conversation_utils.py `✅ 已完成`

- 文件：`backend/app/chat/conversation_utils.py`（新建）、`backend/app/chat/conversation_router.py`（修改）、`backend/app/chat/stream_router.py`（修改）
- 改动类型：新建 + 修改
- domain: backend
- task_layer: foundation
- depends_on: []
- priority: 4
- risk_tags: []
- smoke_required: false
- mode: direct
- status: pending
- acceptance_criteria:
  - conversation_utils.py 包含 load_conversation_by_id 和 to_api_message 公共函数
  - conversation_router.py 和 stream_router.py 从 conversation_utils 导入
  - 无跨路由私有函数导入
  - 后端测试全部通过
- test_tasks:
  - type: integration
    description: 验证 resume_stream 端点仍正常返回消息
    scenarios: ["resume 返回 JSON 消息列表", "resume 返回 SSE 流"]
- contract_refs: []
- decision_refs: []
- blocked_files: []

### BF001.1 新建 conversation_utils.py `⬜`

从 conversation_router.py 移出 `_load_conversation_by_id` 和 `_to_api_message`，去掉下划线前缀，添加 docstring 标注公共 API。

```python
# app/chat/conversation_utils.py
async def load_conversation_by_id(...):
    """从 checkpoint 加载对话消息（公共 API）"""
    ...

def to_api_message(...):
    """转换消息为 API 格式（公共 API）"""
    ...
```

### BF001.2 更新 conversation_router.py 导入 `⬜`

```python
# 旧：函数定义在文件内
# 新：
from app.chat.conversation_utils import load_conversation_by_id, to_api_message
```

### BF001.3 更新 stream_router.py 导入 `⬜`

```python
# 旧：from app.chat.conversation_router import _load_conversation_by_id, _to_api_message
# 新：from app.chat.conversation_utils import load_conversation_by_id, to_api_message
```

---

## R013-FF001：提取 conversationReducer 到独立文件 `✅ 已完成`

- 文件：`frontend/src/chat/conversation-reducer.ts`（新建）、`frontend/src/contexts/conversation-context.tsx`（修改）、`frontend/src/__tests__/contexts/conversation-context.test.tsx`（修改）
- 改动类型：新建 + 修改
- domain: ui
- task_layer: foundation
- depends_on: []
- priority: 4
- risk_tags: []
- smoke_required: false
- mode: direct
- status: pending
- acceptance_criteria:
  - conversation-reducer.ts 包含 ConversationAction、conversationReducer、initialState、STORAGE_KEY、getStoredActiveId、storeActiveId
  - conversation-context.tsx 从 conversation-reducer.ts 导入
  - conversation-context.test.tsx 从 conversation-reducer.ts 导入真实 reducer
  - 测试用例匹配真实行为（INSERT_NEW 分区、REMOVE_ITEM 自动切换、UPDATE_ITEM 重排序）
  - 前端测试全部通过
- test_tasks:
  - type: unit
    description: 验证 INSERT_NEW 分区逻辑
    scenarios: ["置顶区后插入新项", "新项 activeId 正确设置"]
  - type: unit
    description: 验证 REMOVE_ITEM 自动切换
    scenarios: ["删除当前活跃项 → 切换到第一项", "删除唯一项 → activeId=null"]
  - type: unit
    description: 验证 UPDATE_ITEM 重排序
    scenarios: ["置顶更新后移到置顶区顶部", "取消置顶后移到普通区顶部"]
- contract_refs: []
- decision_refs: []
- blocked_files: []

### FF001.1 新建 conversation-reducer.ts `⬜`

从 conversation-context.tsx 移出：ConversationAction 类型、conversationReducer 函数、initialState 常量、STORAGE_KEY、getStoredActiveId、storeActiveId。

### FF001.2 更新 conversation-context.tsx 导入 `⬜`

```typescript
import { conversationReducer, initialState, ... } from '@/chat/conversation-reducer';
```

### FF001.3 更新测试文件 `⬜`

删除复制的 reducer/类型/initialState（第 22-122 行），改为 import 真实 reducer。
更新 INSERT_NEW/REMOVE_ITEM/UPDATE_ITEM 测试用例以匹配真实行为。

---

## R013-FF002：提取 SSE 事件分发共享函数 `✅ 已完成`

- 文件：`frontend/src/chat/use-chat-stream.ts`（修改）
- 改动类型：修改
- domain: ui
- task_layer: foundation
- depends_on: []
- priority: 3
- risk_tags: []
- smoke_required: false
- mode: direct
- status: pending
- acceptance_criteria:
  - handleSSEEvent 函数处理 status/sources/thinking/token/done/error 公共事件
  - chatStreamFetch 和 resumeStream 都调用 handleSSEEvent
  - chatStreamFetch 额外处理 init/title
  - 前端测试全部通过
- test_tasks:
  - type: unit
    description: 验证 handleSSEEvent 正确分发各事件类型
    scenarios: ["status 事件", "token 事件", "done 事件", "error 事件"]
- contract_refs: []
- decision_refs: []
- blocked_files: []

### FF002.1 提取 handleSSEEvent `⬜`

```typescript
type BaseSSECallbacks = {
  onStatus: (stage: string, message: string) => void;
  onSources: (sources: SourceReference[]) => void;
  onToken: (token: string) => void;
  onThinking: (step: ThinkingStep) => void;
  onDone: () => void;
  onError: (error: { code: string; message: string; action: string }) => void;
};

function handleSSEEvent(event: { type: string; data: unknown }, callbacks: BaseSSECallbacks): void {
  switch (event.type) {
    case 'status': callbacks.onStatus(...); break;
    case 'sources': callbacks.onSources(...); break;
    case 'thinking': callbacks.onThinking(...); break;
    case 'token': callbacks.onToken(...); break;
    case 'done': callbacks.onDone(); break;
    case 'error': callbacks.onError(...); break;
  }
}
```

### FF002.2 替换 chatStreamFetch 和 resumeStream 中的 switch-case `⬜`

chatStreamFetch 的 onEvent 改为：
```typescript
onEvent: (event) => {
  firstEventReceived = true;
  switch (event.type) {
    case 'init': callbacks.onInit(...); break;
    case 'title': callbacks.onTitle(...); break;
    default: handleSSEEvent(event, callbacks);
  }
}
```

resumeStream 的 onEvent 改为：
```typescript
onEvent: (event) => {
  firstEventReceived = true;
  handleSSEEvent(event, callbacks);
}
```

---

## R013-FF003：重写 controller-race-condition 测试 `✅ 已完成`

- 文件：`frontend/src/__tests__/chat/controller-race-condition.test.ts`（重写）
- 改动类型：修改
- domain: ui
- task_layer: foundation
- depends_on: ['R013-FF001']
- priority: 3
- risk_tags: []
- smoke_required: false
- mode: direct
- status: pending
- acceptance_criteria:
  - 测试使用 renderHook 测试真实 useChatController
  - 覆盖 init useEffect（含 needsResumePlaceholder 逻辑）
  - 覆盖 SSE 重连触发条件
  - 覆盖新对话清空消息
  - 覆盖 activeId 切换时重新加载
  - 前端测试全部通过
- test_tasks:
  - type: unit
    description: 验证 init useEffect 等待 Auth + Conv 就绪
    scenarios: ["Auth 未就绪不加载", "Conv 未就绪不加载", "两者就绪后加载"]
  - type: unit
    description: 验证 needsResumePlaceholder 逻辑
    scenarios: ["最后一条是用户消息且 2 分钟内 → 追加 AI 占位", "超过 2 分钟 → 不追加"]
  - type: unit
    description: 验证新对话清空消息
    scenarios: ["activeId=null + isNewConversation=true → 清空"]
- contract_refs: []
- decision_refs: []
- blocked_files: []
