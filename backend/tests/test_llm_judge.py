"""LLM Judge 单元测试

使用 mock LLM response 测试 Faithfulness/Coverage/Unknown 解析逻辑。
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from app.evaluation.graders.llm_judge import (
    ClaimVerdict,
    CoverageResult,
    JudgeResult,
    LLMJudge,
)


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _make_mock_response(content: str) -> MagicMock:
    """构造 mock OpenAI response"""
    mock_choice = MagicMock()
    mock_choice.message.content = content
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    return mock_response


# ---------------------------------------------------------------------------
# 测试 _parse_response
# ---------------------------------------------------------------------------


class TestParseResponse:
    """测试 LLMJudge._parse_response 解析逻辑"""

    def setup_method(self):
        self.judge = LLMJudge.__new__(LLMJudge)
        self.judge._model = "test-model"
        self.judge._client = MagicMock()

    def test_parse_normal_response(self):
        """正常 JSON 响应解析"""
        raw = json.dumps({
            "claims": [
                {"claim": "函数是映射", "verdict": "Yes"},
                {"claim": "函数是关系", "verdict": "No"},
                {"claim": "函数有周期", "verdict": "Unknown"},
            ],
            "coverage": [
                {"fact": "定义域", "status": "covered"},
                {"fact": "值域", "status": "not_covered"},
                {"fact": "对应法则", "status": "partially_covered"},
            ],
        })
        result = self.judge._parse_response(raw)

        assert len(result.claims) == 3
        assert result.claims[0].verdict == "Yes"
        assert result.claims[1].verdict == "No"
        assert result.claims[2].verdict == "Unknown"

        assert len(result.coverage) == 3
        assert result.coverage[0].status == "covered"
        assert result.coverage[1].status == "not_covered"
        assert result.coverage[2].status == "partially_covered"

    def test_parse_markdown_wrapped_response(self):
        """带 markdown 代码块的响应解析"""
        inner = json.dumps({
            "claims": [{"claim": "测试", "verdict": "Yes"}],
            "coverage": [{"fact": "知识点A", "status": "covered"}],
        })
        raw = f"```json\n{inner}\n```"
        result = self.judge._parse_response(raw)

        assert len(result.claims) == 1
        assert result.claims[0].verdict == "Yes"

    def test_parse_invalid_json_returns_default(self):
        """无效 JSON 返回默认结果"""
        result = self.judge._parse_response("not valid json")

        assert result.claims == []
        assert result.faithfulness == 0.0
        assert result.coverage_score == 0.0
        assert result.unknown_ratio == 1.0

    def test_parse_invalid_verdict_normalized_to_unknown(self):
        """不合法的 verdict 归为 Unknown"""
        raw = json.dumps({
            "claims": [{"claim": "测试", "verdict": "Maybe"}],
            "coverage": [{"fact": "知识点A", "status": "invalid_status"}],
        })
        result = self.judge._parse_response(raw)

        assert result.claims[0].verdict == "Unknown"
        assert result.coverage[0].status == "not_covered"

    def test_parse_empty_claims_and_coverage(self):
        """空 claims 和 coverage"""
        raw = json.dumps({"claims": [], "coverage": []})
        result = self.judge._parse_response(raw)

        assert result.claims == []
        assert result.coverage == []
        assert result.faithfulness == 0.0
        assert result.coverage_score == 0.0
        assert result.unknown_ratio == 0.0


# ---------------------------------------------------------------------------
# 测试 Faithfulness 计算
# ---------------------------------------------------------------------------


class TestFaithfulnessCalc:
    """测试 Faithfulness 分数和 Unknown 比例计算"""

    def test_all_yes(self):
        """全部 Yes -> faithfulness = 1.0"""
        claims = [
            ClaimVerdict(claim="c1", verdict="Yes"),
            ClaimVerdict(claim="c2", verdict="Yes"),
        ]
        f, u = LLMJudge._calc_faithfulness_and_unknown(claims)
        assert f == 1.0
        assert u == 0.0

    def test_all_no(self):
        """全部 No -> faithfulness = 0.0"""
        claims = [
            ClaimVerdict(claim="c1", verdict="No"),
            ClaimVerdict(claim="c2", verdict="No"),
        ]
        f, u = LLMJudge._calc_faithfulness_and_unknown(claims)
        assert f == 0.0
        assert u == 0.0

    def test_mixed_yes_no(self):
        """混合 Yes/No -> faithfulness = 2/4 = 0.5"""
        claims = [
            ClaimVerdict(claim="c1", verdict="Yes"),
            ClaimVerdict(claim="c2", verdict="Yes"),
            ClaimVerdict(claim="c3", verdict="No"),
            ClaimVerdict(claim="c4", verdict="No"),
        ]
        f, u = LLMJudge._calc_faithfulness_and_unknown(claims)
        assert f == pytest.approx(0.5)
        assert u == 0.0

    def test_unknown_excluded_from_faithfulness(self):
        """Unknown 不计入分子分母"""
        claims = [
            ClaimVerdict(claim="c1", verdict="Yes"),
            ClaimVerdict(claim="c2", verdict="Unknown"),
            ClaimVerdict(claim="c3", verdict="No"),
        ]
        # supported=1, unsupported=1 -> faithfulness = 1/(1+1) = 0.5
        f, u = LLMJudge._calc_faithfulness_and_unknown(claims)
        assert f == pytest.approx(0.5)
        assert u == pytest.approx(1 / 3)

    def test_all_unknown(self):
        """全部 Unknown -> faithfulness = 0.0, unknown_ratio = 1.0"""
        claims = [
            ClaimVerdict(claim="c1", verdict="Unknown"),
            ClaimVerdict(claim="c2", verdict="Unknown"),
        ]
        f, u = LLMJudge._calc_faithfulness_and_unknown(claims)
        assert f == 0.0
        assert u == 1.0

    def test_empty_claims(self):
        """空 claims -> faithfulness = 0.0, unknown_ratio = 0.0"""
        f, u = LLMJudge._calc_faithfulness_and_unknown([])
        assert f == 0.0
        assert u == 0.0


# ---------------------------------------------------------------------------
# 测试 Coverage 计算
# ---------------------------------------------------------------------------


class TestCoverageCalc:
    """测试 Coverage 分数计算"""

    def test_all_covered(self):
        """全部 covered -> coverage = 1.0"""
        coverage = [
            CoverageResult(fact="f1", status="covered"),
            CoverageResult(fact="f2", status="covered"),
        ]
        assert LLMJudge._calc_coverage(coverage) == 1.0

    def test_none_covered(self):
        """全部 not_covered -> coverage = 0.0"""
        coverage = [
            CoverageResult(fact="f1", status="not_covered"),
            CoverageResult(fact="f2", status="not_covered"),
        ]
        assert LLMJudge._calc_coverage(coverage) == 0.0

    def test_partially_covered_counts_half(self):
        """partially_covered 算 0.5"""
        coverage = [
            CoverageResult(fact="f1", status="covered"),       # 1.0
            CoverageResult(fact="f2", status="partially_covered"),  # 0.5
            CoverageResult(fact="f3", status="not_covered"),   # 0.0
        ]
        # (1.0 + 0.5 + 0.0) / 3 = 0.5
        assert LLMJudge._calc_coverage(coverage) == pytest.approx(0.5)

    def test_mixed_coverage(self):
        """混合覆盖"""
        coverage = [
            CoverageResult(fact="f1", status="covered"),
            CoverageResult(fact="f2", status="covered"),
            CoverageResult(fact="f3", status="partially_covered"),
            CoverageResult(fact="f4", status="not_covered"),
        ]
        # (1 + 1 + 0.5 + 0) / 4 = 0.625
        assert LLMJudge._calc_coverage(coverage) == pytest.approx(0.625)

    def test_empty_coverage(self):
        """空 coverage -> 0.0"""
        assert LLMJudge._calc_coverage([]) == 0.0


# ---------------------------------------------------------------------------
# 测试 judge 方法（mock LLM 调用）
# ---------------------------------------------------------------------------


class TestJudgeMethod:
    """测试 LLMJudge.judge 方法（mock OpenAI client）"""

    @patch("app.evaluation.graders.llm_judge.OpenAI")
    def test_judge_with_mock_llm(self, mock_openai_cls):
        """完整 judge 流程 mock 测试"""
        # 准备 mock
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        llm_response = json.dumps({
            "claims": [
                {"claim": "函数是一种映射关系", "verdict": "Yes"},
                {"claim": "函数有三要素", "verdict": "Yes"},
                {"claim": "函数是集合", "verdict": "No"},
            ],
            "coverage": [
                {"fact": "定义域", "status": "covered"},
                {"fact": "值域", "status": "partially_covered"},
                {"fact": "对应法则", "status": "covered"},
            ],
        })
        mock_client.chat.completions.create.return_value = _make_mock_response(
            llm_response
        )

        # 执行
        judge = LLMJudge(api_key="test-key", base_url="http://test.local")
        result = judge.judge(
            answer="函数是一种映射关系，有三要素。函数是集合。",
            context="函数是一种特殊的映射...",
            key_facts=["定义域", "值域", "对应法则"],
        )

        # 验证结果
        assert isinstance(result, JudgeResult)
        # faithfulness = 2 / (2+1) = 0.6667
        assert result.faithfulness == pytest.approx(2.0 / 3.0)
        # coverage = (1 + 0.5 + 1) / 3 = 0.8333
        assert result.coverage_score == pytest.approx(2.5 / 3.0)
        # unknown_ratio = 0 / 3 = 0.0
        assert result.unknown_ratio == 0.0

        # 验证 LLM 被调用
        mock_client.chat.completions.create.assert_called_once()
        call_kwargs = mock_client.chat.completions.create.call_args
        assert call_kwargs.kwargs["model"] == "glm-5.1"
        assert call_kwargs.kwargs["temperature"] == 0.0

    @patch("app.evaluation.graders.llm_judge.OpenAI")
    def test_judge_with_unknown_claims(self, mock_openai_cls):
        """含 Unknown claims 的 judge 测试"""
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        llm_response = json.dumps({
            "claims": [
                {"claim": "声明1", "verdict": "Yes"},
                {"claim": "声明2", "verdict": "Unknown"},
                {"claim": "声明3", "verdict": "Unknown"},
            ],
            "coverage": [
                {"fact": "知识点A", "status": "covered"},
            ],
        })
        mock_client.chat.completions.create.return_value = _make_mock_response(
            llm_response
        )

        judge = LLMJudge(api_key="test-key", base_url="http://test.local")
        result = judge.judge("answer", "context", ["知识点A"])

        # faithfulness = 1 / (1+0) = 1.0 (Unknown 不计入分母)
        assert result.faithfulness == 1.0
        # unknown_ratio = 2 / 3
        assert result.unknown_ratio == pytest.approx(2.0 / 3.0)
        assert result.coverage_score == 1.0
