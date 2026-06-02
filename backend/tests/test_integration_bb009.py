"""BB009 端到端集成验证测试

覆盖场景：
1. POST /api/chat 正常路径 — TestClient + mock 全部依赖
2. POST /api/chat Rerank 降级路径 — reranker 抛出 RuntimeError
3. run_context_precision — EvalRunner 输出有效 Precision@K
4. run_regression — EvalRunner 输出 EvalReport
5. run_faithfulness — EvalRunner 输出 FaithfulnessReport
"""

import os
import sys
import json
import tempfile
from unittest.mock import MagicMock, patch

os.environ.setdefault("DASHSCOPE_API_KEY", "test-api-key-for-testing")

# Mock rank_bm25 模块（测试环境可能未安装），避免 app.main 导入失败
if "rank_bm25" not in sys.modules:
    sys.modules["rank_bm25"] = MagicMock()

import pytest
from fastapi.testclient import TestClient

from app.rag.models import ChunkMetadata, QueryResult
from app.chat.schemas import ChatResponse
from app.domain.models import SourceReference
from tests.conftest import make_query_result
from tests._helpers import make_settings, make_source_ref
from app.evaluation.eval_runner import (
    EvalRunner,
    ContextPrecisionReport,
    FaithfulnessReport,
    EvalReport,
)
from app.evaluation.eval_types import EvalItem, EvalSource, RetrievalTruth
from app.evaluation.eval_set_loader import EvalSetLoader
from app.middleware.auth import UserContext, get_current_user

# 测试用 mock 用户
_test_user = UserContext(user_id="user-123", username="testuser")


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def make_eval_items() -> list[EvalItem]:
    """构造测试用评估条目"""
    return [
        EvalItem(
            id="q001",
            question="什么是函数？",
            retrieval_truth=RetrievalTruth(
                mode="ANY",
                sources=[
                    EvalSource(
                        book="必修第一册",
                        page_start=1,
                        page_end=5,
                        section_id="必修第一册::1.1",
                    )
                ],
            ),
            key_facts=["函数的定义", "定义域"],
            reference_answer="函数是一种特殊的对应关系...",
            suite="regression",
        ),
        EvalItem(
            id="q002",
            question="什么是集合？",
            retrieval_truth=RetrievalTruth(
                mode="ALL",
                sources=[
                    EvalSource(
                        book="必修第一册",
                        page_start=3,
                        page_end=8,
                        section_id="必修第一册::1.1",
                    ),
                    EvalSource(
                        book="必修第一册",
                        page_start=10,
                        page_end=15,
                        section_id="必修第一册::1.2",
                    ),
                ],
            ),
            key_facts=["集合的定义", "元素"],
            reference_answer="集合是一些确定的、不同的对象的整体...",
            suite="regression",
        ),
    ]


