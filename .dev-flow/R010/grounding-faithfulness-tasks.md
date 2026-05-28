---
version: "1.0"
type: tasks
topic: grounding-faithfulness
requirement_cycle: R010
workflow:
  evaluate_provider: local
  mode: auto
status: completed
---

# LLM 忠实性与接地性修复 — 后端任务清单

基于 [设计文档](analysis/2026-05-28--grounding-faithfulness-fix-backend.md) 拆解。

全局约束：
- 不改变 StateGraph 拓扑（不加新节点）
- SSE 事件格式不变
- 不新增第三方依赖
- 不改动前端代码

---

## 执行顺序

1. ✅ R010-BF001 — config.py 新增 RELEVANCE_THRESHOLD（无依赖）
2. ✅ R010-BF002 — prompts.py TEACHING_SYSTEM_PROMPT 加忠实性约束（无依赖）
3. ✅ R010-BB001 — graph.py respond 节点分级注入逻辑（依赖 BF001, BF002）
4. ✅ R010-BB002 — test_agent_nodes.py + test_graph_integration.py 补测试（依赖 BB001）
5. ✅ R010-BB003 — eval 数据集 + GROUNDING_PROMPT + grounding 评估测试（依赖 BB001）
6. ✅ R010-BB004 — architecture.md 更新 DEC-rag-014/015 + 不变量（依赖 BB001）

---

## R010-BF001：config.py — 新增 RELEVANCE_THRESHOLD 配置 `✅ 已完成`

- 文件：`backend/app/config.py`
- 改动类型：修改
- domain: backend
- task_layer: foundation
- depends_on: []
- priority: 5
- risk_tags: []
- smoke_required: false
- mode: direct
- status: pending
- acceptance_criteria:
  - Settings 类包含 `relevance_threshold` 字段，默认值 0.5
  - `from app.config import settings` 后 `settings.relevance_threshold` 可正常访问
  - 现有测试全部通过
- test_tasks:
  - type: unit
    description: 验证 relevance_threshold 默认值和可配置性
    scenarios: [默认值 0.5, 环境变量覆盖]
- contract_refs: []
- decision_refs: [DEC-rag-014]
- blocked_files: []

### BF001.1 新增 relevance_threshold 字段 `⬜`

在 `rerank_top_n` / `rerank_model` 配置块下方新增：

```python
# R010: Context 相关性阈值（reranker score）
relevance_threshold: float = 0.50
```

位置：`app/config.py` 约第 66 行，`chat_max_context_tokens` 之后。

---

## R010-BF002：prompts.py — TEACHING_SYSTEM_PROMPT 加忠实性约束 `✅ 已完成`

- 文件：`backend/app/agent/prompts.py`
- 改动类型：修改
- domain: backend
- task_layer: foundation
- depends_on: []
- priority: 5
- risk_tags: []
- smoke_required: false
- mode: direct
- status: pending
- acceptance_criteria:
  - TEACHING_SYSTEM_PROMPT 包含"忠实性约束"章节
  - "忠实性约束"标记为"最高优先级，覆盖所有其他策略"
  - 包含"绝不编造"措辞
  - 原有教学策略章节保留（类比驱动、启发式引导等）
- test_tasks:
  - type: unit
    description: 验证 prompt 内容完整性
    scenarios: [忠实性章节存在, 最高优先级标记, 绝不编造措辞, 原有策略保留]
- contract_refs: []
- decision_refs: [DEC-rag-015]
- blocked_files: []

### BF002.1 重写 TEACHING_SYSTEM_PROMPT `⬜`

在现有 prompt 的"核心原则"之前插入忠实性约束章节。最终结构：

```
你是一位耐心、循循善诱的课程学习助手，专注于帮助学生理解教材内容。

## 忠实性约束（最高优先级，覆盖所有其他策略）
- 只说检索到的教材内容中明确存在的内容
- 绝不编造教材中没有的概念、定理、例题或比喻
- 类比和比喻只能用于解释教材中已有的概念，不能无中生有
- 如果检索到的内容与问题无关，说明这一点并引导学生提出具体问题
- 如果不确定某内容是否在教材中，标注"教材中未直接涉及"
- 每次只聚焦一个概念，不要试图覆盖多个不相关的话题

## 核心原则
（保持不变）

## 教学策略（按优先级使用）
（保持不变）

## 输出格式
（保持不变）

## 边界
- 如果学生的问题超出课程范围，礼貌说明并回归课程主题
- 如果教材中未找到相关内容，基于自身知识回答并标注"教材中未直接涉及"
- 如果检索到的内容与问题不相关，直接告诉学生并引导提出具体问题
```

