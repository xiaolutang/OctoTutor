---
version: "1.0"
type: tasks
topic: long-context-dialogue
requirement_cycle: R010
workflow:
  evaluate_provider: local
  mode: auto
status: completed
---

# 长对话上下文管理 — 后端任务清单

基于 design.md 设计，将 R010 拆为 6 个任务，纯后端变更，无前端改动。

全局约束：
- 新增节点（summarize/rewrite/retrieve/respond）在 graph.py 中以闭包形式定义，与现有 _retrieve/_respond 一致
- classify/refuse 节点不变（nodes.py 不改）
- LLM 调用统一走 infra/llm.py 的 get_chat_model()
- 所有 prompt 文本常量放 prompts.py
- 评估脚本使用 MemorySaver，不依赖 PostgresSaver
- 参考：`.dev-flow/R010/analysis/2026-05-26--R010-long-context-dialogue.md`（需求分析）
- 参考：`.dev-flow/R010/analysis/2026-05-26--long-context-dialogue-backend.md`（后端设计）

---

## 执行顺序

1. ✅ R010-BF001 — token-budget 纯函数 + 单测（无依赖）
2. ✅ R010-BB001 — summarize 节点闭包 + SUMMARIZE_PROMPT（依赖 BF001）
   - ⬜ BB001.1 AgentState 扩展 conversation_summary
   - ⬜ BB001.2 SUMMARIZE_PROMPT 写入 prompts.py
   - ⬜ BB001.3 _summarize 闭包实现
   - ⬜ BB001.4 summarize 节点单测
3. ✅ R010-BB002 — rewrite 节点闭包 + REWRITE_PROMPT（依赖 BB001）
   - ⬜ BB002.1 AgentState 扩展 rewritten_question
   - ⬜ BB002.2 REWRITE_PROMPT 写入 prompts.py
   - ⬜ BB002.3 _rewrite 闭包实现
   - ⬜ BB002.4 rewrite 节点单测
4. ✅ R010-BB003 — respond 多轮修复 + 图拓扑重构 + SSE 映射（依赖 BB002）
   - ⬜ BB003.1 _retrieve 改为读 rewritten_question
   - ⬜ BB003.2 _respond 重写消息构建逻辑
   - ⬜ BB003.3 图拓扑重构（注册所有节点 + 边）
   - ⬜ BB003.4 stream_router.py 新增 summarize/rewrite SSE 映射
   - ⬜ BB003.5 集成测试 + 回归测试
5. ✅ R010-BB004 — 评估基础设施 + 确定性 Graders（依赖 BB003）
   - ⬜ BB004.1 评估数据集 multi_turn_eval.json
   - ⬜ BB004.2 eval runner 主脚本
   - ⬜ BB004.3 确定性 graders 实现
   - ⬜ BB004.4 Tracked Metrics 采集
   - ⬜ BB004.5 static_analysis + deterministic_tests 集成
6. ✅ R010-BB005 — LLM-as-Judge 评估（依赖 BB004）
   - ⬜ BB005.1 judge_prompts.py（rubric + assertions）
   - ⬜ BB005.2 llm_judge_eval.py 评估主脚本
   - ⬜ BB005.3 完整评估报告生成

---

## R010-BF001：agent/token_budget.py — Token 估算工具 `✅ 已完成`

- 文件：`backend/app/agent/token_budget.py`（新建）+ `backend/tests/test_token_budget.py`（新建）
- 改动类型：新建
- domain: backend
- task_layer: foundation
- depends_on: []
- priority: 5
- risk_tags: []
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - `estimate_tokens("abc") == 4`（len=3 × 1.5 = 4.5 → int → 4）
  - `estimate_tokens("") == 0`
  - `estimate_tokens("中文测试") == 6`（len=4 × 1.5 = 6）
  - TokenBudget 常量值符合设计文档
  - `pytest tests/test_token_budget.py` 全部通过
