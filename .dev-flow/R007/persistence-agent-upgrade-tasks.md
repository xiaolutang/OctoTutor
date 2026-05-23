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

# Agent — 后端 任务清单

基于设计报告 `analysis/2026-05-22--R007-persistence-agent-upgrade-backend.md`，拆解后端实现任务。

**全局约束**：
- Python 3.11+，async/await 贯穿
- **前置依赖**：R006 鉴权代码已实施（`get_current_user()` + `fetchWithAuth`），BB005+BB006 依赖 R006 的 user_id 注入
- 现有 `ChatService` + `router.py`（非流式）保持不变，仅改 `stream_router.py` 调用 graph.stream()
- `service.py` 的 `_retrieve()` 方法不搬移，agent/nodes.py 的 retrieve 节点通过依赖注入调用 ChatService._retrieve
- PostgresSaver 用 `AsyncPostgresSaver.from_conn_string()` 内部管理连接池
- 意图分类默认走 textbook（宁可多检索不漏检）
- 暂不实现：rewrite/assess、多对话管理、教学策略量化评估、检索降级前端提示、编辑已发送消息

---

## 执行顺序

1. ⬜ R007-BF002 — 后端配置 + 依赖（无依赖）
2. ⬜ R007-BF001 — Agent 模块骨架 + PostgresSaver 初始化（依赖 BF002）
3. ⬜ R007-BB002 — classify 节点改造（依赖 BF001）
4. ⬜ R007-BB003+BB004 — respond + refuse 节点实现（依赖 BF001）
5. ⬜ R007-BB001 — StateGraph 条件路由编排（依赖 BB002 + BB003+BB004）
6. ⬜ R007-BB005+BB006 — conversation_id + SSE + 对话 API 集成（依赖 BB001）

---

## R007-BF002：config.py + docker-compose + requirements — 配置变更 `✅ 已完成`

- 文件：`backend/app/config.py`、`deploy/docker-compose.local.yml`、`backend/requirements.txt`
- 改动类型：修改 + 配置
- domain: infra
- task_layer: foundation
- depends_on: []
- priority: 4
- risk_tags: []
- smoke_required: false
- mode: direct
- status: pending
- acceptance_criteria:
  - `Settings` 可从环境变量加载 `database_url`
  - `docker-compose.local.yml` 后端服务包含 `DATABASE_URL` 环境变量
  - `pip install -r requirements.txt` 成功安装 langgraph 等新依赖
- test_tasks:
  - type: unit
    description: 验证 Settings.database_url 可从环境变量加载
    scenarios: [设置 DATABASE_URL 环境变量后 assert settings.database_url 正确]
- contract_refs: []
- decision_refs: []
- blocked_files: []

### BF002.1 config.py 新增 database_url 字段 `⬜`

在 `Settings` 类中 `chroma_persist_dir` 之前新增：

```python
# PostgreSQL — LangGraph PostgresSaver 持久化
database_url: str = Field(
    default="postgresql://localhost:5432/octotutor_checkpoints",
    description="PostgreSQL 连接串，用于 LangGraph PostgresSaver",
)
```

### BF002.2 docker-compose.local.yml 新增 DATABASE_URL `⬜`

在 `octotutor-backend` 的 `environment` 中，`JWT_SECRET_KEY` 之后新增：

```yaml
- DATABASE_URL=postgresql://host.docker.internal:5432/octotutor_checkpoints
```

### BF002.3 requirements.txt 新增依赖 `⬜`

在文件末尾新增：

```
# LangGraph Agent 编排 + 消息持久化 (R007)
langgraph>=0.6.0
langchain-core>=0.3.0
langgraph-checkpoint-postgres>=0.2.0
psycopg[binary]>=3.1.0
```

---

## R007-BF001：agent/ 模块 + main.py + dependencies.py — 骨架初始化 `⬜ 待处理`

- 文件：`backend/app/agent/__init__.py`(新建)、`backend/app/agent/graph.py`(新建)、`backend/app/agent/nodes.py`(新建)、`backend/app/agent/prompts.py`(新建)、`backend/app/chat/dependencies.py`(修改)、`backend/app/main.py`(修改)
- 改动类型：新建 + 修改
- domain: backend
- task_layer: foundation
- depends_on: [R007-BF002]
- priority: 4
- risk_tags: [first_use]
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - `python -c "from app.agent.graph import graph"` 无报错
  - FastAPI 启动时打印 `[startup] PostgresSaver initialized` 或 `[startup] MemorySaver fallback`
  - `GET /api/health` 返回 200
