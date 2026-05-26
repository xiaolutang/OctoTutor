"""R010 多轮对话 LLM-as-Judge 评估 prompt

4 个维度独立评分，每个维度含 rubric（评分标准）+ assertions（行为断言）。
评分含 Unknown=0 退出机制：信息不足时评 0 分，不强制评分。
"""

REWRITE_QUALITY_PROMPT = """评估改写后问题的质量。

## 评分标准
5 = 完美：语义完整，代词替换准确，可独立理解
4 = 良好：语义基本完整，有轻微瑕疵
3 = 可接受：核心语义保留，但细节有缺失
2 = 较差：关键信息缺失或语义偏移
1 = 完全错误：语义完全改变
0 = Unknown：信息不足，无法判断

## 断言检查（每条 通过/不通过）
1. 改写后包含原始问题中的数学概念
2. 代词（它、这个、那个）已被替换为具体概念
3. 改写后可独立理解，无需对话上下文

## 输入
对话历史：{history}
原始问题：{question}
改写结果：{rewritten_question}

## 输出格式（严格 JSON）
{{"score": <0-5>, "assertions": [true/false, true/false, true/false], "reasoning": "<简短理由>"}}
"""

RETRIEVAL_RELEVANCE_PROMPT = """评估检索结果与问题的相关性。

## 评分标准
5 = 完美：所有 chunk 高度相关
4 = 良好：大部分 chunk 相关
3 = 可接受：有相关 chunk 但有噪声
2 = 较差：大部分 chunk 不相关
1 = 完全错误：完全无关
0 = Unknown：无法判断

## 断言检查
1. 返回的 chunks 主题与问题一致
2. chunks 数量 >= 1
3. chunks 包含关键数学术语

## 输入
问题：{question}
检索结果数量：{num_chunks}
检索内容摘要：{chunks_summary}

## 输出格式（严格 JSON）
{{"score": <0-5>, "assertions": [true/false, true/false, true/false], "reasoning": "<简短理由>"}}
"""

CONTEXT_COHERENCE_PROMPT = """评估回答是否正确引用了历史上下文。

## 评分标准
5 = 完美：流畅引用历史概念，教学语气一致
4 = 良好：引用了大部分历史，有小遗漏
3 = 可接受：部分引用历史，有明显断层
2 = 较差：未引用历史或与历史矛盾
1 = 完全错误：完全忽略历史
0 = Unknown：无法判断

## 断言检查
1. 回答引用了前几轮对话的概念
2. 回答没有与历史矛盾的内容
3. 回复语气保持教学一致性

## 输入
对话历史：{history}
当前问题：{question}
回答摘要：{answer_summary}

## 输出格式（严格 JSON）
{{"score": <0-5>, "assertions": [true/false, true/false, true/false], "reasoning": "<简短理由>"}}
"""

SUMMARY_FIDELITY_PROMPT = """评估摘要的保真度。

## 评分标准
5 = 完美：关键概念和因果链完整保留，无多余信息
4 = 良好：关键概念保留，因果链有小遗漏
3 = 可接受：主要概念保留，部分细节丢失
2 = 较差：关键信息丢失或引入了多余信息
1 = 完全错误：摘要与对话内容不符
0 = Unknown：无法判断

## 断言检查
1. 摘要保留了关键数学术语
2. 摘要保留了解题步骤的因果链
3. 摘要未引入对话中未出现的信息

## 输入
原始对话：{original_messages}
摘要内容：{summary}

## 输出格式（严格 JSON）
{{"score": <0-5>, "assertions": [true/false, true/false, true/false], "reasoning": "<简短理由>"}}
"""

# 维度名称常量
DIMENSIONS = [
    "rewrite_quality",
    "retrieval_relevance",
    "context_coherence",
    "summary_fidelity",
]