- test_tasks:
  - type: unit
    description: estimate_tokens 纯函数单元测试
    scenarios: ["空字符串", "纯英文", "纯中文", "混合中英文", "长文本"]
- contract_refs: []
- decision_refs: []
- blocked_files: []

### BF001.1 TokenBudget 配置常量 + estimate_tokens 函数 `⬜`

新建 `backend/app/agent/token_budget.py`：

```python
class TokenBudget:
    CONTEXT_WINDOW = 200_000       # LLM context window 上限
    SUMMARIZE_THRESHOLD = 0.65     # 65% 时触发摘要（130K）
    RESERVED_FOR_RAG = 8_000       # 预留给 RAG context + system prompt
    RESERVED_FOR_OUTPUT = 4_000    # 预留给 LLM 输出
    RECENT_MESSAGES_KEEP = 10      # 摘要时保留最近 10 条消息（5 轮）


def estimate_tokens(text: str) -> int:
    """保守估算文本 token 数（中文 1 字 ≈ 1.5 token）"""
    return int(len(text) * 1.5)
```

### BF001.2 单元测试 `⬜`

新建 `backend/tests/test_token_budget.py`，覆盖：
- estimate_tokens 空字符串 / 纯英文 / 纯中文 / 混合 / 长文本
- TokenBudget 常量值断言（THRESHOLD > 0, RESERVED > 0 等）

---

## R010-BB001：graph.py + prompts.py — summarize 节点 `✅ 已完成`

- 文件：`backend/app/agent/graph.py`（修改）+ `backend/app/agent/prompts.py`（修改）+ `backend/tests/test_agent_nodes.py`（修改）
- 改动类型：修改
- domain: backend
- task_layer: business
- depends_on: [R010-BF001]
- priority: 4
- risk_tags: []
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - AgentState 新增 `conversation_summary: str` 字段
  - SUMMARIZE_PROMPT 写入 prompts.py
  - _summarize 闭包：未超阈值 → return {}；超阈值 → LLM 摘要 + RemoveMessage
  - summarize 未超阈值时 no-op 单测通过
  - summarize 超阈值时生成摘要 + RemoveMessage 单测通过
- test_tasks:
  - type: unit
    description: summarize 节点单元测试
    scenarios: ["未超阈值 no-op", "超阈值生成摘要", "超阈值返回 RemoveMessage", "有旧摘要时合并", "LLM 失败时 no-op"]
- contract_refs: []
- decision_refs: [DEC-rag-010]
- blocked_files: [backend/app/agent/nodes.py]

### BB001.1 AgentState 扩展 `⬜`

在 `graph.py` AgentState 类中新增字段：

```python
class AgentState(dict):
    messages: Annotated[list[BaseMessage], add_messages]
    question: str
    intent: Literal["textbook", "unrelated"]
    context_chunks: list[QueryResult]
    sources: list[SourceReference]
    degraded: bool
    degradation_reason: str | None
    # --- R010 新增 ---
    conversation_summary: str                              # 摘要文本
```

### BB001.2 SUMMARIZE_PROMPT `⬜`

在 `prompts.py` 末尾新增：

```python
SUMMARIZE_PROMPT = """简洁总结以下对话的要点，要求：
1. 保留所有关键数学概念和术语
2. 保留解题步骤的因果链（因为...所以...）
3. 不要引入对话中未出现的信息
4. 输出不超过 300 字

{existing_summary}

对话内容：
{messages_text}

对话要点总结："""
```

### BB001.3 _summarize 闭包 `⬜`

在 `graph.py` create_graph 函数内新增 _summarize 闭包：

```python
from langgraph.graph.message import RemoveMessage
from app.agent.token_budget import TokenBudget, estimate_tokens

async def _summarize(state):
    # 1. 估算总 token：summary + messages + RESERVED
    # 2. 未超阈值 → return {}
    # 3. 超阈值 → 分割：保留最近 RECENT_MESSAGES_KEEP 条，其余为待摘要
    # 4. 构建 LLM 输入：旧摘要（如有）+ 待摘要消息
    # 5. 调用 chat_model.ainvoke 生成摘要
    # 6. 成功 → return {conversation_summary, messages: [RemoveMessage...]}
    # 7. 失败 → return {}（no-op，下轮重试）
```