- test_tasks:
  - type: unit
    description: 验证 AgentState TypedDict 结构
    scenarios: [构造包含所有字段的 AgentState dict 验证类型正确]
  - type: unit
    description: 验证 graph 可编译
    scenarios: [compile 不抛异常，graph.nodes 包含 classify/retrieve/respond/refuse]
- contract_refs: [.dev-flow/R007/analysis/2026-05-22--R007-persistence-agent-upgrade-backend.md]
- decision_refs: []
- blocked_files: [backend/app/chat/service.py, backend/app/chat/router.py]

### BF001.1 agent/__init__.py 模块初始化 `⬜`

新建空文件：

```python
"""Agent 模块 — LangGraph StateGraph 编排"""
```

### BF001.2 agent/graph.py — AgentState + StateGraph 骨架 `⬜`

定义 AgentState TypedDict 和空 StateGraph（节点为 pass-through stub）：

```python
from typing import TypedDict, Literal, Annotated
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage
from app.rag.models import QueryResult
from app.domain.models import SourceReference


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    question: str
    intent: Literal["textbook", "unrelated"]
    context_chunks: list[QueryResult]
    sources: list[SourceReference]
    degraded: bool
    degradation_reason: str | None


def _route_by_intent(state: AgentState) -> str:
    if state.get("intent") == "textbook":
        return "retrieve"
    return "refuse"


def create_graph(checkpointer=None):
    graph = StateGraph(AgentState)
    # 节点在后续任务中实现，此处先注册 stub
    graph.add_node("classify", lambda state: {})
    graph.add_node("retrieve", lambda state: {})
    graph.add_node("respond", lambda state: {})
    graph.add_node("refuse", lambda state: {})
    graph.add_edge(START, "classify")
    graph.add_conditional_edges("classify", _route_by_intent)
    graph.add_edge("retrieve", "respond")
    graph.add_edge("respond", END)
    graph.add_edge("refuse", END)
    return graph.compile(checkpointer=checkpointer)
```

### BF001.3 agent/nodes.py — 节点 stub 函数 `⬜`

占位实现，返回空 dict（LangGraph 节点返回 dict merge 到 state）：

```python
"""Agent 节点函数 — classify / retrieve / respond / refuse"""


async def classify_node(state: dict) -> dict:
    # 后续 BB002 实现
    return {}


async def retrieve_node(state: dict) -> dict:
    # 后续 BB003 实现
    return {}


async def respond_node(state: dict) -> dict:
    # 后续 BB003 实现
    return {}


def refuse_node(state: dict) -> dict:
    # 后续 BB004 实现
    return {}
```

### BF001.4 agent/prompts.py — 教学策略 prompt 占位 `⬜`

```python
"""教学策略 system prompt"""

TEACHING_SYSTEM_PROMPT = "你是一个课程学习助手，帮助学生理解教材内容。"
# 后续 BB003 完善
```

### BF001.5 chat/dependencies.py — 新增依赖注入 `⬜`

在现有文件末尾新增两个函数：

```python
from langgraph.graph.state import CompiledStateGraph


def get_graph(request: Request) -> CompiledStateGraph:
    return request.app.state.graph


def get_checkpointer(request: Request):
    return request.app.state.checkpointer
```

### BF001.6 main.py — lifespan 初始化 PostgresSaver + graph `⬜`

1. 在文件顶部新增 import：

```python
from app.agent.graph import create_graph
from app.chat.conversation_router import router as conversation_router
```

注意：`conversation_router` 在 BB005 任务中创建，此处先注释掉 import，BB005 完成后取消注释。

2. 在 lifespan 中 `generator` 初始化之后、`yield` 之前新增：

```python
    # 初始化 PostgresSaver（降级为 MemorySaver）
    checkpointer = None
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        checkpointer = AsyncPostgresSaver.from_conn_string(settings.database_url)
        await checkpointer.setup()
        print(f"[startup] PostgresSaver initialized")
    except Exception as e:
        from langgraph.checkpoint.memory import MemorySaver
        checkpointer = MemorySaver()
        print(f"[startup] WARNING: PostgresSaver failed ({e}), using MemorySaver fallback")
    application.state.checkpointer = checkpointer

    # 编译 StateGraph
    graph = create_graph(checkpointer=checkpointer)
    application.state.graph = graph
    print(f"[startup] Agent graph compiled")
```

3. 在 router 注册区域新增（BB005 后取消注释）：

```python
# app.include_router(conversation_router)  # BB005 完成后取消注释
```

---

## R007-BB002：question_classifier.py — classify 节点改造 `⬜ 待处理`

