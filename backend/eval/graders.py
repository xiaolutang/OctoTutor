"""多轮对话确定性 Graders

Grader 2: state_check — AgentState 最终状态验证
Grader 3: tool_calls — 节点调用行为验证
Grader 4: transcript — 执行轨迹约束验证
Grader 5: deterministic_filter — 粗筛验证
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

MAX_ELAPSED_MS = 120_000  # 单轮全链路耗时上限（适配真实 LLM 延迟）


@dataclass
class GraderResult:
    """单个 grader 的验证结果"""

    name: str
    passed: bool
    details: list[str] = field(default_factory=list)


@dataclass
class TestCaseResult:
    """单个测试用例的完整评估结果"""

    test_id: str
    level: str
    category: str
    negative: bool
    state_check: GraderResult
    tool_calls: GraderResult
    transcript: GraderResult
    deterministic_filter: GraderResult
    tracked_metrics: dict[str, Any] = field(default_factory=dict)
    execution_time_ms: float = 0.0


def state_check(
    state: dict,
    expected: dict,
    is_first_turn: bool,
) -> GraderResult:
    """Grader 2: 验证 AgentState 最终状态

    断言：
    - 首轮: rewritten_question 应为 None/空
    - 首轮: conversation_summary 应为 None/空
    - 多轮 rewrite: rewritten_question is not None (expected.rewrite_should_trigger)
    - summarize 触发后: summary non-empty (expected.summary_triggered)
    """
    failures = []

    if is_first_turn:
        rewritten = state.get("rewritten_question")
        if rewritten:
            failures.append(
                f"首轮 rewritten_question 应为 null，实际: {rewritten}"
            )

        summary = state.get("conversation_summary")
        if summary:
            failures.append(
                f"首轮 conversation_summary 应为 null，实际: {summary}"
            )

    if expected.get("rewrite_should_trigger") and not is_first_turn:
        rewritten = state.get("rewritten_question")
        if not rewritten:
            failures.append("多轮应触发 rewrite，但 rewritten_question 为 null")

    if expected.get("summary_triggered"):
        summary = state.get("conversation_summary")
        if not summary:
            failures.append("summarize 应触发但 conversation_summary 为 null")

    return GraderResult(
        name="state_check",
        passed=len(failures) == 0,
        details=failures,
    )


def tool_calls_check(
    event_keys: list[str],
    expected: dict,
    is_first_turn: bool,
) -> GraderResult:
    """Grader 3: 验证节点调用行为

    通过事件流中的节点名来验证：
    - 所有输入统一走线性路径: summarize → rewrite → retrieve → respond
    """
    failures = []

    expected_path = ["summarize", "rewrite", "retrieve", "respond"]
    if event_keys != expected_path:
        failures.append(
            f"路径应为 {expected_path}，实际: {event_keys}"
        )

    return GraderResult(
        name="tool_calls",
        passed=len(failures) == 0,
        details=failures,
    )


def transcript_check(
    events: list[dict],
    elapsed_ms: float,
    is_first_turn: bool,
) -> GraderResult:
    """Grader 4: 验证执行轨迹约束

    - 首轮不触发 summarize LLM 调用（summarize 返回 {}）
    - 单轮全链路 <= 120s（真实 LLM 每轮约 15-25s）
    """
    failures = []

    # 全链路耗时上限
    if elapsed_ms > MAX_ELAPSED_MS:
        failures.append(f"全链路耗时 {elapsed_ms:.0f}ms 超过 {MAX_ELAPSED_MS/1000:.0f}s 上限")

    return GraderResult(
        name="transcript",
        passed=len(failures) == 0,
        details=failures,
    )


def deterministic_filter(
    state: dict,
    events: list[dict],  # noqa: ARG001 — 保留参数以兼容调用方签名
    expected: dict,
    negative: bool,
) -> GraderResult:
    """Grader 5: 粗筛验证

    正面用例：关键词断言 + 数量/长度检查
    负面用例：验证"不应该发生"的行为确实没发生
    """
    failures = []

    if negative:
        # 负面用例验证
        rewritten = state.get("rewritten_question", "")
        question = state.get("question", "")

        if expected.get("rewrite_should_not_contain"):
            for kw in expected["rewrite_should_not_contain"]:
                if rewritten and kw in rewritten:
                    failures.append(
                        f"负面用例 rewrite 不应包含 '{kw}'，实际: {rewritten}"
                    )

        if expected.get("rewrite_should_not_trigger"):
            if rewritten and rewritten != question:
                failures.append(
                    f"负面用例不应触发 rewrite，但 rewritten_question={rewritten}"
                )
    else:
        # 正面用例验证
        rewritten = state.get("rewritten_question", "")
        if expected.get("rewrite_contains"):
            for kw in expected["rewrite_contains"]:
                if kw not in rewritten:
                    failures.append(
                        f"rewrite 结果应包含 '{kw}'，实际: {rewritten}"
                    )

    return GraderResult(
        name="deterministic_filter",
        passed=len(failures) == 0,
        details=failures,
    )