注意：此阶段只定义闭包，**不注册到 graph**。图拓扑注册在 BB003 完成。

### BB001.4 summarize 节点单测 `⬜`

在 `test_agent_nodes.py` 中新增 summarize 相关测试：
- mock chat_model，测试未超阈值 → `{}`
- mock chat_model 返回摘要，测试超阈值 → `{"conversation_summary": ..., "messages": [RemoveMessage...]}`
- 测试有旧摘要时 LLM 输入包含旧摘要
- 测试 LLM 失败 → `{}`

---

## R010-BB002：graph.py + prompts.py — rewrite 节点 `✅ 已完成`

- 文件：`backend/app/agent/graph.py`（修改）+ `backend/app/agent/prompts.py`（修改）+ `backend/tests/test_agent_nodes.py`（修改）
- 改动类型：修改
- domain: backend
- task_layer: business
- depends_on: [R010-BB001]
- priority: 4
- risk_tags: []
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - AgentState 新增 `rewritten_question: str` 字段
  - REWRITE_PROMPT 写入 prompts.py
  - _rewrite 闭包：首轮（len(messages)<=1）→ return {}；多轮 → LLM 改写
  - rewrite 首轮透传单测通过
  - rewrite 多轮改写单测通过
  - rewrite LLM 失败 fallback 单测通过
- test_tasks:
  - type: unit
    description: rewrite 节点单元测试
    scenarios: ["首轮透传", "多轮改写", "LLM 失败 fallback 原始 question"]
- contract_refs: []
- decision_refs: [DEC-rag-011]
- blocked_files: [backend/app/agent/nodes.py]

### BB002.1 AgentState 扩展 `⬜`

在 AgentState 中新增字段：

```python
    rewritten_question: str                                # 改写后的独立问题
```

### BB002.2 REWRITE_PROMPT `⬜`

在 `prompts.py` 末尾新增：

```python
REWRITE_PROMPT = """基于以下对话历史，将用户的追问改写为一个独立的、完整的问题。
要求：
1. 保留原始问题的数学语义
2. 将代词（它、这个、那个）替换为具体概念
3. 直接输出改写后的问题，不要解释

对话历史：
{history}

用户追问：{question}

改写后的独立问题："""
```

### BB002.3 _rewrite 闭包 `⬜`

在 `graph.py` create_graph 函数内新增 _rewrite 闭包：

```python
async def _rewrite(state):
    messages = state.get("messages", [])
    question = state.get("question", "")
    # 1. len(messages) <= 1 → return {}（首轮透传）
    # 2. 取最近 2-3 轮历史构建 history 文本
    # 3. 调用 chat_model.ainvoke(REWRITE_PROMPT) 改写
    # 4. 成功 → return {rewritten_question: result}
    # 5. 失败 → return {}（fallback 原始 question）
```

注意：此阶段只定义闭包，**不注册到 graph**。

### BB002.4 rewrite 节点单测 `⬜`

在 `test_agent_nodes.py` 中新增 rewrite 相关测试：
- messages 长度 ≤ 1 → `{}`
- messages 长度 > 1 → mock LLM 返回改写结果 → `{"rewritten_question": "..."}`
- LLM 失败 → `{}`

---

## R010-BB003：graph.py + stream_router.py — 多轮修复 + 拓扑重构 `✅ 已完成`

