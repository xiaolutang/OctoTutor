"""R010 多轮对话确定性评估

使用方式：
    cd backend
    python -m eval.multi_turn_eval --dataset eval/datasets/multi_turn_eval.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from eval.graders import (
    TestCaseResult,
    state_check,
    tool_calls_check,
    transcript_check,
    deterministic_filter,
)


# ---------------------------------------------------------------------------
# Mock LLM — 根据 prompt 内容智能返回
# ---------------------------------------------------------------------------

# 复合数学关键词（优先匹配长词）
_COMPOUND_KEYWORDS = [
    "等差数列", "等比数列", "三角函数", "对数函数",
    "条件概率", "单位圆", "几何意义", "贝叶斯",
]

# 基础数学关键词列表
_MATH_KEYWORDS = {
    "函数", "方程", "不等式", "数列", "集合", "概率", "统计",
    "三角", "向量", "导数", "积分", "极限", "矩阵",
    "直线", "圆", "椭圆", "双曲线", "抛物线", "圆锥",
    "求", "计算", "证明", "解", "化简", "推导",
    "最大值", "最小值", "极值", "单调", "奇偶",
    "排列", "组合", "二项式", "分布",
    "平面", "空间", "坐标", "角度", "距离",
    "公式", "定理", "性质", "定义",
    "模", "通项", "对数", "等差", "等比",
    "单位圆", "图像", "例子", "条件概率", "贝叶斯",
    "几何意义", "余弦", "求和", "运算", "定义域",
    "等差数列", "等比数列", "三角函数", "对数函数",
}


def _extract_keywords(text: str) -> list[str]:
    """从文本中提取数学关键词（优先匹配复合词）"""
    found = []
    # 先匹配复合关键词
    for kw in _COMPOUND_KEYWORDS:
        if kw in text:
            found.append(kw)
    # 再匹配基础关键词（跳过已被复合词包含的）
    for kw in _MATH_KEYWORDS:
        if kw in text and not any(kw in compound for compound in found if compound != kw):
            found.append(kw)
    return found


async def _mock_llm_ainvoke(messages):
    """智能 mock LLM：根据 prompt 内容返回合适的 rewrite 或 respond"""
    last_msg = messages[-1].content if messages else ""

    # 如果是 rewrite prompt（包含"改写后的独立问题"）
    if "改写后的独立问题" in last_msg:
        # 分区提取关键词：从"对话历史"区域提取主概念
        history_section = last_msg.split("对话历史：")[1].split("用户追问：")[0] if "对话历史：" in last_msg else ""

        # 尝试提取用户追问
        question_match = re.search(r"用户追问：(.+?)(?:\n|$)", last_msg)
        question = question_match.group(1).strip() if question_match else ""

        # 替换代词
        pronouns = {"它", "它们", "这个", "那个", "其"}
        result = question
        for pronoun in pronouns:
            result = result.replace(pronoun, "")

        # 找到历史中的主概念（用户第一个问题中的核心复合关键词）
        # 这些是首轮用户消息中的关键词，代表对话主题
        first_user_keywords = []
        user_lines = [line for line in history_section.split("\n") if line.startswith("用户：")]
        if user_lines:
            first_user_keywords = _extract_keywords(user_lines[0])

        # 如果追问中缺少主概念，从首轮用户消息中补充
        missing_concepts = [
            kw for kw in first_user_keywords
            if kw not in result and len(kw) >= 2
        ]
        # 按长度降序，优先补全最长的主概念
        missing_concepts.sort(key=len, reverse=True)
        if missing_concepts:
            result = f"{missing_concepts[0]}{result.lstrip('的')}"

        return AIMessage(content=result if result else question)

    # 默认 respond
    return AIMessage(content="这是测试回答")


def _build_graph():
    """构建带 mock 的 graph（使用真实 graph 拓扑 + mock 外部依赖）"""
    from unittest.mock import MagicMock

    from app.agent.graph import create_graph

    # mock ChatService
    mock_chat_service = MagicMock()
    mock_result = MagicMock()
    mock_result.chunks = []
    mock_result.degraded = False
    mock_result.degradation_reason = None
    mock_chat_service._retrieve.return_value = mock_result

    # mock LLMGenerator — 返回智能 mock ChatOpenAI
    mock_generator = MagicMock()
    mock_chat_model = MagicMock()
    mock_chat_model.ainvoke = _mock_llm_ainvoke
    mock_generator.get_chat_model.return_value = mock_chat_model

    graph = create_graph(
        checkpointer=MemorySaver(),
        chat_service=mock_chat_service,
        generator=mock_generator,
    )

    return graph, mock_chat_service, mock_chat_model


def _merge_state_from_events(events: list[dict]) -> dict:
    """从 LangGraph astream 事件列表合并最终 state

    注意：节点返回 {} 时 node_output 为 None，需要跳过。
    """
    merged = {}
    for evt in events:
        for _node_name, node_output in evt.items():
            if isinstance(node_output, dict):
                # messages 用 add_messages reducer，只取非 messages 字段
                for k, v in node_output.items():
                    if k != "messages":
                        merged[k] = v
    return merged


def _extract_event_keys(events: list[dict]) -> list[str]:
    """从事件列表提取节点执行顺序"""
    return [list(e.keys())[0] for e in events]


def _get_last_turn_events(all_events: list[dict]) -> list[dict]:
    """从全部事件中提取最后一轮的事件"""
    last_turn_events = []
    found_start = False
    for evt in reversed(all_events):
        key = list(evt.keys())[0]
        if key == "summarize":
            last_turn_events.insert(0, evt)
            found_start = True
            break
        last_turn_events.insert(0, evt)

    if not found_start:
        last_turn_events = all_events  # fallback

    return last_turn_events


async def _run_single_case(
    graph,
    case: dict,
) -> TestCaseResult:
    """执行单条评估用例"""
    turns = case["turns"]
    expected = case["expected"]
    is_negative = case.get("negative", False)

    start_time = time.perf_counter()

    # 逐轮执行
    all_events: list[dict] = []
    all_states: list[dict] = []
    conversation_id = f"eval-{case['id']}"

    config = {
        "configurable": {
            "thread_id": conversation_id,
        }
    }

    for _i, turn in enumerate(turns):
        user_msg = turn["content"]

        input_state = {
            "messages": [HumanMessage(content=user_msg)],
            "question": user_msg,
        }

        turn_events: list[dict] = []
        async for event in graph.astream(input_state, config=config):
            turn_events.append(event)

        all_events.extend(turn_events)

        # 合并当前轮次的 state
        merged = _merge_state_from_events(turn_events)
        all_states.append(merged)

    elapsed_ms = (time.perf_counter() - start_time) * 1000

    # 取最终 state
    final_state = all_states[-1] if all_states else {}
    # 注入 question（最终轮的 question）
    final_state["question"] = turns[-1]["content"]
    is_first_turn = len(turns) == 1

    # 取最后一轮的事件 keys
    last_turn_events = _get_last_turn_events(all_events)
    last_turn_keys = _extract_event_keys(last_turn_events)

    # 运行 graders
    sc = state_check(final_state, expected, is_first_turn=is_first_turn)
    tc = tool_calls_check(last_turn_keys, expected, is_first_turn=is_first_turn)
    tr = transcript_check(all_events, elapsed_ms, is_first_turn=is_first_turn)
    df = deterministic_filter(final_state, all_events, expected, is_negative)

    # Tracked metrics
    metrics = {
        "n_events": len(all_events),
        "n_turns": len(turns),
        "time_to_last_token_ms": round(elapsed_ms, 1),
    }

    return TestCaseResult(
        test_id=case["id"],
        level=case["level"],
        category=case["category"],
        negative=is_negative,
        state_check=sc,
        tool_calls=tc,
        transcript=tr,
        deterministic_filter=df,
        tracked_metrics=metrics,
        execution_time_ms=elapsed_ms,
    )


async def run_eval(dataset_path: str) -> list[TestCaseResult]:
    """运行完整评估"""
    with open(dataset_path, "r", encoding="utf-8") as f:
        cases = json.load(f)

    graph, _, _ = _build_graph()

    results = []
    for case in cases:
        result = await _run_single_case(graph, case)
        results.append(result)

    return results


def print_report(results: list[TestCaseResult]) -> bool:
    """打印评估报告，返回 True 如果全部通过"""
    print("\n" + "=" * 60)
    print("R010 多轮对话确定性评估报告")
    print("=" * 60)

    all_passed = True
    for r in results:
        graders_all_pass = (
            r.state_check.passed
            and r.tool_calls.passed
            and r.transcript.passed
            and r.deterministic_filter.passed
        )
        status = "PASS" if graders_all_pass else "FAIL"
        if status == "FAIL":
            all_passed = False
        neg_tag = " [NEG]" if r.negative else ""
        print(f"\n{r.test_id}{neg_tag}: {status}")

        for grader in [
            r.state_check,
            r.tool_calls,
            r.transcript,
            r.deterministic_filter,
        ]:
            icon = "v" if grader.passed else "X"
            detail_str = (
                "pass"
                if grader.passed
                else "FAIL - " + "; ".join(grader.details)
            )
            print(f"  [{icon}] {grader.name}: {detail_str}")

        print(f"  metrics: {r.execution_time_ms:.0f}ms | {r.tracked_metrics}")

    # 汇总
    total = len(results)
    passed = sum(
        1
        for r in results
        if all(
            [
                r.state_check.passed,
                r.tool_calls.passed,
                r.transcript.passed,
                r.deterministic_filter.passed,
            ]
        )
    )

    print(f"\n{'=' * 60}")
    print(
        f"汇总: {passed}/{total} 通过"
        f" ({'ALL PASS' if all_passed else 'HAS FAILURES'})"
    )
    print(f"{'=' * 60}\n")

    return all_passed


def main():
    parser = argparse.ArgumentParser(
        description="R010 多轮对话确定性评估"
    )
    parser.add_argument(
        "--dataset", required=True, help="评估数据集 JSON 路径"
    )
    args = parser.parse_args()

    results = asyncio.run(run_eval(args.dataset))
    all_passed = print_report(results)

    # 额外运行 static_analysis
    print("--- static_analysis ---")
    import subprocess

    try:
        r = subprocess.run(
            ["python3", "-m", "ruff", "check", "eval/"],
            capture_output=True,
            text=True,
        )
        if r.returncode == 0:
            print("ruff check eval/: PASS")
        else:
            print(f"ruff check eval/: FAIL\n{r.stdout}")
            all_passed = False
    except FileNotFoundError:
        print("ruff: SKIPPED (not installed)")

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