关键改动：
1. 新增"忠实性约束"章节，放在最前面
2. "边界"章节新增第 3 条：不相关时直接告知

---

## R010-BB001：graph.py — respond 节点分级注入逻辑 `✅ 已完成`

- 文件：`backend/app/agent/graph.py`
- 改动类型：修改
- domain: backend
- task_layer: business
- depends_on: [R010-BF001, R010-BF002]
- priority: 5
- risk_tags: [llm_quality]
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - respond 节点根据 chunks/degraded/score 三条件分级注入
  - 无 chunks → 不注入 context
  - chunks 非空 + degraded=True → 弱参考路径
  - chunks 非空 + degraded=False + best_score >= threshold → 强约束路径
  - chunks 非空 + degraded=False + best_score < threshold → 弱参考路径
  - 现有 68 个测试全部通过
- test_tasks:
  - type: unit
    description: respond 节点分级注入单元测试
    scenarios: [无chunks, 高相关性, 低相关性, 降级]
  - type: integration
    description: graph 端到端分级注入集成测试
    scenarios: [高相关性集成, 低相关性集成]
- contract_refs: []
- decision_refs: [DEC-rag-014]
- blocked_files: []

### BB001.1 改造 _respond 闭包的 context 注入逻辑 `⬜`

改造 `graph.py` 中 `_respond` 函数（约第 185-215 行）的 context 注入部分。

当前逻辑（第 200-202 行）：
```python
if chunks:
    context_text = build_numbered_context(chunks)
    system_content += f"\n\n以下是检索到的教材内容：\n{context_text}\n请基于以上教材内容回答学生的问题。"
```

改为：
```python
# 1. 新增 import（文件顶部）
from app.config import settings

# 2. 改造注入逻辑
if chunks:
    context_text = build_numbered_context(chunks)
    degraded = state.get("degraded", False)

    if not degraded:
        best_score = max(c.score for c in chunks)
        if best_score >= settings.relevance_threshold:
            # 高相关性 — 强约束
            system_content += (
                f"\n\n以下是检索到的教材内容：\n{context_text}\n"
                "请严格基于以上教材内容回答。只使用教材中明确出现的信息，不要编造教材中没有的内容。"
            )
        else:
            # 低相关性 — 弱参考
            system_content += (
                f"\n\n以下是一些可能相关的参考内容：\n{context_text}\n"
                "如果这些内容与学生的问题相关，可以参考使用；如果不相关，基于你的知识回答并标注'教材中未直接涉及'。"
            )
    else:
        # 降级 — 弱参考（reranker 分数不可信）
        system_content += (
            f"\n\n以下是一些可能相关的参考内容：\n{context_text}\n"
            "如果这些内容与学生的问题相关，可以参考使用；如果不相关，基于你的知识回答并标注'教材中未直接涉及'。"
        )
```

逻辑步骤：
1. 从 `state` 读取 `degraded` 标志
2. 非降级时：取 chunks 中最高 score，与阈值比较
3. 降级时：跳过相关性判断，走弱参考路径
4. 无 chunks 时：不注入（现有行为保持）

---

## R010-BB002：测试补齐 — 无关 context + 降级场景 `✅ 已完成`

- 文件：`backend/tests/test_agent_nodes.py`, `backend/tests/test_graph_integration.py`, `backend/tests/_helpers.py`
- 改动类型：修改
- domain: backend
- task_layer: business
- depends_on: [R010-BB001]
- priority: 4
- risk_tags: [llm_quality]
- smoke_required: false
- mode: direct
- status: pending
- acceptance_criteria:
  - test_agent_nodes.py 新增 respond_relevant / respond_irrelevant / respond_no_chunks / respond_degraded 4 个测试
  - test_graph_integration.py 新增高/低相关性集成测试各 1 个
  - 现有测试全部通过
- test_tasks:
  - type: unit
    description: respond 节点分级注入单元测试
    scenarios: [高相关性, 低相关性, 无chunks, 降级]
  - type: integration
    description: graph 端到端分级注入
    scenarios: [高相关性集成, 低相关性集成]
- contract_refs: []
- decision_refs: [DEC-rag-014]
- blocked_files: []

