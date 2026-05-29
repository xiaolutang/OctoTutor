"""R010 Grounding 评估维度测试"""

import json
from pathlib import Path

from eval.judge_prompts import GROUNDING_PROMPT

_EVAL_DATASET = Path(__file__).resolve().parent.parent / "eval" / "datasets" / "multi_turn_eval.json"


class TestGroundingPrompt:
    """GROUNDING_PROMPT 常量格式验证"""

    def test_grounding_prompt_exists(self):
        """GROUNDING_PROMPT 非空"""
        assert len(GROUNDING_PROMPT) > 100

    def test_grounding_prompt_contains_rubric(self):
        """包含评分标准"""
        assert "评分标准" in GROUNDING_PROMPT
        assert "5 =" in GROUNDING_PROMPT
        assert "1 =" in GROUNDING_PROMPT
        assert "0 = Unknown" in GROUNDING_PROMPT

    def test_grounding_prompt_contains_assertions(self):
        """包含断言检查"""
        assert "断言检查" in GROUNDING_PROMPT
        assert "教材中不存在的数学概念" in GROUNDING_PROMPT

    def test_grounding_prompt_contains_placeholders(self):
        """包含必要的输入占位符"""
        assert "{context}" in GROUNDING_PROMPT
        assert "{question}" in GROUNDING_PROMPT
        assert "{answer}" in GROUNDING_PROMPT

    def test_grounding_prompt_format_works(self):
        """format 不报错"""
        result = GROUNDING_PROMPT.format(
            context="测试教材内容",
            question="测试问题",
            answer="测试回答",
        )
        assert "测试教材内容" in result
        assert "测试问题" in result
        assert "测试回答" in result


class TestEvalDatasetL7:
    """L7 negative context 用例验证"""

    def test_l7_cases_exist(self):
        """eval 数据集中存在 L7 用例"""
        with open(_EVAL_DATASET, "r") as f:
            data = json.load(f)
        l7_cases = [c for c in data if c["level"] == "L7"]
        assert len(l7_cases) >= 5, f"Expected >= 5 L7 cases, got {len(l7_cases)}"

    def test_l7_cases_are_negative(self):
        """L7 用例全部标记为 negative"""
        with open(_EVAL_DATASET, "r") as f:
            data = json.load(f)
        l7_cases = [c for c in data if c["level"] == "L7"]
        for case in l7_cases:
            assert case["negative"] is True, f"{case['id']} should be negative"
            assert case["category"] == "irrelevant_context"

    def test_l7_cases_have_expected_fields(self):
        """L7 用例包含必要的 expected 字段"""
        with open(_EVAL_DATASET, "r") as f:
            data = json.load(f)
        l7_cases = [c for c in data if c["level"] == "L7"]
        for case in l7_cases:
            assert "expected" in case, f"{case['id']} missing expected"
            assert "respond_should_not_use_context" in case["expected"], (
                f"{case['id']} missing respond_should_not_use_context"
            )