- 文件：`backend/app/agent/graph.py`（修改）+ `backend/app/chat/stream_router.py`（修改）+ `backend/tests/test_agent_graph.py`（修改）+ `backend/tests/test_graph_integration.py`（修改）
- 改动类型：修改
- domain: backend
- task_layer: business
- depends_on: [R010-BB002]
- priority: 5
- risk_tags: []
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - _retrieve 使用 rewritten_question（优先于 question）
  - _respond 构建正确消息列表：[SystemMsg(教学策略+RAG), SystemMsg(摘要)?, ...History, HumanMsg(当前)]
  - 新图拓扑包含 6 个节点：summarize/classify/rewrite/retrieve/respond/refuse
  - _route_by_intent 路由到 rewrite（而非 retrieve）
  - stream_router.py 新增 summarize/rewrite 的 SSE thinking 事件映射
  - `pytest tests/test_agent_graph.py -k "compile"` 通过（图编译）
  - `pytest tests/test_agent_graph.py -k "nodes"` 通过（6 节点）
  - `pytest tests/test_graph_integration.py` 通过（多轮集成测试）
  - 现有单轮对话测试仍通过（pass-to-pass）
  - `pytest tests/test_stream_router.py` 通过（SSE 映射）
- test_tasks:
  - type: integration
    description: 多轮对话集成测试
    scenarios: ["首轮单轮对话不变", "多轮追问历史透传", "summarize 未超阈值 no-op", "rewrite 首轮透传"]
  - type: unit
    description: respond 消息构建测试
    scenarios: ["有 RAG + 无摘要 + 无历史", "有 RAG + 有摘要 + 有历史", "无 RAG + 无历史"]
- contract_refs: []
- decision_refs: [DEC-rag-010, DEC-rag-011]
- blocked_files: [backend/app/agent/nodes.py]

### BB003.1 _retrieve 改用 rewritten_question `⬜`

修改 `_retrieve` 闭包（graph.py:68-83）：

```python
async def _retrieve(state):
    # 优先使用 rewritten_question，无则 fallback 到 question
    question = state.get("rewritten_question") or state.get("question", "")
    # 其余逻辑不变
```

### BB003.2 _respond 重写消息构建逻辑 `⬜`

重写 `_respond` 闭包（graph.py:85-113），修复不传历史的 bug：

```python
async def _respond(state):
    chunks = state.get("context_chunks", [])
    summary = state.get("conversation_summary")
    history = state.get("messages", [])

    # 1. 构建 SystemMessage：教学策略 + RAG context（动态注入）
    system_content = TEACHING_SYSTEM_PROMPT
    if chunks:
        context_text = build_numbered_context(chunks)
        system_content += f"\n\n以下是检索到的教材内容：\n{context_text}\n请基于以上教材内容回答学生的问题。"

    messages = [SystemMessage(content=system_content)]

    # 2. 摘要 SystemMessage（如存在）
    if summary:
        messages.append(SystemMessage(content=f"以下是之前对话的要点总结：\n{summary}"))

    # 3. 历史消息原样透传（summarize 已清理旧消息，只剩近期）
    messages.extend(history)

    # 4. 调用 LLM
    response = await chat_model.ainvoke(messages)
    return {"messages": [response]}
```

### BB003.3 图拓扑重构 `⬜`

修改 `graph.py` create_graph 底部的图构建代码（graph.py:115-125）：

```python
    # 新拓扑：START → summarize → classify → [rewrite → retrieve → respond | refuse] → END
    graph = StateGraph(AgentState)
    graph.add_node("classify", classify_node)
    graph.add_node("summarize", _summarize)     # 新增
    graph.add_node("rewrite", _rewrite)          # 新增
    graph.add_node("retrieve", _retrieve)
    graph.add_node("respond", _respond)
    graph.add_node("refuse", refuse_node)

    graph.add_edge(START, "summarize")            # 改：START → summarize
    graph.add_edge("summarize", "classify")       # 新增
    graph.add_conditional_edges("classify", _route_by_intent)  # 路由改为 rewrite/refuse
    graph.add_edge("rewrite", "retrieve")         # 新增
    graph.add_edge("retrieve", "respond")
    graph.add_edge("respond", END)
    graph.add_edge("refuse", END)
```

修改 `_route_by_intent`（graph.py:45-48）：

