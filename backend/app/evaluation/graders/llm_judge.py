"""LLM Judge — 基于 LLM 的 Faithfulness + Coverage 合并评估

使用 OpenAI 兼容协议调用 LLM，对生成回答进行忠实度和覆盖度评估。
支持 Unknown 选项，Unknown claims 不计入 Faithfulness 分子分母，单独统计比例。

Usage:
    from app.evaluation.graders.llm_judge import LLMJudge

    judge = LLMJudge(api_key="...", base_url="...")
    result = judge.judge(answer="...", context="...", key_facts=["..."])
    print(f"Faithfulness: {result.faithfulness}")
    print(f"Coverage: {result.coverage_score}")
    print(f"Unknown ratio: {result.unknown_ratio}")
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from openai import OpenAI

logger = logging.getLogger(__name__)


@dataclass
class ClaimVerdict:
    """单个事实声明的判定结果

    Attributes:
        claim: 声明文本
        verdict: 判定结果 "Yes" | "No" | "Unknown"
    """

    claim: str
    verdict: str


@dataclass
class CoverageResult:
    """单个知识点的覆盖度判定结果

    Attributes:
        fact: 知识点文本
        status: 覆盖状态 "covered" | "not_covered" | "partially_covered"
    """

    fact: str
    status: str


@dataclass
class JudgeResult:
    """LLM Judge 评估结果

    Attributes:
        claims: 事实声明判定列表
        coverage: 知识点覆盖度判定列表
        faithfulness: 忠实度分数 (0.0~1.0)，Unknown 不计入分子分母
        coverage_score: 覆盖度分数 (0.0~1.0)，partially_covered 算 0.5
        unknown_ratio: Unknown 声明占比 (0.0~1.0)
        relevance: 相关性分数 (1.0 / 0.5 / 0.0)
        relevance_label: 相关性标签 "relevant" / "partially_relevant" / "not_relevant"
    """

    claims: list[ClaimVerdict]
    coverage: list[CoverageResult]
    faithfulness: float
    coverage_score: float
    unknown_ratio: float
    relevance: float = 0.0
    relevance_label: str = "not_relevant"


# ---------------------------------------------------------------------------
# Prompt 模板
# ---------------------------------------------------------------------------

JUDGE_SYSTEM_PROMPT = """你是评估助手。你的任务是严格按照指定 JSON 格式输出评估结果，不要添加任何额外文本。"""

JUDGE_USER_PROMPT_TEMPLATE = """你是评估助手。给定原始问题、学生的回答和参考教材内容，完成以下三个任务：

任务一：忠实度评估
将学生的回答拆分为独立的事实声明，对每个声明判断：
- Yes：该声明可从教材内容中直接找到支持
- No：该声明与教材内容矛盾或无法从教材内容中找到依据
- Unknown：无法从提供的教材内容中判断

任务二：覆盖度检查
检查学生的回答是否覆盖了以下关键知识点：
{key_facts}
对每个知识点判断：covered / not_covered / partially_covered

任务三：相关性评估
判断学生的回答是否切题，即是否正面回应了原始问题。
- relevant：回答直接回应了问题的核心
- partially_relevant：回答与问题相关但未直接回答核心问题
- not_relevant：回答与问题无关或完全偏离主题

输出 JSON 格式：
{{
  "claims": [{{"claim": "...", "verdict": "Yes|No|Unknown"}}],
  "coverage": [{{"fact": "...", "status": "covered|not_covered|partially_covered"}}],
  "relevance": "relevant|partially_relevant|not_relevant"
}}

原始问题：
{question}

参考教材内容：
{context}

学生回答：
{answer}