def _create_eval_json_file(items: list[EvalItem]) -> str:
    """将 EvalItem 列表写入临时 JSON 文件，返回文件路径"""
    data = [item.to_dict() for item in items]
    tmpdir = tempfile.mkdtemp()
    filepath = os.path.join(tmpdir, "test_eval.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return filepath


# ===================================================================
# 测试 1: POST /api/chat 正常路径
# ===================================================================


class TestChatEndpointNormal:
    """POST /api/chat 正常路径集成测试"""

    def test_chat_normal_path(self):
        """TestClient 调用 /api/chat，mock 全部底层依赖，验证正常返回"""
        from app.main import app

        # 准备 mock 数据
        r1 = make_query_result("v1", "函数是一种特殊的对应关系", 0.95)
        r2 = make_query_result("v2", "集合是确定的不同的对象", 0.85)

        mock_embedding = MagicMock()
        mock_embedding.embed_query.return_value = [0.1, 0.2, 0.3]

        mock_vector_store = MagicMock()
        mock_vector_store.query.return_value = [r1, r2]

        mock_bm25 = MagicMock()
        mock_bm25.query.return_value = [r1]

        mock_reranker = MagicMock()
        mock_reranker.rerank.return_value = [r1]

        sources = [make_source_ref("v1")]
        mock_generator = MagicMock()
        mock_generator.generate.return_value = ("函数是一种对应关系", sources)

        mock_settings = make_settings()

        # 注入 app.state（跳过 lifespan）
        app.state.embedding = mock_embedding
        app.state.vector_store = mock_vector_store
        app.state.bm25 = mock_bm25
        app.state.reranker = mock_reranker
        app.state.generator = mock_generator

        with patch("app.chat.dependencies.settings", mock_settings):
            app.dependency_overrides[get_current_user] = lambda: _test_user
            client = TestClient(app)
            response = client.post(
                "/api/chat",
                json={"question": "什么是函数？", "top_k": 5},
            )
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert data["answer"] == "函数是一种对应关系"
        assert len(data["sources"]) >= 1
        assert data["context_used"] > 0
        assert data["degraded"] is False
        assert data["degradation_reason"] is None


# ===================================================================
# 测试 2: POST /api/chat Rerank 降级路径
# ===================================================================


class TestChatEndpointRerankDegraded:
    """POST /api/chat Rerank 降级路径集成测试"""

    def test_chat_rerank_degraded(self):
        """reranker 抛出 RuntimeError，验证 degraded=True 且 answer 仍非空"""
        from app.main import app

        r1 = make_query_result("v1", "函数是一种特殊的对应关系", 0.95)

        mock_embedding = MagicMock()
        mock_embedding.embed_query.return_value = [0.1, 0.2]

        mock_vector_store = MagicMock()
        mock_vector_store.query.return_value = [r1]

        mock_bm25 = MagicMock()
        mock_bm25.query.return_value = []

        # Reranker 抛出异常
        mock_reranker = MagicMock()
        mock_reranker.rerank.side_effect = RuntimeError("API service unavailable")

        sources = [make_source_ref("v1")]
        mock_generator = MagicMock()
        mock_generator.generate.return_value = ("降级后的回答", sources)

        mock_settings = make_settings(rerank_top_n=3, chat_max_context_tokens=5000)

        app.state.embedding = mock_embedding
        app.state.vector_store = mock_vector_store
        app.state.bm25 = mock_bm25
        app.state.reranker = mock_reranker
        app.state.generator = mock_generator

        with patch("app.chat.dependencies.settings", mock_settings):
            app.dependency_overrides[get_current_user] = lambda: _test_user
            client = TestClient(app)
            response = client.post(
                "/api/chat",
                json={"question": "什么是函数？", "top_k": 5},
            )
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert data["answer"] == "降级后的回答"
        assert data["degraded"] is True
        assert data["degradation_reason"] == "rerank_failed"
        assert len(data["sources"]) >= 1


# ===================================================================
# 测试 3: run_context_precision 输出有效 Precision@K
# ===================================================================


class TestRunContextPrecision:
    """EvalRunner.run_context_precision 集成测试"""

    def test_context_precision_output(self):
        """mock 全部依赖，验证 ContextPrecisionReport 输出格式和数据"""
        items = make_eval_items()
        filepath = _create_eval_json_file(items)
        eval_dir = os.path.dirname(filepath)
        filename = os.path.basename(filepath)

        # Mock embedding 返回固定向量
        mock_embedding = MagicMock()
        mock_embedding.embed_query.return_value = [0.1, 0.2]

        # Mock vector_store 返回匹配结果
        results = [
            make_query_result(
                "c1",
                "函数定义",
                0.95,
                section_id="必修第一册::1.1",
                page_start=1,
                page_end=5,
            ),
            make_query_result(
                "c2",
                "其他内容",
                0.60,
                section_id="必修第一册::2.1",
                page_start=50,
                page_end=55,
            ),
        ]
        mock_vector_store = MagicMock()
        mock_vector_store.query.return_value = results

        loader = EvalSetLoader(eval_dir=eval_dir)
        runner = EvalRunner(
            embedding_service=mock_embedding,
            vector_store=mock_vector_store,
            eval_loader=loader,
        )

        report = runner.run_context_precision(filename)

        # 验证输出类型
        assert isinstance(report, ContextPrecisionReport)

        # 验证 overall_precision 在合理范围内
        assert 0.0 <= report.overall_precision <= 1.0

        # 验证 details 非空
        assert len(report.details) == len(items)

        # 验证每条 detail 格式
        for detail in report.details:
            assert detail.item_id
            assert detail.question
            assert 0.0 <= detail.precision_at_k <= 1.0
            assert detail.total_k >= 0
            assert detail.matched_count >= 0

        # 验证第一条至少有部分匹配（section_id 匹配）
        assert report.details[0].matched_count >= 1
        assert report.details[0].precision_at_k > 0.0

        # 验证 to_dict 可序列化
        report_dict = report.to_dict()
        assert "overall_precision" in report_dict
        assert "details" in report_dict

        # 清理临时文件
        os.unlink(filepath)
        os.rmdir(eval_dir)


# ===================================================================
# 测试 4: run_regression 输出 EvalReport
# ===================================================================


class TestRunRegression:
    """EvalRunner.run_regression 集成测试"""

    def test_regression_output(self):
        """mock 全部依赖，验证 EvalReport 输出格式和数据"""
        items = make_eval_items()
        filepath = _create_eval_json_file(items)
        eval_dir = os.path.dirname(filepath)
        filename = os.path.basename(filepath)

        mock_embedding = MagicMock()
        mock_embedding.embed_query.return_value = [0.1, 0.2]

        # 构造检索结果：q001 命中，q002 命中
        results_q001 = [
            make_query_result("c1", "函数定义", 0.95, page_start=1, page_end=5),
            make_query_result("c2", "其他", 0.50, page_start=100, page_end=101),
        ]
        results_q002 = [
            make_query_result("c3", "集合定义", 0.90, page_start=3, page_end=8),
            make_query_result("c4", "更多内容", 0.85, page_start=10, page_end=15),
        ]

        mock_vector_store = MagicMock()
        mock_vector_store.query.side_effect = [results_q001, results_q002]

        loader = EvalSetLoader(eval_dir=eval_dir)
        runner = EvalRunner(
            embedding_service=mock_embedding,
            vector_store=mock_vector_store,
            eval_loader=loader,
        )

        report = runner.run_regression(filename)

        # 验证输出类型
        assert isinstance(report, EvalReport)

        # 验证 overall 指标
        assert report.overall.total_questions == 2
        assert 0.0 <= report.overall.hit_rate_at_5 <= 1.0
        assert 0.0 <= report.overall.hit_rate_at_10 <= 1.0
        assert 0.0 <= report.overall.mrr <= 1.0

        # 验证 details
        assert len(report.details) == 2
        for detail in report.details:
            assert detail.id
            assert detail.question
            assert detail.mode in ("ANY", "ALL", "NEGATIVE")

        # 验证 to_dict 可序列化
        report_dict = report.to_dict()
        assert "overall" in report_dict
        assert "by_book" in report_dict
        assert "details" in report_dict

        # 清理
        os.unlink(filepath)
        os.rmdir(eval_dir)


# ===================================================================
# 测试 5: run_faithfulness 输出 FaithfulnessReport
# ===================================================================


class TestRunFaithfulness:
    """EvalRunner.run_faithfulness 集成测试"""

    def test_faithfulness_output(self):
        """mock 全部依赖（含 reranker/generator/graders），验证 FaithfulnessReport"""
        items = make_eval_items()
        filepath = _create_eval_json_file(items)
        eval_dir = os.path.dirname(filepath)
        filename = os.path.basename(filepath)

        mock_embedding = MagicMock()
        mock_embedding.embed_query.return_value = [0.1, 0.2]

        results = [
            make_query_result("c1", "函数定义文本", 0.95, page_start=1, page_end=5),
            make_query_result("c2", "更多文本", 0.80, page_start=3, page_end=8),
        ]
        mock_vector_store = MagicMock()
        mock_vector_store.query.return_value = results

        mock_reranker = MagicMock()
        mock_reranker.rerank.return_value = results[:1]

        sources = [make_source_ref("c1")]
        mock_generator = MagicMock()
        mock_generator.generate.return_value = ("函数是一种对应关系", sources)

        mock_settings = MagicMock()
        mock_settings.similarity_threshold = 0.70
        mock_settings.rerank_top_n = 3
        mock_settings.newapi_api_key = "test-key"
        mock_settings.newapi_base_url = "http://localhost:13000/v1"
        mock_settings.llm_model = "test-model"

        loader = EvalSetLoader(eval_dir=eval_dir)
        runner = EvalRunner(
            embedding_service=mock_embedding,
            vector_store=mock_vector_store,
            eval_loader=loader,
            reranker=mock_reranker,
            generator=mock_generator,
            settings=mock_settings,
        )

        # Mock graders 避免真实 LLM 调用
        mock_det_grader = MagicMock()
        mock_det_grader.check.return_value = MagicMock(passed=True, failures=[])

        from app.evaluation.graders.llm_judge import JudgeResult, ClaimVerdict, CoverageResult

        mock_judge_result = JudgeResult(
            claims=[
                ClaimVerdict(claim="函数是一种对应关系", verdict="Yes"),
            ],
            coverage=[
                CoverageResult(fact="函数的定义", status="covered"),
                CoverageResult(fact="定义域", status="partially_covered"),
            ],
            faithfulness=1.0,
            coverage_score=0.75,
            unknown_ratio=0.0,
        )
        mock_llm_judge = MagicMock()
        mock_llm_judge.judge.return_value = mock_judge_result

        with patch(
            "app.evaluation.graders.deterministic.DeterministicGrader",
            return_value=mock_det_grader,
        ), patch(
            "app.evaluation.graders.llm_judge.LLMJudge",
            return_value=mock_llm_judge,
        ):
            report = runner.run_faithfulness(filename)

        # 验证输出类型
        assert isinstance(report, FaithfulnessReport)

        # 验证汇总指标
        assert 0.0 <= report.overall_faithfulness <= 1.0
        assert 0.0 <= report.overall_coverage <= 1.0
        assert 0.0 <= report.avg_unknown_ratio <= 1.0

        # 验证 details 非空
        assert len(report.details) == len(items)

        # 验证每条 detail 格式
        for detail in report.details:
            assert detail.item_id
            assert detail.question
            assert 0.0 <= detail.faithfulness <= 1.0
            assert 0.0 <= detail.coverage <= 1.0
            assert 0.0 <= detail.unknown_ratio <= 1.0
            assert isinstance(detail.deterministic_passed, bool)

        # 验证 to_dict 可序列化
        report_dict = report.to_dict()
        assert "overall_faithfulness" in report_dict
        assert "overall_coverage" in report_dict
        assert "avg_unknown_ratio" in report_dict
        assert "details" in report_dict

        # 清理
        os.unlink(filepath)
        os.rmdir(eval_dir)