```python
def _route_by_intent(state: AgentState) -> str:
    if state.get("intent") == "textbook":
        return "rewrite"    # 改：原为 "retrieve"
    return "refuse"
```

### BB003.4 stream_router.py SSE 映射 `⬜`

在 `_map_node_update_to_sse` 函数（stream_router.py:159-191）中新增两个节点的映射：

```python
    # summarize 节点 — 推送 thinking 事件
    elif node_name == "summarize":
        summary = node_output.get("conversation_summary")
        if summary:
            yield _sse_frame("thinking", {"text": "上下文已压缩", "index": 0})

    # rewrite 节点 — 推送 thinking 事件
    elif node_name == "rewrite":
        rewritten = node_output.get("rewritten_question")
        if rewritten:
            yield _sse_frame("thinking", {"text": f"查询改写: {rewritten}", "index": 1})
```

### BB003.5 集成测试 + 回归测试 `⬜`

**test_agent_graph.py** 改造：
- 图编译测试：验证 6 个节点存在
- 边测试：START→summarize, summarize→classify, classify→rewrite/refuse

**test_graph_integration.py** 改造：
- 多轮对话集成：首轮 → 追问 → 验证历史透传
- summarize no-op 场景：短历史不触发摘要

**回归测试**：确保现有 test_agent_nodes.py 中 classify/refuse 测试仍通过（pass-to-pass）

---

## R010-BB004：eval/ — 评估基础设施 + 确定性 Graders `✅ 已完成`

- 文件：`backend/eval/__init__.py`（新建）+ `backend/eval/multi_turn_eval.py`（新建）+ `backend/eval/graders.py`（新建）+ `backend/eval/datasets/multi_turn_eval.json`（新建）
- 改动类型：新建
- domain: backend
- task_layer: business
- depends_on: [R010-BB003]
- priority: 3
- risk_tags: []
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - 评估数据集包含 23 条用例（16 正面 + 7 负面），覆盖 L1-L4
  - `python -m eval.multi_turn_eval --dataset eval/datasets/multi_turn_eval.json` 可运行
  - state_check 全部通过（首轮 rewritten_question 为 null、summarize 触发后 messages 数量正确等）
  - tool_calls 全部通过（rewrite 首轮未调 LLM、retrieve 用 rewritten_question）
  - transcript 约束通过（首轮不触发 summarize、单轮 ≤ 30s）
  - 确定性粗筛通过（负面用例正确拒绝）
  - Tracked metrics 在基线范围内
  - `ruff check` 无错误
  - `mypy` 无类型错误
  - `pytest tests/` 全部通过（pass-to-pass + fail-to-pass）
- test_tasks:
  - type: integration
    description: 确定性评估端到端运行
    scenarios: ["23条用例全部执行", "负面用例正确拒绝", "tracked metrics 在基线内"]
- contract_refs: []
- decision_refs: []
- blocked_files: [backend/app/agent/graph.py, backend/app/chat/stream_router.py]

### BB004.1 评估数据集 multi_turn_eval.json `⬜`

新建 `backend/eval/datasets/multi_turn_eval.json`，定义 JSON schema 并填充 23 条用例：

```json
[
  {
    "id": "L1-P01",
    "level": "L1",
    "category": "simple_pronoun",
    "negative": false,
    "turns": [
      {"role": "user", "content": "什么是函数？"},
      {"role": "user", "content": "它的定义域怎么求？"}
    ],
    "expected": {
      "rewrite_contains": ["函数", "定义域"],
      "intent": "textbook",
      "summary_triggered": false
    }
  }
]
```

覆盖 L1-L4，每层级按正/负面分配。

### BB004.2 eval runner 主脚本 `⬜`

新建 `backend/eval/multi_turn_eval.py`：
- 读取 JSON 数据集
- 逐条用例执行 agent pipeline（MemorySaver）
- 收集每轮中间产物（state snapshot + timing）
- 调用 graders 逐项验证
- 输出确定性评估报告