请直接输出 JSON，不要包含 markdown 代码块标记。"""


class LLMJudge:
    """LLM Judge — Faithfulness + Coverage 合并评估

    通过 OpenAI 兼容协议调用 LLM，对生成回答进行忠实度和覆盖度评估。

    Args:
        api_key: OpenAI 兼容 API Key
        base_url: OpenAI 兼容 API 地址
        model: LLM 模型名称，默认 "glm-5.1"
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str = "glm-5.1",
    ) -> None:
        self._model = model
        self._client = OpenAI(api_key=api_key, base_url=base_url)

    def judge(
        self,
        answer: str,
        context: str,
        key_facts: list[str],
        question: str = "",
    ) -> JudgeResult:
        """执行 Faithfulness + Coverage + Relevance 合并评估

        Args:
            answer: 学生回答文本
            context: 参考教材内容
            key_facts: 期望覆盖的关键知识点列表
            question: 原始问题文本（可选，用于相关性评估）

        Returns:
            JudgeResult 包含 faithfulness, coverage_score, unknown_ratio, relevance 等指标
        """
        key_facts_text = (
            "\n".join(f"- {fact}" for fact in key_facts)
            if key_facts
            else "(无指定知识点)"
        )

        prompt = JUDGE_USER_PROMPT_TEMPLATE.format(
            key_facts=key_facts_text,
            question=question,
            context=context,
            answer=answer,
        )

        messages = [
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        response = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=0.0,
        )

        raw_content = response.choices[0].message.content
        return self._parse_response(raw_content)

    def _parse_response(self, raw_content: str) -> JudgeResult:
        """解析 LLM 响应为 JudgeResult

        Args:
            raw_content: LLM 返回的原始文本

        Returns:
            JudgeResult 结构化评估结果
        """
        # 清理 markdown 代码块标记
        content = raw_content.strip()
        if content.startswith("```"):
            # 移除开头的 ```json 或 ```
            first_newline = content.index("\n")
            content = content[first_newline + 1 :]
            # 移除结尾的 ```
            if content.endswith("```"):
                content = content[:-3].strip()

        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            logger.warning(
                "LLM Judge 响应 JSON 解析失败，返回默认结果: %s", raw_content[:200]
            )
            return JudgeResult(
                claims=[],
                coverage=[],
                faithfulness=0.0,
                coverage_score=0.0,
                unknown_ratio=1.0,
                relevance=0.0,
                relevance_label="not_relevant",
            )

        # 解析 claims
        claims: list[ClaimVerdict] = []
        for claim_data in data.get("claims", []):
            verdict = claim_data.get("verdict", "Unknown")
            if verdict not in ("Yes", "No", "Unknown"):
                verdict = "Unknown"
            claims.append(
                ClaimVerdict(
                    claim=claim_data.get("claim", ""),
                    verdict=verdict,
                )
            )

        # 解析 coverage
        coverage_results: list[CoverageResult] = []
        for cov_data in data.get("coverage", []):
            status = cov_data.get("status", "not_covered")
            if status not in ("covered", "not_covered", "partially_covered"):
                status = "not_covered"
            coverage_results.append(
                CoverageResult(
                    fact=cov_data.get("fact", ""),
                    status=status,
                )
            )

        # 解析 relevance
        relevance_str = data.get("relevance", "not_relevant")
        relevance_map = {"relevant": 1.0, "partially_relevant": 0.5, "not_relevant": 0.0}
        relevance_score = relevance_map.get(relevance_str, 0.0)
        if relevance_str not in relevance_map:
            relevance_str = "not_relevant"

        # 计算指标
        faithfulness, unknown_ratio = self._calc_faithfulness_and_unknown(claims)
        coverage_score = self._calc_coverage(coverage_results)

        return JudgeResult(
            claims=claims,
            coverage=coverage_results,
            faithfulness=faithfulness,
            coverage_score=coverage_score,
            unknown_ratio=unknown_ratio,
            relevance=relevance_score,
            relevance_label=relevance_str,
        )

    @staticmethod
    def _calc_faithfulness_and_unknown(claims: list[ClaimVerdict]) -> tuple[float, float]:
        """计算 Faithfulness 分数和 Unknown 比例（单次遍历）

        Faithfulness = supported / (supported + unsupported)，Unknown 不计入分子分母。
        Unknown ratio = unknown_count / total_claims。
        """
        if not claims:
            return 0.0, 0.0
        supported = 0
        unsupported = 0
        unknown_count = 0
        for c in claims:
            if c.verdict == "Yes":
                supported += 1
            elif c.verdict == "No":
                unsupported += 1
            else:
                unknown_count += 1
        total_known = supported + unsupported
        faithfulness = supported / total_known if total_known > 0 else 0.0
        unknown_ratio = unknown_count / len(claims)
        return faithfulness, unknown_ratio

    @staticmethod
    def _calc_coverage(coverage_results: list[CoverageResult]) -> float:
        """计算 Coverage 分数

        Coverage = (covered * 1 + partially_covered * 0.5) / total
        """
        if not coverage_results:
            return 0.0
        total = len(coverage_results)
        score = 0.0
        for cr in coverage_results:
            if cr.status == "covered":
                score += 1.0
            elif cr.status == "partially_covered":
                score += 0.5
        return score / total
