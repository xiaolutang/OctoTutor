---
date: 2026-05-21
type: analysis
mode: new_requirement
status: analyzed
requirement_cycle: R004
topic: R004-eval-dataset-annotation
supplements: 2026-05-21--R004-rag-dialogue.md
brainstorm_ref: null
source_scope:
  code_files:
    - backend/app/evaluation/eval_types.py
    - backend/app/evaluation/eval_set_loader.py
    - backend/app/evaluation/graders/deterministic.py
    - backend/app/evaluation/graders/llm_judge.py
    - backend/app/evaluation/eval_runner.py
    - backend/app/infra/llm.py
    - backend/app/config.py
  data_files:
    - backend/data/evaluation/eval_set.json (200 items)
    - backend/data/parsed/ (974 pages across 5 textbooks)
  user_request: "补齐 R004 评估数据集标注方案：为 200 条 eval_set 生成 key_facts、reference_answer、suite 字段"
architecture_impact: false
replaces: null
confirmation:
  status: confirmed
  confirmed_at: "2026-05-21"
---

# R004 评估数据集自动标注方案

> 本文档补充 `2026-05-21--R004-rag-dialogue.md` §8 数据标注规范，将原"人工标注"方案调整为"LLM 辅助 + 交叉验证"的自动化方案。

## 1. 分析边界

- 分析类型：new_requirement（补充方案）
- 输入来源：R004 已完成的评估管线代码 + 200 条 eval_set + 974 页 parsed markdown
- 已读取代码：eval_types.py, eval_set_loader.py, deterministic.py, llm_judge.py, eval_runner.py, infra/llm.py, config.py
- 已读取数据：eval_set.json（200 条，189 条非 NEGATIVE + 11 条 NEGATIVE）
- 明确不分析：
  - 不新增 eval 问题（沿用现有 200 条）
  - 不改变 EvalItem 数据结构（BB006 已完成）
  - 不改变评估管线代码（BB007 已完成）

## 2. 功能目标

为现有 200 条 eval_set 数据填充三个空字段，使 R004 评估管线（run_faithfulness / run_full）可以端到端运行。

| 字段 | 目标状态 | 来源 |
|------|---------|------|
| `key_facts` | 每条 3-7 个关键知识点 | LLM 从教材原文提取 |
| `reference_answer` | 每条 200-500 字参考答案 | LLM 从教材原文生成 |
| `suite` | 每条有归属标记 | 按规则自动分配 |

## 3. 数据现状分析

### 3.1 现有 200 条数据分布

| 维度 | 分布 |
|------|------|
| 总量 | 200 条（q001-q200） |
| question_type | formal=117, misconception=31, comparison=27, application=14, colloquial=11 |
| difficulty | medium=131, easy=35, hard=34 |
| retrieval_truth.mode | ANY=163, ALL=26, NEGATIVE=11 |
| sources/book 覆盖 | 必修第一册=61, 必修第二册=48, 选择性必修第一册=41, 选择性必修第二册=35, 选择性必修第三册=32 |
| section_id 覆盖率 | 100%（217 个 sources 全部有 section_id） |
| required_keywords 覆盖率 | 100%（平均 3.3 个/source） |

### 3.2 教材资源

| 资源 | 路径 | 规模 |
|------|------|------|
| parsed markdown | `backend/data/parsed/{书名}/page_{N}.md` | 974 页 |
| eval_set | `backend/data/evaluation/eval_set.json` | 200 条 |

每条 eval item 的 `retrieval_truth.sources` 精确指定了书名和页码范围（如 `必修第一册 p9-9`），可以直接定位到对应的 parsed markdown 文件。

### 3.3 核心问题

**原方案（人工标注）的困境**：
- 原方案要求"标注员 A 起草 → 标注员 B 审查 → 负责人仲裁"（§8 数据标注规范）
- 1 人团队无法执行双人交叉审查
- 200 条全量人工标注时间成本高

**实际可行方案**：用 LLM 基于教材原文自动生成标注数据，再通过程序化验证保证质量。

## 4. 方案设计

### 4.1 整体流程

