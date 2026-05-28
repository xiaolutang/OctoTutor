"""R010 多轮对话 LLM-as-Judge 评估 prompt

5 个维度独立评分，每个维度含 rubric（评分标准）+ assertions（行为断言）。
评分含 Unknown=0 退出机制：信息不足时评 0 分，不强制评分。
"""

_JUDGE_OUTPUT_FORMAT = '{{"score": <0-5>, "assertions": [true/false, true/false, true/false], "reasoning": "<简短理由>"}}'


def _build_judge_prompt(rubric: str, assertions: list[str], inputs: list[tuple[str, str]]) -> str:
    """构建 Judge prompt 模板

    Args:
        rubric: 评分标准描述（每行 "N = ..."）
        assertions: 断言列表
        inputs: 输入字段列表，每项 (label, placeholder)
    """
    rubric_block = rubric
    assertions_block = "\n".join(f"{i+1}. {a}" for i, a in enumerate(assertions))
    inputs_block = "\n".join(f"{label}：{{{placeholder}}}" for label, placeholder in inputs)

    return f"""{rubric_block}

## 断言检查
{assertions_block}

## 输入
{inputs_block}

## 输出格式（严格 JSON）
{_JUDGE_OUTPUT_FORMAT}
"""


REWRITE_QUALITY_PROMPT = _build_judge_prompt(
    rubric="""评估改写后问题的质量。

## 评分标准
5 = 完美：语义完整，代词替换准确，可独立理解
4 = 良好：语义基本完整，有轻微瑕疵
3 = 可接受：核心语义保留，但细节有缺失
2 = 较差：关键信息缺失或语义偏移
1 = 完全错误：语义完全改变
0 = Unknown：信息不足，无法判断""",
    assertions=[
        "改写后包含原始问题中的数学概念",
        "代词（它、这个、那个）已被替换为具体概念",
        "改写后可独立理解，无需对话上下文",
    ],
    inputs=[
        ("对话历史", "history"),
        ("原始问题", "question"),
        ("改写结果", "rewritten_question"),
    ],
)

RETRIEVAL_RELEVANCE_PROMPT = _build_judge_prompt(
    rubric="""评估检索结果与问题的相关性。

## 评分标准
5 = 完美：所有 chunk 高度相关
4 = 良好：大部分 chunk 相关
3 = 可接受：有相关 chunk 但有噪声
2 = 较差：大部分 chunk 不相关
1 = 完全错误：完全无关
0 = Unknown：无法判断""",
    assertions=[
        "返回的 chunks 主题与问题一致",
        "chunks 数量 >= 1",
        "chunks 包含关键数学术语",
    ],
    inputs=[
        ("问题", "question"),
        ("检索结果数量", "num_chunks"),
        ("检索内容摘要", "chunks_summary"),
    ],
)

CONTEXT_COHERENCE_PROMPT = _build_judge_prompt(
    rubric="""评估回答是否正确引用了历史上下文。

## 评分标准
5 = 完美：流畅引用历史概念，教学语气一致
4 = 良好：引用了大部分历史，有小遗漏
3 = 可接受：部分引用历史，有明显断层
2 = 较差：未引用历史或与历史矛盾
1 = 完全错误：完全忽略历史
0 = Unknown：无法判断""",
    assertions=[
        "回答引用了前几轮对话的概念",
        "回答没有与历史矛盾的内容",
        "回复语气保持教学一致性",
    ],
    inputs=[
        ("对话历史", "history"),
        ("当前问题", "question"),
        ("回答摘要", "answer_summary"),
    ],
)

SUMMARY_FIDELITY_PROMPT = _build_judge_prompt(
    rubric="""评估摘要的保真度（主题覆盖度）。

## 评分标准
5 = 完美：对话中的每个话题都被覆盖，关键概念和因果链完整保留，无多余信息
4 = 良好：绝大多数话题被覆盖（>=80%），关键概念保留，因果链有小遗漏
3 = 可接受：主要话题被覆盖（>=60%），主要概念保留，部分细节丢失
2 = 较差：大量话题未被覆盖（<60%），关键信息丢失
1 = 完全错误：摘要与对话内容严重不符
0 = Unknown：无法判断""",
    assertions=[
        "摘要覆盖了原始对话中至少 60% 的话题",
        "已覆盖话题的关键因果链被保留",
        "摘要未引入对话中未出现的信息",
    ],
    inputs=[
        ("原始对话主题列表", "original_messages"),
        ("摘要内容", "summary"),
    ],
)

# 维度名称常量
DIMENSIONS = [
    "rewrite_quality",
    "retrieval_relevance",
    "context_coherence",
    "summary_fidelity",
    "grounding",
]

GROUNDING_PROMPT = _build_judge_prompt(
    rubric="""评估 LLM 回答的接地性（Grounding）。

评估维度：LLM 的回答是否忠于提供的教材内容，没有编造教材中不存在的信息。

## 评分标准
5 = 完全忠实：回答完全基于教材内容，没有编造
4 = 高度忠实：回答主要基于教材内容，有少量合理推断但无编造
3 = 部分忠实：回答部分基于教材内容，有一些未明确标注的自由发挥
2 = 编造嫌疑：回答包含明显的教材中不存在的概念或比喻
1 = 严重编造：回答大部分是编造的，与教材内容关联很弱
0 = Unknown：无法判断""",
    assertions=[
        "回答中没有出现教材中不存在的数学概念",
        "如果使用了类比或比喻，它解释的是教材中已有的概念",
        "如果教材内容与问题不相关，回答中明确指出了这一点",
    ],
    inputs=[
        ("教材内容", "context"),
        ("学生问题", "question"),
        ("LLM 回答", "answer"),
    ],
)