### BB004.3 确定性 graders 实现 `⬜`

新建 `backend/eval/graders.py`，实现：
- `state_check(state, expected)` — 验证 AgentState 最终状态
- `tool_calls_check(transcript, expected)` — 验证节点调用行为（通过 LangGraph callback 或 mock 记录）
- `transcript_check(transcript)` — 验证执行轨迹约束
- `deterministic_filter(artifacts, expected)` — 粗筛：关键词断言 + 数量/长度检查

### BB004.4 Tracked Metrics 采集 `⬜`

在 eval runner 中集成：
- n_toolcalls — 每轮 LLM 调用计数
- n_total_tokens — 从 LLM response metadata 提取
- time_to_first_token — 首个 respond token 的时间戳
- time_to_last_token — 全链路耗时

输出 tracked metrics 报告并与基线预期对比。

### BB004.5 static_analysis + deterministic_tests 集成 `⬜`

在 eval 报告中集成：
- `ruff check` 结果
- `mypy` 结果
- `pytest tests/` 结果（pass-to-pass + fail-to-pass 统计）

---

## R010-BB005：eval/ — LLM-as-Judge 评估 `✅ 已完成`

- 文件：`backend/eval/llm_judge_eval.py`（新建）+ `backend/eval/judge_prompts.py`（新建）
- 改动类型：新建
- domain: backend
- task_layer: business
- depends_on: [R010-BB004]
- priority: 2
- risk_tags: []
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - judge_prompts.py 包含 4 个维度的 rubric + assertions prompt
  - LLM Judge 评分含 Unknown=0 退出机制
  - LLM assertions 平均通过率 ≥ 90%
  - L1-L2 场景 Rewrite 质量 rubric ≥ 4 分
  - L3-L4 场景 Rewrite 质量 rubric ≥ 3 分
  - 上下文连贯性 rubric 平均 ≥ 4 分
  - `python -m eval.llm_judge_eval --dataset eval/datasets/multi_turn_eval.json` 可运行
  - 输出完整结构化报告（BB004 确定性结果 + BB005 LLM 结果汇总）
- test_tasks:
  - type: integration
    description: LLM-as-Judge 端到端运行
    scenarios: ["4维度独立评分", "assertions通过率", "报告输出格式"]
- contract_refs: []
- decision_refs: []
- blocked_files: [backend/app/agent/graph.py, backend/app/chat/stream_router.py]

### BB005.1 judge_prompts.py — rubric + assertions `⬜`

新建 `backend/eval/judge_prompts.py`，定义 4 个维度的 Judge prompt：

```python
REWRITE_QUALITY_PROMPT = """评估改写后问题的质量。

评分标准：
5=完美 4=良好 3=可接受 2=较差 1=完全错误 0=Unknown

断言检查（每条通过/不通过）：
1. 改写后包含原始问题中的数学概念
2. 代词已被替换为具体概念
3. 改写后可独立理解，无需对话上下文

对话历史：{history}
原始问题：{question}
改写结果：{rewritten_question}

输出 JSON：{"score": <0-5>, "assertions": [true/false, true/false, true/false], "reasoning": "..."}"""
```

同理定义 RETRIEVAL_RELEVANCE_PROMPT / CONTEXT_COHERENCE_PROMPT / SUMMARY_FIDELITY_PROMPT。

### BB005.2 llm_judge_eval.py 评估主脚本 `⬜`

新建 `backend/eval/llm_judge_eval.py`：
- 读取 BB004 产出的中间产物数据
- 对每个维度调独立 LLM Judge 打分
- 解析 JSON 输出（score + assertions + reasoning）
- 汇总各维度平均分 + assertions 通过率

### BB005.3 完整评估报告生成 `⬜`

输出结构化报告，包含：
- BB004 确定性结果（state_check / tool_calls / transcript / static_analysis / deterministic_tests / tracked metrics）
- BB005 LLM 结果（4 维度 rubric 得分 + assertions 通过率）
- 总体评分 + 是否达标