```
eval_set.json (200 items)
    │
    ├─ 非NEGATIVE (189 items)
    │   ├─ 读取 retrieval_truth.sources → 定位教材页码
    │   ├─ 拼接教材原文 (parsed/{book}/page_{start}~page_{end}.md)
    │   ├─ LLM 调用 → 生成 key_facts + reference_answer
    │   └─ 按 question_type 分配 suite
    │
    ├─ NEGATIVE (11 items)
    │   ├─ key_facts = []
    │   ├─ reference_answer = "该问题超出高中数学范围"
    │   └─ suite = "negative"
    │
    └─ 写入 eval_set.json + 验证
```

### 4.2 suite 分配规则

| 条件 | suite 值 | 数量（预估） |
|------|---------|------------|
| mode=NEGATIVE | `"negative"` | 11 |
| mode=ANY/ALL, difficulty=easy/medium | `"regression"` | ~166 |
| mode=ANY/ALL, difficulty=hard | `"capability"` | ~23 |

说明：
- `regression`：回归测试用例，验证检索基线不退化
- `capability`：能力测试用例（hard 难度），用于 Faithfulness + Coverage 评估
- `negative`：拒识测试用例，验证超纲问题不返回结果

### 4.3 教材原文读取逻辑

```python
def load_textbook_pages(book: str, page_start: int, page_end: int) -> str:
    """从 parsed/ 目录读取指定书名和页码范围的教材内容"""
    pages = []
    for page_num in range(page_start, page_end + 1):
        path = Path(f"data/parsed/{book}/page_{page_num}.md")
        if path.exists():
            pages.append(path.read_text(encoding="utf-8"))
    return "\n\n".join(pages)
```

对多 source 的问题（24 条有 2 个 source，2 条有 3 个 source），拼接所有 source 的教材内容。

### 4.4 LLM 标注 Prompt 设计

使用与 infra/llm.py 相同的 OpenAI 兼容客户端（glm-5.1）。

**System Prompt**：
```
你是高中数学教材标注助手。基于提供的教材原文，完成以下两个任务：

任务一：提取关键知识点
从教材原文中提取 3-7 个关键知识点。要求：
- 每个知识点是一个独立的数学概念、公式或性质
- 必须能在提供的教材原文中找到明确依据
- 避免重复表述同一概念
- 粒度适中（如"集合元素的确定性"、"交集运算的定义"）

任务二：编写参考答案
基于教材原文，针对问题编写参考答案。要求：
- 只使用提供的教材原文内容，不编造
- 长度 200-500 字
- 包含关键概念解释和必要推导
- 标注出处（书名+页码）

输出 JSON 格式：
{
  "key_facts": ["知识点1", "知识点2", ...],
  "reference_answer": "参考答案文本..."
}
```

**User Prompt**：
```
问题：{question}
问题类型：{question_type}
难度：{difficulty}
教材原文：
{textbook_content}
```

### 4.5 数据质量保证（三层验证）

#### 第一层：格式验证（程序化，0 成本）

```python
def validate_annotation(item: dict) -> list[str]:
    errors = []
    facts = item.get("key_facts", [])
    answer = item.get("reference_answer", "")

    # key_facts 检查
    if len(facts) < 3 or len(facts) > 7:
        errors.append(f"key_facts 数量异常: {len(facts)} (期望 3-7)")
    for fact in facts:
        if len(fact) > 50:
            errors.append(f"key_facts 粒度过粗: '{fact[:30]}...'")

    # reference_answer 检查
    if len(answer) < 100:
        errors.append(f"reference_answer 过短: {len(answer)} 字")
    if len(answer) > 800:
        errors.append(f"reference_answer 过长: {len(answer)} 字")

    return errors
```

#### 第二层：确定性检查（DeterministicGrader，0 成本）

对 LLM 生成的 reference_answer 走一遍 DeterministicGrader：
- 答案非空
- 包含的关键概念与 key_facts 有交集（内容相关性）

#### 第三层：交叉验证（LLM Judge，1 次 LLM 调用/条）

对 reference_answer 做 Faithfulness 自评：
- Faithfulness ≥ 0.8：标注合格
- Faithfulness < 0.5：标注可能有问题，标记待人工复核
- 0.5 ≤ Faithfulness < 0.8：标记为 marginal

> 注意：此层验证可选，对全部 200 条跑成本较高。建议首次只对抽样 20 条运行。

### 4.6 脚本设计

