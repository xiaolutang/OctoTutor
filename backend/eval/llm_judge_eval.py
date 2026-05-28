"""R010 多轮对话 LLM-as-Judge 评估

使用方式：
    cd backend
    python -m eval.llm_judge_eval --dataset eval/datasets/multi_turn_eval.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass, field
from typing import Any

from eval.graders import TestCaseResult
from eval._helpers import get_llm_config, call_llm_json


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class JudgeResult:
    """单个维度的 Judge 评分结果"""

    dimension: str
    score: int  # 0-5, 0=Unknown
    assertions: list[bool]
    reasoning: str
    error: str | None = None


@dataclass
class LLMJudgeCaseResult:
    """单个用例的 LLM Judge 完整结果"""

    test_id: str
    level: str
    category: str
    negative: bool
    deterministic_result: TestCaseResult | None = None
    judge_results: list[JudgeResult] = field(default_factory=list)
    avg_score: float = 0.0
    assertion_pass_rate: float = 0.0


# ---------------------------------------------------------------------------
# LLM Judge 工具
# ---------------------------------------------------------------------------


def _make_judge_result(dimension: str, judge_output: dict[str, Any]) -> JudgeResult:
    """从 LLM Judge 输出构建 JudgeResult"""
    return JudgeResult(
        dimension=dimension,
        score=judge_output.get("score", 0),
        assertions=judge_output.get("assertions", [False, False, False]),
        reasoning=judge_output.get("reasoning", ""),
        error=judge_output.get("error"),
    )


def _summarize_chunks(chunks_raw: list, limit: int = 5, max_chars: int = 200) -> str:
    """将 context_chunks 转为带编号的摘要文本"""
    if not chunks_raw:
        return ""
    lines = []
    for i, c in enumerate(chunks_raw[:limit]):
        text = c.text if hasattr(c, "text") else str(c)
        lines.append(f"[{i+1}] {text[:max_chars]}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 单用例 LLM Judge
# ---------------------------------------------------------------------------


async def _run_llm_judge_for_case(
    case: dict,
    deterministic_result: TestCaseResult,
    llm_config: dict[str, str],
    final_state: dict,
) -> LLMJudgeCaseResult:
    """对单个用例运行 LLM Judge（GLM-5.1）"""
    from eval.judge_prompts import (
        REWRITE_QUALITY_PROMPT,
        RETRIEVAL_RELEVANCE_PROMPT,
        CONTEXT_COHERENCE_PROMPT,
        SUMMARY_FIDELITY_PROMPT,
        GROUNDING_PROMPT,
    )

    result = LLMJudgeCaseResult(
        test_id=case["id"],
        level=case["level"],
        category=case["category"],
        negative=case.get("negative", False),
        deterministic_result=deterministic_result,
    )

    turns = case["turns"]
    expected = case["expected"]

    # 从 state 获取真实 rewrite 结果
    rewritten_question = final_state.get("rewritten_question", "")
    conversation_summary = final_state.get("conversation_summary", "")

    # 维度 1: Rewrite 质量（仅多轮正面用例评估）
    if expected.get("rewrite_should_trigger") and not result.negative:
        history = "\n".join(t["content"] for t in turns[:-1])
        question = turns[-1]["content"]
        prompt = REWRITE_QUALITY_PROMPT.format(
            history=history,
            question=question,
            rewritten_question=rewritten_question or "(未改写)",
        )
        judge_output = call_llm_json(prompt, llm_config)
        result.judge_results.append(
            _make_judge_result("rewrite_quality", judge_output)
        )

    # 维度 2: 检索相关性（正面用例，所有输入都走 retrieve 路径）
    if not result.negative:
        chunks_raw = final_state.get("context_chunks", [])
        chunks_summary = _summarize_chunks(chunks_raw) or "(无检索结果)"
        prompt = RETRIEVAL_RELEVANCE_PROMPT.format(
            question=turns[-1]["content"],
            num_chunks=len(chunks_raw),
            chunks_summary=chunks_summary or "(无检索结果)",
        )
        judge_output = call_llm_json(prompt, llm_config)
        result.judge_results.append(
            _make_judge_result("retrieval_relevance", judge_output)
        )

    # 维度 3: 上下文连贯性（多轮正面用例）
    if len(turns) > 1 and not result.negative:
        history = "\n".join(t["content"] for t in turns[:-1])
        ai_answer = final_state.get("last_ai_answer", "")
        answer_summary = ai_answer[:500] if ai_answer else (
            f"rewrite: {rewritten_question}" if rewritten_question else "首轮无 rewrite"
        )
        prompt = CONTEXT_COHERENCE_PROMPT.format(
            history=history,
            question=turns[-1]["content"],
            answer_summary=answer_summary,
        )
        judge_output = call_llm_json(prompt, llm_config)
        result.judge_results.append(
            _make_judge_result("context_coherence", judge_output)
        )

    # 维度 4: 摘要保真度（仅 summarize 触发时评估）
    if conversation_summary:
        original_messages = "\n".join(t["content"] for t in turns)
        prompt = SUMMARY_FIDELITY_PROMPT.format(
            original_messages=original_messages,
            summary=conversation_summary,
        )
        judge_output = call_llm_json(prompt, llm_config)
        result.judge_results.append(
            _make_judge_result("summary_fidelity", judge_output)
        )

    # 维度 5: 接地性（irrelevant_context / L7 用例）
    if case.get("category") == "irrelevant_context":
        chunks_raw = final_state.get("context_chunks", [])
        context_summary = _summarize_chunks(chunks_raw) or "(无检索结果)"
        ai_answer = final_state.get("last_ai_answer", "")
        prompt = GROUNDING_PROMPT.format(
            context=context_summary or "(无检索结果)",
            question=turns[-1]["content"],
            answer=ai_answer or "(无回答)",
        )
        judge_output = call_llm_json(prompt, llm_config)
        result.judge_results.append(
            _make_judge_result("grounding", judge_output)
        )

    # 计算汇总
    if result.judge_results:
        scores = [r.score for r in result.judge_results if r.score > 0]
        result.avg_score = sum(scores) / len(scores) if scores else 0.0

        total_assertions = sum(len(r.assertions) for r in result.judge_results)
        passed_assertions = sum(
            sum(1 for a in r.assertions if a) for r in result.judge_results
        )
        result.assertion_pass_rate = (
            passed_assertions / total_assertions if total_assertions else 0.0
        )

    return result


# ---------------------------------------------------------------------------
# 完整评估流程
# ---------------------------------------------------------------------------


async def run_llm_judge_eval(
    dataset_path: str,
    all_states: list[dict] | None = None,
) -> list[LLMJudgeCaseResult]:
    """运行完整 LLM Judge 评估（使用真实 GLM-5.1）"""
    from eval.multi_turn_eval import run_eval

    # 运行 BB004 确定性评估（真实 LLM）
    det_results, all_states = await run_eval(dataset_path)

    # 读取数据集
    with open(dataset_path, "r", encoding="utf-8") as f:
        cases = json.load(f)

    # 获取 LLM 配置
    llm_config = get_llm_config()
    print(f"\n[LLM Judge] 模型: {llm_config['model']}, 基地址: {llm_config['base_url']}")

    results = []
    for i, (case, det_result) in enumerate(zip(cases, det_results)):
        final_state = all_states[i] if all_states and i < len(all_states) else {}
        final_state.setdefault("question", case["turns"][-1]["content"])

        result = await _run_llm_judge_for_case(
            case, det_result, llm_config, final_state
        )
        results.append(result)

    return results


# ---------------------------------------------------------------------------
# 报告输出
# ---------------------------------------------------------------------------


def print_full_report(
    det_results: list,
    judge_results: list[LLMJudgeCaseResult],
) -> bool:
    """打印完整评估报告（BB004 + BB005 汇总）"""
    print("\n" + "=" * 70)
    print("R010 多轮对话完整评估报告（GLM-5.1）")
    print("=" * 70)

    # BB004 确定性结果
    print("\n--- BB004 确定性评估 ---")
    det_passed = 0
    for r in det_results:
        all_pass = all(
            [
                r.state_check.passed,
                r.tool_calls.passed,
                r.transcript.passed,
                r.deterministic_filter.passed,
            ]
        )
        if all_pass:
            det_passed += 1
        status = "PASS" if all_pass else "FAIL"
        print(f"  {r.test_id}: {status}")
    print(f"  BB004 汇总: {det_passed}/{len(det_results)}")

    # BB005 LLM Judge 结果
    print("\n--- BB005 LLM-as-Judge 评估（GLM-5.1） ---")
    all_scores: list[int] = []
    all_assertions_total = 0
    all_assertions_passed = 0

    for r in judge_results:
        if not r.judge_results:
            neg_tag = " [NEG]" if r.negative else ""
            print(f"  {r.test_id}{neg_tag}: (跳过 — 负面用例或首轮)")
            continue

        judge_details = []
        for jr in r.judge_results:
            all_scores.append(jr.score)
            all_assertions_total += len(jr.assertions)
            all_assertions_passed += sum(1 for a in jr.assertions if a)
            judge_details.append(f"{jr.dimension}={jr.score}")

        neg_tag = " [NEG]" if r.negative else ""
        print(
            f"  {r.test_id}{neg_tag}: avg={r.avg_score:.1f}, "
            f"assertions={r.assertion_pass_rate:.0%}, "
            f"[{', '.join(judge_details)}]"
        )

    overall_avg = sum(all_scores) / len(all_scores) if all_scores else 0
    overall_assertion_rate = (
        all_assertions_passed / all_assertions_total
        if all_assertions_total
        else 0
    )

    print("\n  BB005 汇总:")
    print(f"    平均得分: {overall_avg:.1f}/5")
    print(f"    断言通过率: {overall_assertion_rate:.0%}")

    # 综合结论
    print(f"\n{'=' * 70}")
    det_all_pass = det_passed == len(det_results)
    llm_pass = overall_avg >= 3.5 and overall_assertion_rate >= 0.7

    if det_all_pass and llm_pass:
        overall_status = "PASS"
    elif det_all_pass:
        overall_status = "CONDITIONAL_PASS"
    else:
        overall_status = "FAIL"

    print(f"综合结论: {overall_status}")
    print(
        f"  BB004 确定性: "
        f"{'PASS' if det_all_pass else 'FAIL'} "
        f"({det_passed}/{len(det_results)})"
    )
    print(
        f"  BB005 LLM Judge: "
        f"{'PASS' if llm_pass else 'CONDITIONAL'} "
        f"(avg={overall_avg:.1f}, assertions={overall_assertion_rate:.0%})"
    )
    print(f"{'=' * 70}\n")

    return det_all_pass and llm_pass


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="R010 多轮对话 LLM-as-Judge 评估（GLM-5.1）"
    )
    parser.add_argument(
        "--dataset", required=True, help="评估数据集 JSON 路径"
    )
    args = parser.parse_args()

    # BB004 + BB005 一起跑（都用真实 LLM）
    judge_results = asyncio.run(run_llm_judge_eval(args.dataset))

    # 从 judge_results 中提取 det_results
    det_results = [jr.deterministic_result for jr in judge_results]

    all_passed = print_full_report(det_results, judge_results)
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
