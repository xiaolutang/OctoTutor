"""EvalRunner 扩展评估方法单元测试

测试 run_context_precision、run_faithfulness、run_regression、run_full。
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.config import Settings
from app.domain.models import SourceReference
from app.evaluation.eval_runner import (
    ContextPrecisionDetail,
    ContextPrecisionReport,
    EvalReport,
    EvalRunner,
    FaithfulnessDetail,
    FaithfulnessReport,
    FullEvalReport,
)
from app.evaluation.eval_set_loader import EvalSetLoader
from app.evaluation.eval_types import EvalItem, EvalSource, RetrievalTruth
from app.rag.models import ChunkMetadata, QueryResult


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def make_eval_item(
    item_id: str = "q001",
    question: str = "测试问题",
    mode: str = "ANY",
    sources: list[dict] | None = None,
    key_facts: list[str] | None = None,
    suite: str = "regression",
    section_id: str | None = None,
) -> EvalItem:
    """构造 EvalItem 辅助函数"""
    if sources is None:
        sources = [{"book": "必修第一册", "page_start": 1, "page_end": 10}]

    eval_sources = [EvalSource(**s) for s in sources]
    if section_id and len(eval_sources) == 1:
        eval_sources[0].section_id = section_id
    truth = RetrievalTruth(mode=mode, sources=eval_sources)
    return EvalItem(
        id=item_id,
        question=question,
        retrieval_truth=truth,
        key_facts=key_facts or [],
        suite=suite,
    )


def make_query_result(
    book: str = "必修第一册",
    page: int = 5,
    score: float = 0.9,
    section_id: str = "",
) -> QueryResult:
    """构造 QueryResult 辅助函数"""
    return QueryResult(
        chunk_id=f"test::{book}::p{page}",
        text=f"测试文本 page={page}",
        metadata=ChunkMetadata(
            book=book,
            chapter="测试章",
            section="测试节",
            section_id=section_id or f"{book}::s1",
            page=page,
            page_start=page,
            page_end=page,
        ),
        score=score,
    )


def make_eval_json_file(items: list[dict], tmpdir: str) -> str:
    """创建临时评估集 JSON 文件"""
    filepath = os.path.join(tmpdir, "test_eval.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False)
    return filepath


def make_runner(
    embedding_service=None,
    vector_store=None,
    eval_loader=None,
    reranker=None,
    generator=None,
    settings=None,
) -> EvalRunner:
    """构造 EvalRunner 辅助函数"""
    if embedding_service is None:
        embedding_service = MagicMock()
    if vector_store is None:
        vector_store = MagicMock()
    if eval_loader is None:
        eval_loader = MagicMock()
    return EvalRunner(
        embedding_service=embedding_service,
        vector_store=vector_store,
        eval_loader=eval_loader,
        reranker=reranker,
        generator=generator,
        settings=settings,
    )


# ---------------------------------------------------------------------------
# 测试 run_context_precision
# ---------------------------------------------------------------------------


class TestRunContextPrecision:
    """测试 run_context_precision 方法"""

    def test_basic_context_precision(self):
        """基本 Context Precision 计算"""
        # 准备数据
        items = [
            make_eval_item(
                item_id="q001",
                question="什么是函数？",
                sources=[{"book": "必修第一册", "page_start": 1, "page_end": 10}],
                section_id="必修第一册::s1",
            ),
        ]

        mock_loader = MagicMock()
        mock_loader.load.return_value = items

        mock_embedding = MagicMock()
        mock_embedding.embed_query.return_value = [0.1, 0.2, 0.3]

        mock_store = MagicMock()
        mock_store.query.return_value = [
            make_query_result(section_id="必修第一册::s1", score=0.95),
            make_query_result(page=6, section_id="必修第一册::s2", score=0.80),
        ]

        runner = make_runner(
            embedding_service=mock_embedding,
            vector_store=mock_store,
            eval_loader=mock_loader,
        )

        report = runner.run_context_precision("test.json", top_k=10)

        assert isinstance(report, ContextPrecisionReport)
        assert len(report.details) == 1
        assert report.details[0].item_id == "q001"
        # 1 个匹配 / 2 个结果 = 0.5
        assert report.details[0].precision_at_k == pytest.approx(0.5)
        assert report.details[0].matched_count == 1
        assert report.details[0].total_k == 2
        assert report.overall_precision == pytest.approx(0.5)

    def test_context_precision_negative_mode(self):
        """NEGATIVE 模式应返回 precision=0"""
        items = [
            make_eval_item(
                item_id="q_neg",
                question="无关问题",
                mode="NEGATIVE",
                sources=[],
            ),
        ]

        mock_loader = MagicMock()
        mock_loader.load.return_value = items

        runner = make_runner(eval_loader=mock_loader)
        report = runner.run_context_precision("test.json")

        assert report.details[0].precision_at_k == 0.0
        assert report.details[0].total_k == 0

    def test_context_precision_no_section_id_fallback(self):
        """无 section_id 时 fallback 到 page range 匹配"""
        items = [
            make_eval_item(
                item_id="q002",
                question="测试问题",
                sources=[{"book": "必修第一册", "page_start": 1, "page_end": 10}],
                # 不设 section_id
            ),
        ]

        mock_loader = MagicMock()
        mock_loader.load.return_value = items

        mock_embedding = MagicMock()
        mock_embedding.embed_query.return_value = [0.1]

        mock_store = MagicMock()
        mock_store.query.return_value = [
            make_query_result(page=5, score=0.9),   # 在范围内
            make_query_result(page=20, score=0.7),   # 不在范围内
        ]

        runner = make_runner(
            embedding_service=mock_embedding,
            vector_store=mock_store,
            eval_loader=mock_loader,
        )

        report = runner.run_context_precision("test.json")
        # page=5 匹配, page=20 不匹配 -> precision = 1/2 = 0.5
        assert report.details[0].precision_at_k == pytest.approx(0.5)

    def test_context_precision_empty_items(self):
        """空评估集"""
        mock_loader = MagicMock()
        mock_loader.load.return_value = []

        runner = make_runner(eval_loader=mock_loader)
        report = runner.run_context_precision("test.json")

        assert report.overall_precision == 0.0
        assert len(report.details) == 0

    def test_context_precision_report_to_dict(self):
        """测试 ContextPrecisionReport.to_dict()"""
        report = ContextPrecisionReport(
            overall_precision=0.75,
            details=[
                ContextPrecisionDetail(
                    item_id="q001",
                    question="测试",
                    precision_at_k=0.75,
                    matched_count=3,
                    total_k=4,
                ),
            ],
        )
        d = report.to_dict()
        assert d["overall_precision"] == 0.75
        assert len(d["details"]) == 1
        assert d["details"][0]["item_id"] == "q001"


# ---------------------------------------------------------------------------
# 测试 run_faithfulness
# ---------------------------------------------------------------------------


class TestRunFaithfulness:
    """测试 run_faithfulness 方法"""

    def test_faithfulness_without_reranker_raises(self):
        """缺少 reranker 时抛出 RuntimeError"""
        runner = make_runner()
        with pytest.raises(RuntimeError, match="reranker"):
            runner.run_faithfulness("test.json")

    def test_faithfulness_without_generator_raises(self):
        """缺少 generator 时抛出 RuntimeError"""
        mock_reranker = MagicMock()
        runner = make_runner(reranker=mock_reranker)
        with pytest.raises(RuntimeError, match="generator"):
            runner.run_faithfulness("test.json")

    @patch("app.evaluation.graders.llm_judge.OpenAI")
    def test_faithfulness_basic_flow(self, mock_openai_cls):
        """基本 Faithfulness 评估流程"""
        # Mock LLM client
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_choice = MagicMock()
        mock_choice.message.content = json.dumps({
            "claims": [{"claim": "函数是映射", "verdict": "Yes"}],
            "coverage": [{"fact": "定义域", "status": "covered"}],
        })
        mock_client.chat.completions.create.return_value.choices = [mock_choice]

        # 准备数据
        items = [
            make_eval_item(
                item_id="q001",
                question="什么是函数？",
                key_facts=["定义域"],
            ),
        ]

        mock_loader = MagicMock()
        mock_loader.load.return_value = items

        mock_embedding = MagicMock()
        mock_embedding.embed_query.return_value = [0.1, 0.2]

        mock_store = MagicMock()
        qr = make_query_result(score=0.95)
        mock_store.query.return_value = [qr]

        mock_reranker = MagicMock()
        mock_reranker.rerank.return_value = [qr]

        mock_generator = MagicMock()
        mock_generator.generate.return_value = (
            "函数是一种映射关系",
            [SourceReference(
                chunk_id=qr.chunk_id,
                book=qr.metadata.book,
                section=qr.metadata.section,
                page_start=qr.metadata.page_start,
                page_end=qr.metadata.page_end,
            )],
        )

        mock_settings = MagicMock(spec=Settings)
        mock_settings.similarity_threshold = 0.7
        mock_settings.rerank_top_n = 3
        mock_settings.newapi_api_key = "test-key"
        mock_settings.newapi_base_url = "http://test.local"
        mock_settings.llm_model = "test-model"

        runner = make_runner(
            embedding_service=mock_embedding,
            vector_store=mock_store,
            eval_loader=mock_loader,
            reranker=mock_reranker,
            generator=mock_generator,
            settings=mock_settings,
        )

        report = runner.run_faithfulness("test.json")

        assert isinstance(report, FaithfulnessReport)
        assert len(report.details) == 1
        assert report.details[0].item_id == "q001"
        assert report.details[0].faithfulness == 1.0
        assert report.details[0].coverage == 1.0
        assert report.details[0].unknown_ratio == 0.0
        assert report.details[0].deterministic_passed is True

        assert report.overall_faithfulness == 1.0
        assert report.overall_coverage == 1.0
        assert report.avg_unknown_ratio == 0.0

    def test_faithfulness_report_to_dict(self):
        """测试 FaithfulnessReport.to_dict()"""
        report = FaithfulnessReport(
            overall_faithfulness=0.8,
            overall_coverage=0.6,
            avg_unknown_ratio=0.1,
            overall_relevance=0.7,
            details=[
                FaithfulnessDetail(
                    item_id="q001",
                    question="测试",
                    faithfulness=0.8,
                    coverage=0.6,
                    unknown_ratio=0.1,
                    deterministic_passed=True,
                    relevance=0.7,
                    relevance_label="partially_relevant",
                ),
            ],
        )
        d = report.to_dict()
        assert d["overall_faithfulness"] == 0.8
        assert d["overall_coverage"] == 0.6
        assert d["avg_unknown_ratio"] == 0.1
        assert d["overall_relevance"] == 0.7
        assert len(d["details"]) == 1

    @patch("app.evaluation.graders.llm_judge.OpenAI")
    def test_faithfulness_empty_results(self, mock_openai_cls):
        """检索结果为空（低于阈值过滤后）"""
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        items = [
            make_eval_item(item_id="q001", question="测试"),
        ]

        mock_loader = MagicMock()
        mock_loader.load.return_value = items

        mock_embedding = MagicMock()
        mock_embedding.embed_query.return_value = [0.1]

        # 所有结果分数都低于阈值
        mock_store = MagicMock()
        mock_store.query.return_value = [
            make_query_result(score=0.3),
        ]

        mock_reranker = MagicMock()
        mock_reranker.rerank.return_value = []

        mock_generator = MagicMock()

        mock_settings = MagicMock(spec=Settings)
        mock_settings.similarity_threshold = 0.7
        mock_settings.rerank_top_n = 3
        mock_settings.newapi_api_key = "test-key"
        mock_settings.newapi_base_url = "http://test.local"
        mock_settings.llm_model = "test-model"

        runner = make_runner(
            embedding_service=mock_embedding,
            vector_store=mock_store,
            eval_loader=mock_loader,
            reranker=mock_reranker,
            generator=mock_generator,
            settings=mock_settings,
        )

        report = runner.run_faithfulness("test.json")

        # 过滤后为空 -> 默认值
        assert report.details[0].faithfulness == 0.0
        assert report.details[0].coverage == 0.0
        assert report.details[0].deterministic_passed is False


# ---------------------------------------------------------------------------
# 测试 run_regression
# ---------------------------------------------------------------------------


class TestRunRegression:
    """测试 run_regression 方法"""

    def test_regression_filters_suite(self):
        """只筛选 suite=regression 的 items"""
        items = [
            make_eval_item(item_id="q001", suite="regression"),
            make_eval_item(item_id="q002", suite="extended"),
            make_eval_item(item_id="q003", suite="regression"),
        ]

        mock_loader = MagicMock()
        mock_loader.load.return_value = items

        mock_embedding = MagicMock()
        mock_embedding.embed_query.return_value = [0.1, 0.2]

        mock_store = MagicMock()
        mock_store.query.return_value = [
            make_query_result(page=5, score=0.9),
        ]

        runner = make_runner(
            embedding_service=mock_embedding,
            vector_store=mock_store,
            eval_loader=mock_loader,
        )

        report = runner.run_regression("test.json")

        assert isinstance(report, EvalReport)
        # 只有 q001 和 q003 是 regression
        assert len(report.details) == 2
        assert report.overall.total_questions == 2

    def test_regression_no_matching_items(self):
        """无 regression items 时返回空报告"""
        items = [
            make_eval_item(item_id="q001", suite="extended"),
        ]

        mock_loader = MagicMock()
        mock_loader.load.return_value = items

        runner = make_runner(eval_loader=mock_loader)
        report = runner.run_regression("test.json")

        assert len(report.details) == 0
        assert report.overall.total_questions == 0

    def test_regression_uses_existing_logic(self):
        """run_regression 复用现有 run() 的底层逻辑"""
        items = [
            make_eval_item(
                item_id="q001",
                question="函数是什么？",
                sources=[{"book": "必修第一册", "page_start": 1, "page_end": 10}],
                suite="regression",
            ),
        ]

        mock_loader = MagicMock()
        mock_loader.load.return_value = items

        mock_embedding = MagicMock()
        mock_embedding.embed_query.return_value = [0.1]

        mock_store = MagicMock()
        mock_store.query.return_value = [
            make_query_result(page=5, score=0.95),
        ]

        runner = make_runner(
            embedding_service=mock_embedding,
            vector_store=mock_store,
            eval_loader=mock_loader,
        )

        report = runner.run_regression("test.json")
        assert report.overall.hit_rate_at_5 == 1.0


# ---------------------------------------------------------------------------
# 测试 run_full
# ---------------------------------------------------------------------------


class TestRunFull:
    """测试 run_full 方法"""

    def test_full_without_reranker_raises(self):
        """缺少 reranker 时抛出 RuntimeError"""
        runner = make_runner()
        with pytest.raises(RuntimeError, match="reranker"):
            runner.run_full("test.json")

    def test_full_without_generator_raises(self):
        """缺少 generator 时抛出 RuntimeError"""
        mock_reranker = MagicMock()
        runner = make_runner(reranker=mock_reranker)
        with pytest.raises(RuntimeError, match="generator"):
            runner.run_full("test.json")

    @patch("app.evaluation.graders.llm_judge.OpenAI")
    def test_full_aggregates_all_reports(self, mock_openai_cls):
        """run_full 汇总所有指标"""
        # Mock LLM client
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_choice = MagicMock()
        mock_choice.message.content = json.dumps({
            "claims": [{"claim": "测试", "verdict": "Yes"}],
            "coverage": [{"fact": "知识点A", "status": "covered"}],
        })
        mock_client.chat.completions.create.return_value.choices = [mock_choice]

        items = [
            make_eval_item(
                item_id="q001",
                question="什么是函数？",
                sources=[{"book": "必修第一册", "page_start": 1, "page_end": 10}],
                key_facts=["知识点A"],
                suite="regression",
            ),
        ]

        mock_loader = MagicMock()
        mock_loader.load.return_value = items

        mock_embedding = MagicMock()
        mock_embedding.embed_query.return_value = [0.1]

        mock_store = MagicMock()
        qr = make_query_result(score=0.95)
        mock_store.query.return_value = [qr]

        mock_reranker = MagicMock()
        mock_reranker.rerank.return_value = [qr]

        mock_generator = MagicMock()
        mock_generator.generate.return_value = (
            "函数是映射",
            [SourceReference(
                chunk_id=qr.chunk_id,
                book=qr.metadata.book,
                section=qr.metadata.section,
                page_start=qr.metadata.page_start,
                page_end=qr.metadata.page_end,
            )],
        )

        mock_settings = MagicMock(spec=Settings)
        mock_settings.similarity_threshold = 0.7
        mock_settings.rerank_top_n = 3
        mock_settings.newapi_api_key = "test-key"
        mock_settings.newapi_base_url = "http://test.local"
        mock_settings.llm_model = "test-model"

        runner = make_runner(
            embedding_service=mock_embedding,
            vector_store=mock_store,
            eval_loader=mock_loader,
            reranker=mock_reranker,
            generator=mock_generator,
            settings=mock_settings,
        )

        report = runner.run_full("test.json")

        assert isinstance(report, FullEvalReport)
        assert report.regression is not None
        assert isinstance(report.regression, EvalReport)
        assert report.context_precision is not None
        assert isinstance(report.context_precision, ContextPrecisionReport)
        assert report.faithfulness is not None
        assert isinstance(report.faithfulness, FaithfulnessReport)

    def test_full_eval_report_to_dict(self):
        """测试 FullEvalReport.to_dict()"""
        report = FullEvalReport(
            regression=None,
            context_precision=None,
            faithfulness=None,
        )
        d = report.to_dict()
        assert d["regression"] is None
        assert d["context_precision"] is None
        assert d["faithfulness"] is None


# ---------------------------------------------------------------------------
# 测试现有 run() 方法不受影响
# ---------------------------------------------------------------------------


class TestExistingRunUnaffected:
    """确保现有 run() 方法不受新代码影响"""

    def test_run_still_works(self):
        """基本 run() 方法仍然正常工作"""
        items = [
            make_eval_item(
                item_id="q001",
                question="测试问题",
                sources=[{"book": "必修第一册", "page_start": 1, "page_end": 10}],
            ),
        ]

        mock_loader = MagicMock()
        mock_loader.load.return_value = items

        mock_embedding = MagicMock()
        mock_embedding.embed_query.return_value = [0.1, 0.2]

        mock_store = MagicMock()
        mock_store.query.return_value = [
            make_query_result(page=5, score=0.9),
        ]

        runner = make_runner(
            embedding_service=mock_embedding,
            vector_store=mock_store,
            eval_loader=mock_loader,
        )

        report = runner.run("test.json")

        assert isinstance(report, EvalReport)
        assert report.overall.total_questions == 1

    def test_run_with_optional_params_not_provided(self):
        """不提供 reranker/generator/settings 时 run() 正常工作"""
        items = [
            make_eval_item(item_id="q001"),
        ]

        mock_loader = MagicMock()
        mock_loader.load.return_value = items

        mock_embedding = MagicMock()
        mock_embedding.embed_query.return_value = [0.1]

        mock_store = MagicMock()
        mock_store.query.return_value = [make_query_result()]

        # 只传必选参数
        runner = EvalRunner(
            embedding_service=mock_embedding,
            vector_store=mock_store,
            eval_loader=mock_loader,
        )

        report = runner.run("test.json")
        assert isinstance(report, EvalReport)


# ---------------------------------------------------------------------------
# 测试 Relevance 相关性评估
# ---------------------------------------------------------------------------


class TestRelevance:
    """测试 Relevance 相关性评估指标"""

    def test_parse_relevance_relevant(self):
        """_parse_response 正确解析 relevant"""
        from app.evaluation.graders.llm_judge import LLMJudge

        judge = LLMJudge.__new__(LLMJudge)
        raw = json.dumps({
            "claims": [{"claim": "测试", "verdict": "Yes"}],
            "coverage": [{"fact": "知识点", "status": "covered"}],
            "relevance": "relevant",
        })
        result = judge._parse_response(raw)
        assert result.relevance == 1.0
        assert result.relevance_label == "relevant"

    def test_parse_relevance_partially(self):
        """_parse_response 正确解析 partially_relevant"""
        from app.evaluation.graders.llm_judge import LLMJudge

        judge = LLMJudge.__new__(LLMJudge)
        raw = json.dumps({
            "claims": [{"claim": "测试", "verdict": "Yes"}],
            "coverage": [{"fact": "知识点", "status": "covered"}],
            "relevance": "partially_relevant",
        })
        result = judge._parse_response(raw)
        assert result.relevance == 0.5
        assert result.relevance_label == "partially_relevant"

    def test_parse_relevance_not_relevant(self):
        """_parse_response 正确解析 not_relevant"""
        from app.evaluation.graders.llm_judge import LLMJudge

        judge = LLMJudge.__new__(LLMJudge)
        raw = json.dumps({
            "claims": [{"claim": "测试", "verdict": "Yes"}],
            "coverage": [{"fact": "知识点", "status": "covered"}],
            "relevance": "not_relevant",
        })
        result = judge._parse_response(raw)
        assert result.relevance == 0.0
        assert result.relevance_label == "not_relevant"

    def test_parse_relevance_fallback(self):
        """_parse_response 在无 relevance 字段时 fallback 为 not_relevant"""
        from app.evaluation.graders.llm_judge import LLMJudge

        judge = LLMJudge.__new__(LLMJudge)
        raw = json.dumps({
            "claims": [{"claim": "测试", "verdict": "Yes"}],
            "coverage": [{"fact": "知识点", "status": "covered"}],
        })
        result = judge._parse_response(raw)
        assert result.relevance == 0.0
        assert result.relevance_label == "not_relevant"

    def test_parse_relevance_invalid_value_fallback(self):
        """_parse_response 在 relevance 为无效值时 fallback 为 not_relevant"""
        from app.evaluation.graders.llm_judge import LLMJudge

        judge = LLMJudge.__new__(LLMJudge)
        raw = json.dumps({
            "claims": [{"claim": "测试", "verdict": "Yes"}],
            "coverage": [{"fact": "知识点", "status": "covered"}],
            "relevance": "invalid_value",
        })
        result = judge._parse_response(raw)
        assert result.relevance == 0.0
        assert result.relevance_label == "not_relevant"

    def test_faithfulness_detail_contains_relevance(self):
        """FaithfulnessDetail.to_dict 包含 relevance 和 relevance_label"""
        detail = FaithfulnessDetail(
            item_id="q001",
            question="测试问题",
            faithfulness=0.8,
            coverage=0.6,
            unknown_ratio=0.1,
            deterministic_passed=True,
            relevance=1.0,
            relevance_label="relevant",
        )
        d = detail.to_dict()
        assert "relevance" in d
        assert d["relevance"] == 1.0
        assert "relevance_label" in d
        assert d["relevance_label"] == "relevant"

    def test_faithfulness_detail_default_relevance(self):
        """FaithfulnessDetail 默认 relevance 值为 0.0 / not_relevant"""
        detail = FaithfulnessDetail(
            item_id="q001",
            question="测试",
            faithfulness=0.0,
            coverage=0.0,
            unknown_ratio=0.0,
            deterministic_passed=False,
        )
        assert detail.relevance == 0.0
        assert detail.relevance_label == "not_relevant"

    @patch("app.evaluation.graders.llm_judge.OpenAI")
    def test_faithfulness_report_contains_overall_relevance(self, mock_openai_cls):
        """FaithfulnessReport 包含 overall_relevance 字段"""
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_choice = MagicMock()
        mock_choice.message.content = json.dumps({
            "claims": [{"claim": "函数是映射", "verdict": "Yes"}],
            "coverage": [{"fact": "定义域", "status": "covered"}],
            "relevance": "relevant",
        })
        mock_client.chat.completions.create.return_value.choices = [mock_choice]

        items = [
            make_eval_item(
                item_id="q001",
                question="什么是函数？",
                key_facts=["定义域"],
            ),
        ]

        mock_loader = MagicMock()
        mock_loader.load.return_value = items

        mock_embedding = MagicMock()
        mock_embedding.embed_query.return_value = [0.1, 0.2]

        mock_store = MagicMock()
        qr = make_query_result(score=0.95)
        mock_store.query.return_value = [qr]

        mock_reranker = MagicMock()
        mock_reranker.rerank.return_value = [qr]

        mock_generator = MagicMock()
        mock_generator.generate.return_value = (
            "函数是一种映射关系",
            [SourceReference(
                chunk_id=qr.chunk_id,
                book=qr.metadata.book,
                section=qr.metadata.section,
                page_start=qr.metadata.page_start,
                page_end=qr.metadata.page_end,
            )],
        )

        mock_settings = MagicMock(spec=Settings)
        mock_settings.similarity_threshold = 0.7
        mock_settings.rerank_top_n = 3
        mock_settings.newapi_api_key = "test-key"
        mock_settings.newapi_base_url = "http://test.local"
        mock_settings.llm_model = "test-model"

        runner = make_runner(
            embedding_service=mock_embedding,
            vector_store=mock_store,
            eval_loader=mock_loader,
            reranker=mock_reranker,
            generator=mock_generator,
            settings=mock_settings,
        )

        report = runner.run_faithfulness("test.json")

        assert report.details[0].relevance == 1.0
        assert report.details[0].relevance_label == "relevant"
        assert report.overall_relevance == 1.0

    def test_judge_result_default_relevance(self):
        """JudgeResult 默认 relevance 值为 0.0 / not_relevant"""
        from app.evaluation.graders.llm_judge import JudgeResult

        result = JudgeResult(
            claims=[],
            coverage=[],
            faithfulness=0.0,
            coverage_score=0.0,
            unknown_ratio=1.0,
        )
        assert result.relevance == 0.0
        assert result.relevance_label == "not_relevant"