**文件路径**：`backend/scripts/annotate_eval_set.py`

**依赖**：`openai`、项目 config（读取 API Key/URL）

**执行流程**：
1. 加载 `eval_set.json`
2. 遍历每条 item：
   - NEGATIVE：直接填充默认值
   - 非 NEGATIVE：读取教材原文 → LLM 标注 → 格式验证
3. 格式验证失败的条目：重试一次（调整 prompt）
4. 重试仍失败：保留原始字段，记录 warning
5. 写入 `eval_set.json`（覆盖原文件）
6. 输出统计报告

**幂等性**：已有 key_facts 的条目跳过（支持增量运行）。

**成本估算**：
- 189 条非 NEGATIVE × 1 次 LLM 调用 ≈ 189 次
- 重试：约 10% ≈ 19 次
- 总计约 208 次 LLM 调用
- 按 glm-5.1 定价，成本可忽略

### 4.7 NEGATIVE 条目处理

11 条 NEGATIVE 条目（超纲问题）不调用 LLM，直接硬编码：

```python
{
    "key_facts": [],
    "reference_answer": "该问题超出高中数学课程范围，不应检索到相关教材内容。",
    "suite": "negative"
}
```

### 4.8 模块边界

| 模块 | 职责 | 文件 |
|------|------|------|
| 标注脚本 | 读取教材 + 调用 LLM + 写入 eval_set | `backend/scripts/annotate_eval_set.py` |
| LLM 客户端 | 复用 OpenAI 兼容协议 | 复用 `app/config.py` 的 NEWAPI 配置 |
| 数据模型 | EvalItem 序列化/反序列化 | 复用 `app/evaluation/eval_types.py` |
| 验证 | 格式检查 | 脚本内实现 |

不修改任何现有应用代码，只新增 1 个脚本文件。

## 5. Decision Items

| ID | Summary | Type | Must Plan | Source |
|----|---------|------|-----------|--------|
| DEC-eval-001 | 评估数据集采用 LLM 辅助标注（非纯人工标注），基于教材原文生成 key_facts + reference_answer，三层验证保证质量 | test_strategy | yes | solution_design |
| DEC-eval-002 | suite 字段按规则自动分配：NEGATIVE→negative, hard→capability, 其他→regression | business_rule | yes | solution_design |
| DEC-eval-003 | NEGATIVE 条目不调用 LLM，硬编码 key_facts=[] + reference_answer 描述拒识 | test_strategy | no | solution_design |
| DEC-eval-004 | 标注脚本幂等设计：已有 key_facts 的条目跳过，支持增量运行和失败重跑 | process | no | solution_design |

## 6. 风险与缺口

| ID | Gap/Risk | Impact | Suggested Handling |
|----|----------|--------|--------------------|
| RSK-eval-001 | LLM 生成 key_facts 可能包含教材原文中没有的知识点 | Coverage 评估失真 | 第一层验证：对比 key_facts 与 required_keywords 交集 |
| RSK-eval-002 | reference_answer 可能不忠于教材原文 | Faithfulness 自评失真 | 第三层交叉验证：reference_answer 的 Faithfulness 自评 ≥ 0.8 |
| RSK-eval-003 | 多 source 问题（26 条）教材内容拼接过长 | LLM 输入超 token 限制 | 截断到 3000 字符（与 CHAT_MAX_CONTEXT_TOKENS 一致） |

## 7. 集成测试要求

- 脚本执行后验证 `eval_set.json`：
  - 200 条全部有 `suite` 字段
  - 189 条非 NEGATIVE 全部有非空 `key_facts`（3-7 个）和非空 `reference_answer`（≥100 字）
  - 11 条 NEGATIVE 的 `key_facts` 为空，`reference_answer` 包含"超出"关键词
  - `EvalSetLoader.load()` 无报错
  - `EvalRunner.run_faithfulness()` 可端到端运行（需真实 LLM 服务）

## 8. 实施计划建议

单任务即可完成：

| Task | Description | Files |
|------|-------------|-------|
| BB010 | 评估数据集自动标注：编写 annotate_eval_set.py 脚本，为 200 条 eval_set 生成 key_facts + reference_answer + suite | `backend/scripts/annotate_eval_set.py`（新建），`backend/data/evaluation/eval_set.json`（修改） |