- 文件：`backend/app/chat/question_classifier.py`
- 改动类型：修改
- domain: backend
- task_layer: business
- depends_on: [R007-BF001]
- priority: 3
- risk_tags: []
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - 数学问题返回 `"textbook"`（原 `"retrieval"`）
  - 问候/闲聊/短文本返回 `"unrelated"`（原 `"direct"`）
  - 默认返回 `"textbook"`
  - 现有 `test_question_classifier.py` 测试全部通过（修改预期值）
- test_tasks:
  - type: unit
    description: 验证分类器返回 textbook/unrelated
    scenarios: ["什么是导数" → textbook, "你好" → unrelated, "今天天气" → unrelated, "函数" → textbook, 默认 → textbook]
- contract_refs: []
- decision_refs: []
- blocked_files: []

### BB002.1 question_classifier.py 返回值替换 `⬜`

1. 修改文件头注释：`"retrieval"` → `"textbook"`，`"direct"` → `"unrelated"`
2. `classify_question()` 函数体中所有 `return "retrieval"` 替换为 `return "textbook"`，`return "direct"` 替换为 `return "unrelated"`
3. docstring 同步更新

### BB002.2 agent/nodes.py classify 节点实现 `⬜`

替换 classify_node stub：

```python
from app.chat.question_classifier import classify_question
from langchain_core.messages import HumanMessage


async def classify_node(state: dict) -> dict:
    question = state.get("question", "")
    intent = classify_question(question)
    # thinking payload
    thinking_text = "识别为课程相关问题，准备检索教材" if intent == "textbook" else "识别为非课程问题"
    return {"intent": intent}
```

---

## R007-BB003+BB004：agent/nodes.py + agent/prompts.py — respond + refuse 实现 `⬜ 待处理`

- 文件：`backend/app/agent/nodes.py`、`backend/app/agent/prompts.py`
- 改动类型：修改
- domain: backend
- task_layer: business
- depends_on: [R007-BF001]
- priority: 4
- risk_tags: [network]
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - refuse 节点返回静态拒绝消息 `"我是课程学习助手..."`，不调 LLM
  - respond 节点使用教学策略 prompt 驱动 LLM 流式生成
  - 教学策略 prompt 包含：类比驱动、启发式引导、步骤化叙事、纠正误解、知识关联
- test_tasks:
  - type: unit
    description: refuse_node 返回静态 AIMessage
    scenarios: [输入任意 state → 返回含静态拒绝文本的 dict]
  - type: unit
    description: respond_node 调用 LLM（mock）
    scenarios: [mock generator → 验证 prompt 包含教学策略关键词]
  - type: unit
    description: respond_node LLM 错误处理
    scenarios: [mock generator 抛异常 → SSE error event code=02201/02202/02204]
- contract_refs: [.dev-flow/R007/analysis/2026-05-22--R007-persistence-agent-upgrade-backend.md]
- decision_refs: []
- blocked_files: []

### BB003.1 agent/prompts.py — 教学策略 system prompt `⬜`

完整教学策略 prompt（核心内容，需精心编写）：

```python
TEACHING_SYSTEM_PROMPT = """你是一位耐心、循循善诱的课程学习助手，专注于帮助学生理解教材内容。

## 核心原则
- 绝不直接给出完整答案，而是通过引导让学生自己发现答案
- 每次回答聚焦一个关键概念，避免信息过载
- 使用学生已掌握的知识作为跳板，逐步引入新概念

## 教学策略（按优先级使用）

1. **类比驱动**：用生活中的熟悉场景解释抽象概念（如"导数就像拍照时的快门速度"）
2. **启发式引导**：通过提问引导学生思考（如"你觉得当 x 趋近于 0 时，这个分式会怎样？"）
3. **步骤化叙事**：将复杂问题拆解为清晰的步骤，每步解释为什么这么做
4. **纠正误解**：当学生表述有误时，先肯定合理部分，再指出问题（如"你的直觉是对的，但这里有个细节需要注意..."）
5. **知识关联**：连接不同章节/概念，帮助学生构建知识网络
6. **趣味记忆**：用口诀、谐音、故事等方法帮助记忆关键公式和定理

## 输出格式
- 使用清晰的 Markdown 格式，数学公式用 LaTeX（$...$ 或 $$...$$）
- 引导性提问用加粗标记
- 步骤用编号列表

## 边界
- 如果学生的问题超出课程范围，礼貌说明并回归课程主题
- 如果教材中未找到相关内容，基于自身知识回答并标注"教材中未直接涉及"
"""
```

### BB003.2 agent/nodes.py retrieve 节点 `⬜`