### BB002.1 _helpers.py 新增 make_mock_chat_service_with_scores 辅助函数 `⬜`

新增支持 score 控制的 mock 构造函数：

```python
def make_mock_chat_service_with_scores(scores, degraded=False, degradation_reason=None):
    """构造 mock ChatService，chunks 带指定 score"""
    from tests.conftest import make_query_result
    chunks = []
    for i, s in enumerate(scores):
        qr = make_query_result(chunk_id=f"chunk-{i}", text=f"chunk text {i}", score=s)
        chunks.append(qr)
    return make_mock_chat_service(chunks=chunks, degraded=degraded, degradation_reason=degradation_reason)
```

同时更新 `make_query_result` 确认 score 参数是否已支持（检查 conftest.py 现有签名）。

### BB002.2 test_agent_nodes.py 新增 4 个 respond 分级测试 `⬜`

在 test_agent_nodes.py 的 respond 相关测试类中新增：

```python
# 1. test_respond_high_score_strict_context — score=0.9, degraded=False
#    验证：system_content 包含 "严格基于以上教材内容"

# 2. test_respond_low_score_weak_reference — score=0.2, degraded=False
#    验证：system_content 包含 "可能相关的参考内容"

# 3. test_respond_no_chunks_no_injection — chunks=[]
#    验证：system_content 不包含任何 context 相关文本

# 4. test_respond_degraded_weak_reference — score=0.9, degraded=True
#    验证：即使 score 高，走弱参考路径（降级分支）
```

关键：需让 `_respond` 闭包可测试。当前 `_respond` 是 `create_graph` 内部闭包，需将其提取为 `_make_respond(chat_model, chat_service)` 闭包（与 `_make_summarize` / `_make_rewrite` 模式一致），或者用完整 graph 集成测试替代。

### BB002.3 test_graph_integration.py 新增集成测试 `⬜`

```python
# test_relevant_chunks_full_path — score=0.9 的 chunk → 完整路径 → respond 输出正常
# test_irrelevant_chunks_full_path — score=0.2 的 chunk → 完整路径 → respond 输出正常
```

### BB002.4 更新现有 prompt 测试 `⬜`

在 test_agent_nodes.py 中更新对 TEACHING_SYSTEM_PROMPT 的断言：
- 新增 `assert "忠实性约束" in prompt`
- 新增 `assert "最高优先级" in prompt`
- 新增 `assert "绝不编造" in prompt`

---

## R010-BB003：eval 评估体系补齐 `✅ 已完成`

- 文件：`backend/eval/judge_prompts.py`, `backend/eval/llm_judge_eval.py`, `backend/eval/datasets/multi_turn_eval.json`, `backend/tests/test_grounding_eval.py`
- 改动类型：修改 + 新建
- domain: backend
- task_layer: business
- depends_on: [R010-BB001]
- priority: 3
- risk_tags: [llm_quality]
- smoke_required: false
- mode: direct
- status: pending
- acceptance_criteria:
  - multi_turn_eval.json 新增 ≥ 5 条 negative context 用例
  - judge_prompts.py 新增 GROUNDING_PROMPT 常量
  - llm_judge_eval.py 接入 grounding 维度评估
  - test_grounding_eval.py 验证 GROUNDING_PROMPT 格式正确
- test_tasks:
  - type: unit
    description: grounding prompt 格式和解析测试
    scenarios: [prompt 格式正确, JSON 输出解析]
- contract_refs: []
- decision_refs: [DEC-rag-014]
- blocked_files: []

### BB003.1 multi_turn_eval.json 新增 negative context 用例 `⬜`

在数据集末尾新增 5 条用例，使用新 level 标记：