retrieve 节点复用 `ChatService._retrieve()` 逻辑：

```python
from app.domain.models import SourceReference


async def retrieve_node(state: dict) -> dict:
    """复用 ChatService._retrieve 的检索管线"""
    # 从 state 获取检索服务（通过闭包注入）
    # 此处定义签名，实际注入在 graph.py create_graph 中处理
    question = state.get("question", "")
    top_k = 10  # 从 config 获取
    # 调用 ChatService._retrieve() 的逻辑
    # 返回 context_chunks, sources, degraded, degradation_reason
    ...
```

实际实现方式：在 `create_graph()` 中通过闭包捕获 `ChatService` 实例，节点函数作为闭包访问。

### BB003.3 agent/nodes.py respond 节点 `⬜`

```python
from langchain_core.messages import AIMessage


async def respond_node(state: dict) -> dict:
    """教学策略 prompt + LLM 流式生成"""
    question = state.get("question", "")
    chunks = state.get("context_chunks", [])
    # 组装上下文文本
    context_text = "\n\n".join(chunk.text for chunk in chunks) if chunks else ""
    # 调用 LLM（通过闭包注入的 generator）
    # LLM 使用 TEACHING_SYSTEM_PROMPT 作为 system prompt
    # 流式生成由 stream_mode="messages" 自动处理
    # 返回 AIMessage
    ...
```

### BB004.1 agent/nodes.py refuse 节点 `⬜`

```python
from langchain_core.messages import AIMessage

_REFUSE_MESSAGE = "我是课程学习助手，专注于帮你理解教材内容。如果你有课程相关的问题，随时问我！"


def refuse_node(state: dict) -> dict:
    """非课程问题返回静态拒绝消息"""
    return {"messages": [AIMessage(content=_REFUSE_MESSAGE)]}
```

---

## R007-BB001：agent/graph.py — StateGraph 条件路由编排 `⬜ 待处理`

- 文件：`backend/app/agent/graph.py`
- 改动类型：修改
- domain: backend
- task_layer: business
- depends_on: [R007-BB002, R007-BB003+BB004]
- priority: 4
- risk_tags: []
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - `graph.nodes` 包含 classify, retrieve, respond, refuse 四个节点
  - textbook 意图走 classify→retrieve→respond 路径
  - unrelated 意图走 classify→refuse 路径
  - graph.stream() 可执行并产出 events
- test_tasks:
  - type: integration
    description: 端到端 StateGraph 流测试（mock LLM）
    scenarios: [textbook 问题 → 经过 retrieve+respond, unrelated 问题 → 经过 refuse]
- contract_refs: []
- decision_refs: []
- blocked_files: []

### BB001.1 graph.py 替换 stub 为真实节点函数 `⬜`

修改 `create_graph()` 函数：
1. 接收 `chat_service` 参数（用于 retrieve 节点调用 `_retrieve`）和 `generator` 参数（用于 respond 节点调用 LLM）
2. 将 stub lambda 替换为 nodes.py 中的真实函数（通过闭包或 partial 绑定服务实例）
3. 保留条件路由 `_route_by_intent` 不变

关键结构：

```python
def create_graph(checkpointer=None, chat_service=None, generator=None):
    from app.agent.nodes import classify_node, refuse_node
    from app.agent.prompts import TEACHING_SYSTEM_PROMPT

    # 通过闭包绑定服务的节点函数
    async def _retrieve(state):
        # 调用 chat_service._retrieve()
        ...
    async def _respond(state):
        # 调用 generator + TEACHING_SYSTEM_PROMPT
        ...

    graph = StateGraph(AgentState)
    graph.add_node("classify", classify_node)
    graph.add_node("retrieve", _retrieve)
    graph.add_node("respond", _respond)
    graph.add_node("refuse", refuse_node)
    # ... 路由不变
```

### BB001.2 main.py 传入 chat_service 和 generator `⬜`

修改 `create_graph()` 调用：

```python
graph = create_graph(
    checkpointer=checkpointer,
    chat_service=chat_service_instance,  # 需构造
    generator=generator,
)
```

---

## R007-BB005+BB006：schemas + stream_router + conversation_router — SSE 集成 `⬜ 待处理`