```json
[
  {
    "id": "L7-N01",
    "level": "L7",
    "category": "irrelevant_context",
    "negative": true,
    "turns": [{"role": "user", "content": "你好"}],
    "expected": {
      "rewrite_should_trigger": false,
      "respond_should_not_use_context": true,
      "respond_should_acknowledge_irrelevant": true
    }
  },
  {
    "id": "L7-N02",
    "level": "L7",
    "category": "irrelevant_context",
    "negative": true,
    "turns": [{"role": "user", "content": "今天天气怎么样"}],
    "expected": {
      "rewrite_should_trigger": false,
      "respond_should_not_use_context": true,
      "respond_should_decline_out_of_scope": true
    }
  },
  {
    "id": "L7-N03",
    "level": "L7",
    "category": "irrelevant_context",
    "negative": true,
    "turns": [{"role": "user", "content": "背诵一下将进酒"}],
    "expected": {
      "respond_should_not_use_context": true,
      "respond_should_decline_out_of_scope": true
    }
  },
  {
    "id": "L7-N04",
    "level": "L7",
    "category": "irrelevant_context",
    "negative": true,
    "turns": [{"role": "user", "content": "谢谢你"}],
    "expected": {
      "respond_should_not_use_context": true,
      "respond_should_be_polite_acknowledgment": true
    }
  },
  {
    "id": "L7-N05",
    "level": "L7",
    "category": "irrelevant_context",
    "negative": true,
    "turns": [{"role": "user", "content": "帮我做一道菜"}],
    "expected": {
      "respond_should_not_use_context": true,
      "respond_should_decline_out_of_scope": true
    }
  }
]
```

### BB003.2 judge_prompts.py 新增 GROUNDING_PROMPT `⬜`

```python
GROUNDING_PROMPT = """你是一个评估 LLM 回答接地性的 Judge。

评估维度：LLM 的回答是否忠于提供的教材内容，没有编造教材中不存在的信息。

评分标准：
5分：回答完全基于教材内容，没有编造
4分：回答主要基于教材内容，有少量合理推断但无编造
3分：回答部分基于教材内容，有一些未明确标注的自由发挥
2分：回答包含明显的教材中不存在的概念或比喻
1分：回答大部分是编造的，与教材内容关联很弱
0分：Unknown（无法判断）

断言（assertions）：
1. 回答中没有出现教材中不存在的数学概念
2. 如果使用了类比或比喻，它解释的是教材中已有的概念
3. 如果教材内容与问题不相关，回答中明确指出了这一点

请评估以下内容：

教材内容：
{context}

学生问题：{question}

LLM 回答：
{answer}

请输出 JSON：{{"score": <0-5>, "assertions": [<true/false>, ...], "reasoning": "<简短理由>"}}"""
```

### BB003.3 llm_judge_eval.py 接入 grounding 维度 `⬜`

在 `llm_judge_eval.py` 的评估流程中新增第 5 维度：
- 对 L7 (irrelevant_context) 用例运行 GROUNDING_PROMPT 评估
- 输出 grounding_score 和 grounding_assertions_pass_rate
- 汇总到最终报告中

### BB003.4 新建 tests/test_grounding_eval.py `⬜`

```python
"""Grounding 评估维度测试"""
# 验证 GROUNDING_PROMPT 常量存在且格式正确
# 验证 JSON 输出解析逻辑
# 验证 L7 用例在 eval 数据集中存在
```

---

## R010-BB004：architecture.md 更新 `✅ 已完成`

- 文件：`.dev-flow/architecture.md`
- 改动类型：修改
- domain: docs
- task_layer: foundation
- depends_on: [R010-BB001]
- priority: 3
- risk_tags: []
- smoke_required: false
- mode: direct
- status: pending
- acceptance_criteria:
  - 新增 DEC-rag-014 和 DEC-rag-015 决策记录
  - 更新 respond 节点不变量
  - 现有内容不被破坏
- test_tasks:
  - type: unit
    description: 文件格式验证
    scenarios: [DEC 条目存在, 不变量更新]
- contract_refs: []
- decision_refs: [DEC-rag-014, DEC-rag-015]
- blocked_files: []

### BB004.1 新增 DEC-rag-014 和 DEC-rag-015 `⬜`

在 architecture.md 的"关键决策与理由"部分追加：

```
- **Context 分级注入策略**: respond 节点按检索结果相关性分级注入系统指令（相关→强约束/不相关→弱参考/降级→弱参考/空→不注入），避免 LLM 基于不相关内容产生幻觉（DEC-rag-014）
- **忠实性约束最高优先级**: TEACHING_SYSTEM_PROMPT 新增"忠实性约束"章节标记为最高优先级，要求 LLM 只说教材中明确存在的内容（DEC-rag-015）
```

### BB004.2 更新不变量 `⬜`

在"不变量"部分更新 respond 节点相关条目：

```
- respond 节点使用分级 context 注入：高相关性（degraded=False, score>=threshold）强约束；低相关性和降级（degraded=True）弱参考；无结果不注入
```

替换现有的：
```
- respond 节点使用动态 system prompt 注入 RAG context，对话历史原样透传，不修改用户消息
```