- 文件：`backend/app/chat/schemas.py`(修改)、`backend/app/chat/stream_router.py`(修改)、`backend/app/chat/conversation_router.py`(新建)
- 改动类型：修改 + 新建
- domain: backend
- task_layer: business
- depends_on: [R007-BB001]
- priority: 5
- risk_tags: [network]
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - `POST /api/chat/stream` 使用 `graph.stream()` 替代 `service.stream_chat()`
  - SSE 事件包含 thinking 类型，格式 `{"text": "...", "index": N}`
  - `ChatRequest` 包含 `conversation_id: str | None`
  - `GET /api/conversations/current` 返回 200 + messages 或 204
  - `GET /api/conversations/current` 响应的 message 包含 id/role/content/status/sources/thinking_steps/created_at 七个字段
- test_tasks:
  - type: integration
    description: SSE 流式端到端测试
    scenarios: [发送数学问题 → 收到 thinking+status+sources+token+done 事件序列]
  - type: integration
    description: conversation_id 多轮对话
    scenarios: [不传 conversation_id → 自动创建 → 第二次传 ID → 恢复对话]
  - type: integration
    description: GET /api/conversations/current
    scenarios: [有历史 → 200 + messages, 无历史 → 204]
  - type: integration
    description: 非课程问题
    scenarios: [发送闲聊 → refuse 节点返回拒绝消息 → SSE token+done]
- contract_refs: [.dev-flow/R007/analysis/2026-05-22--R007-persistence-agent-upgrade-backend.md]
- decision_refs: []
- blocked_files: [backend/app/chat/service.py, backend/app/chat/router.py]

### BB005.1 schemas.py — ChatRequest + conversation_id + thinking 事件 `⬜`

1. `ChatRequest` 新增字段：

```python
class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000, description="学生问题")
    top_k: int = Field(default=10, ge=3, le=20, description="检索数量")
    conversation_id: str | None = Field(default=None, description="对话 ID，null 时后端自动创建")
```

2. `StreamEvent.type` Literal 新增 `"thinking"`：

```python
@dataclass
class StreamEvent:
    type: Literal["status", "sources", "token", "done", "error", "thinking"]
    data: Any
```

3. 新增 thinking payload：

```python
@dataclass
class ThinkingPayload:
    text: str
    index: int
```

### BB005.2 stream_router.py — 重构为 graph.stream() `⬜`

核心改动：`event_generator()` 从遍历 `service.stream_chat()` 改为遍历 `graph.stream()`：

1. 函数签名改为注入 `graph` 和 `checkpointer`
2. `conversation_id` 为 null 时生成 UUID4，作为 `thread_id`
3. 构造 graph config：`{"configurable": {"thread_id": conversation_id, "user_id": user.user_id}}`
4. 调用 `graph.stream(input, config, stream_mode=["updates", "messages"], version="v2")`
5. 遍历 stream chunk：
   - `type == "updates"` → 根据 node name 转换为 SSE thinking/status/sources
   - `type == "messages"` → 转换为 SSE token
6. 循环结束后 yield SSE done

关键结构：

```python
@router.post("/chat/stream")
async def stream_chat(
    body: ChatRequest,
    http_request: Request,
    graph=Depends(get_graph),
    user: UserContext = Depends(get_current_user),
):
    conversation_id = body.conversation_id or str(uuid4())
    config = {"configurable": {"thread_id": conversation_id, "user_id": user.user_id}}
    input_msg = {"messages": [HumanMessage(content=body.question)], "question": body.question}

    async def event_generator():
        thinking_idx = 0
        try:
            async for chunk in graph.stream(input_msg, config, stream_mode=["updates", "messages"], version="v2"):
                if await http_request.is_disconnected():
                    break
                # 根据 chunk type 转换为 SSE
                ...
            yield sse_event("done", None)
        except Exception:
            yield sse_event("error", make_error(ChatErrorCode.INTERNAL_ERROR))

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

### BB005.3 conversation_router.py — GET /api/conversations/current `⬜`

新建文件：

```python
"""对话历史 API"""
from fastapi import APIRouter, Depends, Response
from langchain_core.messages import HumanMessage, AIMessage

from app.chat.dependencies import get_checkpointer
from app.middleware.auth import UserContext, get_current_user

router = APIRouter(prefix="/api", tags=["conversations"])


@router.get("/conversations/current")
async def get_current_conversation(
    checkpointer=Depends(get_checkpointer),
    user: UserContext = Depends(get_current_user),
):
    # 1. 按 user_id 查找最近的 thread_id
    # 2. checkpointer.aget() 加载 checkpoint
    # 3. 提取 messages 转换为 ApiMessage 格式
    # 4. 有消息 → 200 + {conversation_id, messages}
    #    无消息 → 204
    ...
```

### BB005.4 main.py 取消注释 conversation_router 注册 `⬜`

在 `main.py` 中取消 BB001.6 中的注释行：

```python
app.include_router(conversation_router)
```
