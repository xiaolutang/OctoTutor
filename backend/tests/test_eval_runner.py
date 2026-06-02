"""检索质量评估运行器测试

测试 EvalRunner 的 Hit Rate@K 和 MRR 计算逻辑，
覆盖 ANY/ALL mode、按书分组、报告格式等场景。
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.evaluation.eval_runner import (
    BookMetrics,
    EvalDetail,
    EvalReport,
    EvalRunner,
    OverallMetrics,
    _calc_hit_rate_at_k,
    _calc_keyword_coverage_at_k,
    _calc_mrr,
    _calc_negative_pass_rate,
    _calc_section_hit_at_k,
    _group_by_book,
)
from app.evaluation.eval_set_loader import EvalSetLoader
from app.evaluation.eval_types import EvalItem, EvalSource, RetrievalTruth
from app.rag.models import ChunkMetadata, QueryResult
from tests.conftest import make_query_result, make_eval_query_result
from tests._helpers import make_eval_item


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def create_mock_embedding_and_store(
    query_results_map: dict[str, list[QueryResult]],
) -> tuple[MagicMock, MagicMock]:
    """构造 mock EmbeddingService 和 ChromaDBStore

    Args:
        query_results_map: question -> QueryResult 列表的映射

    Returns:
        (mock_embedding, mock_store) 元组
    """
    mock_embedding = MagicMock()

    def embed_query_side_effect(text: str) -> list[float]:
        return [0.1] * 768

    mock_embedding.embed_query.side_effect = embed_query_side_effect

    mock_store = MagicMock()

    def query_side_effect(
        query_embedding: list[float],
        top_k: int = 5,
        where: dict | None = None,
    ) -> list[QueryResult]:
        # 根据 embedding 的调用顺序返回结果
        # 通过调用计数来确定是第几次查询
        call_idx = mock_store.query.call_count - 1
        questions = list(query_results_map.keys())
        if call_idx < len(questions):
            all_results = query_results_map[questions[call_idx]]
            return all_results[:top_k]
        return []

    mock_store.query.side_effect = query_side_effect

    return mock_embedding, mock_store


def create_eval_json_file(items_data: list[dict]) -> str:
    """创建临时评估集 JSON 文件

    Args:
        items_data: 评估数据列表

    Returns:
        临时目录路径
    """
    tmp_dir = tempfile.mkdtemp()
    json_path = os.path.join(tmp_dir, "test_eval.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(items_data, f, ensure_ascii=False)
    return tmp_dir


# ---------------------------------------------------------------------------
# 测试: _calc_mrr
# ---------------------------------------------------------------------------


class TestCalcMRR:
    """MRR 计算测试"""

    def test_all_hit_rank_1(self) -> None:
        """所有条目都在第 1 位命中 → MRR = 1.0"""
        details = [
            EvalDetail(id="q1", question="Q1", hit=True, first_rank=1, mode="ANY"),
            EvalDetail(id="q2", question="Q2", hit=True, first_rank=1, mode="ANY"),
            EvalDetail(id="q3", question="Q3", hit=True, first_rank=1, mode="ANY"),
        ]
        assert _calc_mrr(details) == pytest.approx(1.0)

    def test_various_ranks(self) -> None:
        """不同排名: rank 1, 2, 3 → MRR = (1/1 + 1/2 + 1/3) / 3"""
        details = [
            EvalDetail(id="q1", question="Q1", hit=True, first_rank=1, mode="ANY"),
            EvalDetail(id="q2", question="Q2", hit=True, first_rank=2, mode="ANY"),
            EvalDetail(id="q3", question="Q3", hit=True, first_rank=3, mode="ANY"),
        ]
        expected = (1.0 / 1 + 1.0 / 2 + 1.0 / 3) / 3
        assert _calc_mrr(details) == pytest.approx(expected)

    def test_no_hits(self) -> None:
        """所有条目都未命中 → MRR = 0.0"""
        details = [
            EvalDetail(id="q1", question="Q1", hit=False, first_rank=0, mode="ANY"),
            EvalDetail(id="q2", question="Q2", hit=False, first_rank=0, mode="ANY"),
        ]
        assert _calc_mrr(details) == pytest.approx(0.0)

    def test_partial_hits(self) -> None:
        """部分命中: rank 1 和 0 → MRR = (1/1 + 0) / 2 = 0.5"""
        details = [
            EvalDetail(id="q1", question="Q1", hit=True, first_rank=1, mode="ANY"),
            EvalDetail(id="q2", question="Q2", hit=False, first_rank=0, mode="ANY"),
        ]
        assert _calc_mrr(details) == pytest.approx(0.5)

    def test_empty_details(self) -> None:
        """空列表 → MRR = 0.0"""
        assert _calc_mrr([]) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# 测试: _calc_hit_rate_at_k
# ---------------------------------------------------------------------------


class TestCalcHitRateAtK:
    """Hit Rate@K 计算测试"""

    def test_all_hit_any_mode_at_k5(self) -> None:
        """ANY mode: 所有 first_rank <= 5 → Hit Rate@5 = 1.0"""
        details = [
            EvalDetail(id="q1", question="Q1", hit=True, first_rank=1, mode="ANY"),
            EvalDetail(id="q2", question="Q2", hit=True, first_rank=3, mode="ANY"),
            EvalDetail(id="q3", question="Q3", hit=True, first_rank=5, mode="ANY"),
        ]
        assert _calc_hit_rate_at_k(details, 5) == pytest.approx(1.0)

    def test_partial_hit_any_mode_at_k5(self) -> None:
        """ANY mode: 2/3 在 top-5 命中 → Hit Rate@5 = 2/3"""
        details = [
            EvalDetail(id="q1", question="Q1", hit=True, first_rank=1, mode="ANY"),
            EvalDetail(id="q2", question="Q2", hit=True, first_rank=6, mode="ANY"),
            EvalDetail(id="q3", question="Q3", hit=True, first_rank=5, mode="ANY"),
        ]
        assert _calc_hit_rate_at_k(details, 5) == pytest.approx(2.0 / 3)

    def test_no_hits_any_mode(self) -> None:
        """ANY mode: 都未命中 → Hit Rate = 0.0"""
        details = [
            EvalDetail(id="q1", question="Q1", hit=False, first_rank=0, mode="ANY"),
            EvalDetail(id="q2", question="Q2", hit=False, first_rank=0, mode="ANY"),
        ]
        assert _calc_hit_rate_at_k(details, 5) == pytest.approx(0.0)

    def test_all_mode_hit(self) -> None:
        """ALL mode: hit=True → 算命中"""
        details = [
            EvalDetail(id="q1", question="Q1", hit=True, first_rank=1, mode="ALL"),
            EvalDetail(id="q2", question="Q2", hit=True, first_rank=3, mode="ALL"),
        ]
        assert _calc_hit_rate_at_k(details, 5) == pytest.approx(1.0)

    def test_all_mode_partial_hit(self) -> None:
        """ALL mode: 部分 hit=True"""
        details = [
            EvalDetail(id="q1", question="Q1", hit=True, first_rank=1, mode="ALL"),
            EvalDetail(id="q2", question="Q2", hit=False, first_rank=0, mode="ALL"),
        ]
        assert _calc_hit_rate_at_k(details, 5) == pytest.approx(0.5)

    def test_empty_details(self) -> None:
        """空列表 → Hit Rate = 0.0"""
        assert _calc_hit_rate_at_k([], 5) == pytest.approx(0.0)

    def test_k10_captures_more_than_k5(self) -> None:
        """K=10 比 K=5 能捕获更多命中"""
        details = [
            EvalDetail(id="q1", question="Q1", hit=True, first_rank=1, mode="ANY"),
            EvalDetail(id="q2", question="Q2", hit=True, first_rank=8, mode="ANY"),
        ]
        # K=5: 只有 q1 命中
        assert _calc_hit_rate_at_k(details, 5) == pytest.approx(0.5)
        # K=10: 两个都命中
        assert _calc_hit_rate_at_k(details, 10) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# 测试: _group_by_book
# ---------------------------------------------------------------------------


class TestGroupByBook:
    """按书分组测试"""

    def test_basic_grouping(self) -> None:
        """基本按书分组"""
        items = [
            make_eval_item("q1", sources=[{"book": "必修第一册", "page_start": 1, "page_end": 5}]),
            make_eval_item("q2", sources=[{"book": "必修第二册", "page_start": 1, "page_end": 5}]),
            make_eval_item("q3", sources=[{"book": "必修第一册", "page_start": 10, "page_end": 15}]),
        ]
        details = [
            EvalDetail(id="q1", question="Q1", hit=True, first_rank=1, mode="ANY"),
            EvalDetail(id="q2", question="Q2", hit=False, first_rank=0, mode="ANY"),
            EvalDetail(id="q3", question="Q3", hit=True, first_rank=2, mode="ANY"),
        ]

        groups = _group_by_book(details, items)

        assert "必修第一册" in groups
        assert "必修第二册" in groups
        assert len(groups["必修第一册"]) == 2
        assert len(groups["必修第二册"]) == 1

    def test_empty_lists(self) -> None:
        """空列表"""
        groups = _group_by_book([], [])
        assert groups == {}


# ---------------------------------------------------------------------------
# 测试: EvalRunner 集成（mock）
# ---------------------------------------------------------------------------


class TestEvalRunner:
    """EvalRunner 集成测试"""

    def test_any_mode_hit_at_rank_1(self) -> None:
        """ANY mode: 第一个结果即命中 → hit=True, first_rank=1"""
        eval_data = [
            {
                "id": "q001",
                "question": "什么是集合？",
                "retrieval_truth": {
                    "mode": "ANY",
                    "sources": [{"book": "必修第一册", "page_start": 1, "page_end": 8}],
                },
            }
        ]

        query_results = [
            make_eval_query_result(book="必修第一册", page=3),  # 命中
            make_eval_query_result(book="必修第二册", page=10),  # 不命中
        ]

        tmp_dir = create_eval_json_file(eval_data)
        try:
            mock_embedding, mock_store = create_mock_embedding_and_store(
                {"什么是集合？": query_results}
            )
            loader = EvalSetLoader(eval_dir=tmp_dir)
            runner = EvalRunner(
                embedding_service=mock_embedding,
                vector_store=mock_store,
                eval_loader=loader,
            )
            report = runner.run(eval_filename="test_eval.json")

            assert report.overall.total_questions == 1
            assert report.overall.hit_rate_at_5 == pytest.approx(1.0)
            assert report.overall.hit_rate_at_10 == pytest.approx(1.0)
            assert report.overall.mrr == pytest.approx(1.0)
            assert len(report.details) == 1
            assert report.details[0].hit is True
            assert report.details[0].first_rank == 1
            assert report.details[0].mode == "ANY"
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_any_mode_hit_at_rank_3(self) -> None:
        """ANY mode: 第 3 个结果命中 → first_rank=3, MRR=1/3"""
        eval_data = [
            {
                "id": "q001",
                "question": "函数的定义",
                "retrieval_truth": {
                    "mode": "ANY",
                    "sources": [{"book": "必修第一册", "page_start": 43, "page_end": 55}],
                },
            }
        ]

        query_results = [
            make_eval_query_result(book="必修第二册", page=10),  # 不命中
            make_eval_query_result(book="选择性必修第一册", page=50),  # 不命中
            make_eval_query_result(book="必修第一册", page=50),  # 命中
            make_eval_query_result(book="必修第一册", page=80),  # 不在范围
        ]

        tmp_dir = create_eval_json_file(eval_data)
        try:
            mock_embedding, mock_store = create_mock_embedding_and_store(
                {"函数的定义": query_results}
            )
            loader = EvalSetLoader(eval_dir=tmp_dir)
            runner = EvalRunner(
                embedding_service=mock_embedding,
                vector_store=mock_store,
                eval_loader=loader,
            )
            report = runner.run(eval_filename="test_eval.json")

            assert report.details[0].hit is True
            assert report.details[0].first_rank == 3
            assert report.overall.mrr == pytest.approx(1.0 / 3)
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_any_mode_no_hit(self) -> None:
        """ANY mode: 所有结果都不在范围内 → hit=False, first_rank=0"""
        eval_data = [
            {
                "id": "q001",
                "question": "什么是集合？",
                "retrieval_truth": {
                    "mode": "ANY",
                    "sources": [{"book": "必修第一册", "page_start": 1, "page_end": 8}],
                },
            }
        ]

        query_results = [
            make_eval_query_result(book="必修第二册", page=10),
            make_eval_query_result(book="选择性必修第一册", page=50),
        ]

        tmp_dir = create_eval_json_file(eval_data)
        try:
            mock_embedding, mock_store = create_mock_embedding_and_store(
                {"什么是集合？": query_results}
            )
            loader = EvalSetLoader(eval_dir=tmp_dir)
            runner = EvalRunner(
                embedding_service=mock_embedding,
                vector_store=mock_store,
                eval_loader=loader,
            )
            report = runner.run(eval_filename="test_eval.json")

            assert report.details[0].hit is False
            assert report.details[0].first_rank == 0
            assert report.overall.hit_rate_at_5 == pytest.approx(0.0)
            assert report.overall.mrr == pytest.approx(0.0)
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_all_mode_all_sources_hit(self) -> None:
        """ALL mode: 两个 source 都命中 → hit=True"""
        eval_data = [
            {
                "id": "q001",
                "question": "双曲线和抛物线",
                "retrieval_truth": {
                    "mode": "ALL",
                    "sources": [
                        {"book": "选择性必修第一册", "page_start": 99, "page_end": 115},
                        {"book": "选择性必修第一册", "page_start": 116, "page_end": 130},
                    ],
                },
            }
        ]

        query_results = [
            make_eval_query_result(book="选择性必修第一册", page=100),  # 命中 source 1
            make_eval_query_result(book="选择性必修第一册", page=120),  # 命中 source 2
            make_eval_query_result(book="必修第一册", page=10),
        ]

        tmp_dir = create_eval_json_file(eval_data)
        try:
            mock_embedding, mock_store = create_mock_embedding_and_store(
                {"双曲线和抛物线": query_results}
            )
            loader = EvalSetLoader(eval_dir=tmp_dir)
            runner = EvalRunner(
                embedding_service=mock_embedding,
                vector_store=mock_store,
                eval_loader=loader,
            )
            report = runner.run(eval_filename="test_eval.json")

            assert report.details[0].hit is True
            assert report.details[0].mode == "ALL"
            assert report.details[0].first_rank == 1  # 第一个结果命中 source 1
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_all_mode_missing_one_source(self) -> None:
        """ALL mode: 只命中一个 source → hit=False"""
        eval_data = [
            {
                "id": "q001",
                "question": "排列和组合",
                "retrieval_truth": {
                    "mode": "ALL",
                    "sources": [
                        {"book": "选择性必修第三册", "page_start": 11, "page_end": 22},
                        {"book": "选择性必修第三册", "page_start": 23, "page_end": 35},
                    ],
                },
            }
        ]

        query_results = [
            make_eval_query_result(book="选择性必修第三册", page=15),  # 命中 source 1
            make_eval_query_result(book="必修第一册", page=10),  # 不命中
        ]

        tmp_dir = create_eval_json_file(eval_data)
        try:
            mock_embedding, mock_store = create_mock_embedding_and_store(
                {"排列和组合": query_results}
            )
            loader = EvalSetLoader(eval_dir=tmp_dir)
            runner = EvalRunner(
                embedding_service=mock_embedding,
                vector_store=mock_store,
                eval_loader=loader,
            )
            report = runner.run(eval_filename="test_eval.json")

            assert report.details[0].hit is False
            assert report.details[0].first_rank == 1  # source 1 在第 1 位命中
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_multiple_items_by_book(self) -> None:
        """多条评估按书分组，报告包含 by_book"""
        eval_data = [
            {
                "id": "q001",
                "question": "集合的概念",
                "retrieval_truth": {
                    "mode": "ANY",
                    "sources": [{"book": "必修第一册", "page_start": 1, "page_end": 8}],
                },
            },
            {
                "id": "q002",
                "question": "函数的单调性",
                "retrieval_truth": {
                    "mode": "ANY",
                    "sources": [{"book": "必修第一册", "page_start": 56, "page_end": 70}],
                },
            },
            {
                "id": "q003",
                "question": "平面向量的加法",
                "retrieval_truth": {
                    "mode": "ANY",
                    "sources": [{"book": "必修第二册", "page_start": 1, "page_end": 15}],
                },
            },
        ]

        results_map = {
            "集合的概念": [
                make_eval_query_result(book="必修第一册", page=3),  # 命中
                make_eval_query_result(book="必修第二册", page=10),
            ],
            "函数的单调性": [
                make_eval_query_result(book="必修第二册", page=10),  # 不命中
                make_eval_query_result(book="必修第一册", page=60),  # 命中
            ],
            "平面向量的加法": [
                make_eval_query_result(book="选择性必修第一册", page=10),  # 不命中
                make_eval_query_result(book="必修第二册", page=20),  # 不在范围
            ],
        }

        tmp_dir = create_eval_json_file(eval_data)
        try:
            mock_embedding, mock_store = create_mock_embedding_and_store(results_map)
            loader = EvalSetLoader(eval_dir=tmp_dir)
            runner = EvalRunner(
                embedding_service=mock_embedding,
                vector_store=mock_store,
                eval_loader=loader,
            )
            report = runner.run(eval_filename="test_eval.json")

            # 总体: 2/3 命中
            assert report.overall.total_questions == 3
            assert report.overall.hit_rate_at_5 == pytest.approx(2.0 / 3)
            assert report.overall.hit_rate_at_10 == pytest.approx(2.0 / 3)
            # MRR: q001=1, q002=1/2, q003=0 → (1 + 0.5 + 0) / 3
            assert report.overall.mrr == pytest.approx(0.5)

            # 按书分组
            assert "必修第一册" in report.by_book
            assert "必修第二册" in report.by_book
            assert report.by_book["必修第一册"].count == 2
            assert report.by_book["必修第一册"].hit_rate_at_5 == pytest.approx(1.0)
            assert report.by_book["必修第二册"].count == 1
            assert report.by_book["必修第二册"].hit_rate_at_5 == pytest.approx(0.0)
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_empty_query_results(self) -> None:
        """检索结果为空 → hit=False, first_rank=0"""
        eval_data = [
            {
                "id": "q001",
                "question": "测试问题",
                "retrieval_truth": {
                    "mode": "ANY",
                    "sources": [{"book": "必修第一册", "page_start": 1, "page_end": 8}],
                },
            }
        ]

        tmp_dir = create_eval_json_file(eval_data)
        try:
            mock_embedding, mock_store = create_mock_embedding_and_store(
                {"测试问题": []}
            )
            loader = EvalSetLoader(eval_dir=tmp_dir)
            runner = EvalRunner(
                embedding_service=mock_embedding,
                vector_store=mock_store,
                eval_loader=loader,
            )
            report = runner.run(eval_filename="test_eval.json")

            assert report.details[0].hit is False
            assert report.details[0].first_rank == 0
            assert report.overall.hit_rate_at_5 == pytest.approx(0.0)
            assert report.overall.mrr == pytest.approx(0.0)
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_report_to_dict_serializable(self) -> None:
        """EvalReport.to_dict() 返回 JSON 可序列化字典"""
        report = EvalReport(
            overall=OverallMetrics(
                hit_rate_at_5=0.72,
                hit_rate_at_10=0.88,
                mrr=0.65,
                total_questions=25,
            ),
            by_book={
                "必修第一册": BookMetrics(
                    hit_rate_at_5=0.8,
                    hit_rate_at_10=1.0,
                    mrr=0.7,
                    count=5,
                ),
            },
            details=[
                EvalDetail(
                    id="q001",
                    question="测试问题",
                    hit=True,
                    first_rank=2,
                    mode="ANY",
                ),
            ],
        )

        result = report.to_dict()

        # 验证可以 JSON 序列化
        json_str = json.dumps(result, ensure_ascii=False)
        parsed = json.loads(json_str)

        assert parsed["overall"]["hit_rate_at_5"] == 0.72
        assert parsed["overall"]["mrr"] == 0.65
        assert parsed["overall"]["total_questions"] == 25
        assert "必修第一册" in parsed["by_book"]
        assert parsed["by_book"]["必修第一册"]["count"] == 5
        assert parsed["details"][0]["id"] == "q001"
        assert parsed["details"][0]["hit"] is True
        assert parsed["details"][0]["first_rank"] == 2

    def test_custom_top_k_values(self) -> None:
        """自定义 top_k_values=[3, 7]"""
        eval_data = [
            {
                "id": "q001",
                "question": "测试",
                "retrieval_truth": {
                    "mode": "ANY",
                    "sources": [{"book": "必修第一册", "page_start": 1, "page_end": 10}],
                },
            }
        ]

        query_results = [
            make_eval_query_result(book="必修第二册", page=10),
            make_eval_query_result(book="必修第二册", page=20),
            make_eval_query_result(book="必修第二册", page=30),
            make_eval_query_result(book="必修第二册", page=40),
            make_eval_query_result(book="必修第一册", page=5),  # rank=5, 命中
            make_eval_query_result(book="必修第二册", page=50),
            make_eval_query_result(book="必修第二册", page=60),
        ]

        tmp_dir = create_eval_json_file(eval_data)
        try:
            mock_embedding, mock_store = create_mock_embedding_and_store(
                {"测试": query_results}
            )
            loader = EvalSetLoader(eval_dir=tmp_dir)
            runner = EvalRunner(
                embedding_service=mock_embedding,
                vector_store=mock_store,
                eval_loader=loader,
            )
            report = runner.run(eval_filename="test_eval.json", top_k_values=[3, 7])

            # hit=True（在 max_k=7 范围内命中）
            assert report.details[0].hit is True
            assert report.details[0].first_rank == 5
            # Hit Rate@3 = 0（first_rank=5 > 3）
            assert report.overall.hit_rate_at_5 == pytest.approx(0.0)
            # Hit Rate@10 不会被计算（不在 top_k_values 中），默认 0
            # 但 K=7 也没有对应的字段... 实际上只计算 [3, 7]
            # overall.hit_rate_at_5 和 hit_rate_at_10 来自 top_k_values 默认的 [5, 10]
            # 不，top_k_values=[3, 7] 时，overall 只有 hit_rate_at_5 和 hit_rate_at_10
            # 这两个字段是固定的，top_k_values 只影响实际计算
            # 实际上 _build_report 中对 top_k_values 为 [3, 7] 时
            # hit_rate_by_k = {3: 0.0, 7: 1.0}
            # overall.hit_rate_at_5 = hit_rate_by_k.get(5, 0.0) = 0.0
            # overall.hit_rate_at_10 = hit_rate_by_k.get(10, 0.0) = 0.0
            assert report.overall.hit_rate_at_5 == pytest.approx(0.0)
            assert report.overall.hit_rate_at_10 == pytest.approx(0.0)
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# 测试: EvalDetail / BookMetrics / OverallMetrics 序列化
# ---------------------------------------------------------------------------


class TestDataclassSerialization:
    """数据模型序列化测试"""

    def test_eval_detail_to_dict(self) -> None:
        detail = EvalDetail(id="q1", question="Q", hit=True, first_rank=3, mode="ANY")
        d = detail.to_dict()
        assert d == {
            "id": "q1",
            "question": "Q",
            "hit": True,
            "first_rank": 3,
            "mode": "ANY",
            "section_hit": False,
            "keyword_coverage": 0.0,
        }

    def test_book_metrics_to_dict(self) -> None:
        metrics = BookMetrics(hit_rate_at_5=0.8, hit_rate_at_10=0.9, mrr=0.7, count=5)
        d = metrics.to_dict()
        assert d == {
            "hit_rate_at_5": 0.8,
            "hit_rate_at_10": 0.9,
            "mrr": 0.7,
            "count": 5,
            "section_hit_at_5": 0.0,
            "section_hit_at_10": 0.0,
            "keyword_coverage_at_10": 0.0,
        }

    def test_overall_metrics_to_dict(self) -> None:
        metrics = OverallMetrics(
            hit_rate_at_5=0.72, hit_rate_at_10=0.88, mrr=0.65, total_questions=25
        )
        d = metrics.to_dict()
        assert d == {
            "hit_rate_at_5": 0.72,
            "hit_rate_at_10": 0.88,
            "mrr": 0.65,
            "total_questions": 25,
            "section_hit_at_5": 0.0,
            "section_hit_at_10": 0.0,
            "keyword_coverage_at_10": 0.0,
            "negative_pass_rate": 0.0,
        }


# ---------------------------------------------------------------------------
# 测试: EvalRunner 端到端（使用真实 eval_set.json 路径 + mock）
# ---------------------------------------------------------------------------


class TestEvalRunnerWithRealEvalSet:
    """使用真实 eval_set.json 的端到端测试（mock 检索）"""

    @pytest.fixture
    def eval_dir(self) -> str:
        """返回评估集所在目录"""
        return str(
            Path(__file__).parent.parent / "data" / "evaluation"
        )

    def test_can_load_real_eval_set(self, eval_dir: str) -> None:
        """验证能加载真实评估集并通过运行器"""
        loader = EvalSetLoader(eval_dir=eval_dir)
        items = loader.load("eval_set.json")
        assert len(items) >= 20

        # 构造全部命中的 mock 结果
        mock_embedding = MagicMock()
        mock_embedding.embed_query.return_value = [0.1] * 768

        mock_store = MagicMock()

        def query_side_effect(
            query_embedding: list[float],
            top_k: int = 5,
            where: dict | None = None,
        ) -> list[QueryResult]:
            # 返回一个通用命中结果
            return [
                make_eval_query_result(book="必修第一册", page=3),
                make_eval_query_result(book="必修第二册", page=10),
            ][:top_k]

        mock_store.query.side_effect = query_side_effect

        runner = EvalRunner(
            embedding_service=mock_embedding,
            vector_store=mock_store,
            eval_loader=loader,
        )
        report = runner.run(eval_filename="eval_set.json")

        assert report.overall.total_questions == len(items)
        assert len(report.details) == len(items)
        assert isinstance(report.overall.hit_rate_at_5, float)
        assert isinstance(report.overall.hit_rate_at_10, float)
        assert isinstance(report.overall.mrr, float)

        # 验证报告可序列化
        result_dict = report.to_dict()
        json_str = json.dumps(result_dict, ensure_ascii=False)
        parsed = json.loads(json_str)
        assert parsed["overall"]["total_questions"] == len(items)


# ---------------------------------------------------------------------------
# 测试: RetrievalTruth.check_hit（从 eval_types 复用，验证集成）
# ---------------------------------------------------------------------------


class TestCheckHitIntegration:
    """验证 EvalRunner 与 RetrievalTruth.check_hit 的集成"""

    def test_any_mode_boundary_page(self) -> None:
        """ANY mode: 边界页码测试"""
        source = EvalSource(book="必修第一册", page_start=10, page_end=20)
        truth = RetrievalTruth(mode="ANY", sources=[source])

        # page=10（边界起始）
        assert truth.check_hit([("必修第一册", 10)]) is True
        # page=20（边界结束）
        assert truth.check_hit([("必修第一册", 20)]) is True
        # page=9（边界外）
        assert truth.check_hit([("必修第一册", 9)]) is False
        # page=21（边界外）
        assert truth.check_hit([("必修第一册", 21)]) is False

    def test_all_mode_two_sources(self) -> None:
        """ALL mode: 两个 source 都需要命中"""
        source1 = EvalSource(book="必修第一册", page_start=1, page_end=10)
        source2 = EvalSource(book="必修第二册", page_start=1, page_end=10)
        truth = RetrievalTruth(mode="ALL", sources=[source1, source2])

        # 两个都命中
        assert truth.check_hit([("必修第一册", 5), ("必修第二册", 5)]) is True
        # 只命中 source1
        assert truth.check_hit([("必修第一册", 5), ("必修第一册", 8)]) is False
        # 只命中 source2
        assert truth.check_hit([("必修第二册", 5), ("必修第二册", 8)]) is False
        # 都没命中
        assert truth.check_hit([("必修第三册", 5)]) is False

    def test_first_rank_with_multiple_sources(self) -> None:
        """MRR first_rank 在多 source 场景下找第一个命中"""
        source1 = EvalSource(book="必修第一册", page_start=1, page_end=10)
        source2 = EvalSource(book="必修第二册", page_start=1, page_end=10)
        item = make_eval_item(
            "q1",
            mode="ANY",
            sources=[
                {"book": "必修第一册", "page_start": 1, "page_end": 10},
                {"book": "必修第二册", "page_start": 1, "page_end": 10},
            ],
        )

        book_page_list = [
            ("选择性必修第一册", 5),  # rank=1, 不命中
            ("必修第二册", 3),  # rank=2, 命中 source2
            ("必修第一册", 5),  # rank=3, 命中 source1
        ]

        first_rank = EvalRunner._find_first_rank(item, book_page_list)
        assert first_rank == 2  # 找到第一个命中的位置


# ---------------------------------------------------------------------------
# 测试: EvalSource 新字段（section_id / required_keywords）
# ---------------------------------------------------------------------------


class TestEvalSourceNewFields:
    """EvalSource section_id 和 required_keywords 测试"""

    def test_section_id_optional(self) -> None:
        """section_id 可选，默认为 None"""
        source = EvalSource(book="必修第一册", page_start=1, page_end=10)
        assert source.section_id is None
        assert source.required_keywords == []

    def test_section_id_set(self) -> None:
        """可以设置 section_id"""
        source = EvalSource(
            book="必修第一册",
            page_start=1,
            page_end=10,
            section_id="必修第一册::1.1",
        )
        assert source.section_id == "必修第一册::1.1"

    def test_required_keywords_set(self) -> None:
        """可以设置 required_keywords"""
        source = EvalSource(
            book="必修第一册",
            page_start=1,
            page_end=10,
            required_keywords=["集合", "子集"],
        )
        assert source.required_keywords == ["集合", "子集"]

    def test_to_dict_with_new_fields(self) -> None:
        """to_dict 包含 section_id 和 required_keywords"""
        source = EvalSource(
            book="必修第一册",
            page_start=1,
            page_end=10,
            section_id="必修第一册::1.1",
            required_keywords=["集合"],
        )
        d = source.to_dict()
        assert d["section_id"] == "必修第一册::1.1"
        assert d["required_keywords"] == ["集合"]

    def test_to_dict_without_new_fields(self) -> None:
        """to_dict 不包含空的新字段"""
        source = EvalSource(book="必修第一册", page_start=1, page_end=10)
        d = source.to_dict()
        assert "section_id" not in d
        assert "required_keywords" not in d

    def test_from_dict_with_new_fields(self) -> None:
        """from_dict 解析新字段"""
        data = {
            "book": "必修第一册",
            "page_start": 1,
            "page_end": 10,
            "section_id": "必修第一册::1.1",
            "required_keywords": ["集合", "子集"],
        }
        source = EvalSource.from_dict(data)
        assert source.section_id == "必修第一册::1.1"
        assert source.required_keywords == ["集合", "子集"]

    def test_from_dict_without_new_fields(self) -> None:
        """from_dict 旧格式兼容（无新字段）"""
        data = {"book": "必修第一册", "page_start": 1, "page_end": 10}
        source = EvalSource.from_dict(data)
        assert source.section_id is None
        assert source.required_keywords == []

    def test_roundtrip_with_new_fields(self) -> None:
        """to_dict -> from_dict 往返（含新字段）"""
        original = EvalSource(
            book="必修第一册",
            page_start=1,
            page_end=10,
            section_id="必修第一册::1.1",
            required_keywords=["集合"],
        )
        restored = EvalSource.from_dict(original.to_dict())
        assert restored.book == original.book
        assert restored.page_start == original.page_start
        assert restored.page_end == original.page_end
        assert restored.section_id == original.section_id
        assert restored.required_keywords == original.required_keywords


# ---------------------------------------------------------------------------
# 测试: Section Hit@K
# ---------------------------------------------------------------------------


class TestSectionHit:
    """Section Hit@K 计算测试"""

    def test_all_section_hit(self) -> None:
        """所有条目 section_hit=True → Section Hit@5 = 1.0"""
        details = [
            EvalDetail(
                id="q1", question="Q1", hit=True, first_rank=1,
                mode="ANY", section_hit=True,
            ),
            EvalDetail(
                id="q2", question="Q2", hit=True, first_rank=2,
                mode="ANY", section_hit=True,
            ),
        ]
        assert _calc_section_hit_at_k(details, 5) == pytest.approx(1.0)

    def test_no_section_hit(self) -> None:
        """所有条目 section_hit=False → Section Hit@5 = 0.0"""
        details = [
            EvalDetail(
                id="q1", question="Q1", hit=False, first_rank=0,
                mode="ANY", section_hit=False,
            ),
        ]
        assert _calc_section_hit_at_k(details, 5) == pytest.approx(0.0)

    def test_partial_section_hit(self) -> None:
        """部分 section_hit=True → Section Hit@5 = 0.5"""
        details = [
            EvalDetail(
                id="q1", question="Q1", hit=True, first_rank=1,
                mode="ANY", section_hit=True,
            ),
            EvalDetail(
                id="q2", question="Q2", hit=False, first_rank=0,
                mode="ANY", section_hit=False,
            ),
        ]
        assert _calc_section_hit_at_k(details, 5) == pytest.approx(0.5)

    def test_empty_details(self) -> None:
        """空列表 → Section Hit = 0.0"""
        assert _calc_section_hit_at_k([], 5) == pytest.approx(0.0)

    def test_section_hit_with_section_id_in_eval(self) -> None:
        """section_id 匹配判定：使用 section_id 的 EvalSource"""
        eval_data = [
            {
                "id": "q001",
                "question": "集合的定义",
                "retrieval_truth": {
                    "mode": "ANY",
                    "sources": [{
                        "book": "必修第一册",
                        "page_start": 1,
                        "page_end": 10,
                        "section_id": "必修第一册::1.1",
                    }],
                },
            }
        ]

        # 结果的 section_id 匹配
        query_results = [
            make_eval_query_result(book="必修第一册", page=5),
        ]

        tmp_dir = create_eval_json_file(eval_data)
        try:
            mock_embedding, mock_store = create_mock_embedding_and_store(
                {"集合的定义": query_results}
            )
            loader = EvalSetLoader(eval_dir=tmp_dir)
            runner = EvalRunner(
                embedding_service=mock_embedding,
                vector_store=mock_store,
                eval_loader=loader,
            )
            report = runner.run(eval_filename="test_eval.json")

            # make_query_result 中 section_id = "必修第一册::1.1"
            assert report.details[0].section_hit is True
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_section_hit_mismatch_section_id(self) -> None:
        """section_id 不匹配"""
        eval_data = [
            {
                "id": "q001",
                "question": "集合的定义",
                "retrieval_truth": {
                    "mode": "ANY",
                    "sources": [{
                        "book": "必修第一册",
                        "page_start": 1,
                        "page_end": 10,
                        "section_id": "必修第一册::2.1",
                    }],
                },
            }
        ]

        query_results = [
            make_eval_query_result(book="必修第一册", page=5),
        ]

        tmp_dir = create_eval_json_file(eval_data)
        try:
            mock_embedding, mock_store = create_mock_embedding_and_store(
                {"集合的定义": query_results}
            )
            loader = EvalSetLoader(eval_dir=tmp_dir)
            runner = EvalRunner(
                embedding_service=mock_embedding,
                vector_store=mock_store,
                eval_loader=loader,
            )
            report = runner.run(eval_filename="test_eval.json")

            # section_id 不匹配（期望 "必修第一册::2.1"，实际 "必修第一册::1.1"）
            assert report.details[0].section_hit is False
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_section_hit_fallback_to_page_range(self) -> None:
        """无 section_id 时 fallback 到 page range 匹配"""
        eval_data = [
            {
                "id": "q001",
                "question": "集合的定义",
                "retrieval_truth": {
                    "mode": "ANY",
                    "sources": [{"book": "必修第一册", "page_start": 1, "page_end": 10}],
                },
            }
        ]

        query_results = [
            make_eval_query_result(book="必修第一册", page=5),
        ]

        tmp_dir = create_eval_json_file(eval_data)
        try:
            mock_embedding, mock_store = create_mock_embedding_and_store(
                {"集合的定义": query_results}
            )
            loader = EvalSetLoader(eval_dir=tmp_dir)
            runner = EvalRunner(
                embedding_service=mock_embedding,
                vector_store=mock_store,
                eval_loader=loader,
            )
            report = runner.run(eval_filename="test_eval.json")

            # 无 section_id → fallback 到 page range，page=5 在 1-10 范围内
            assert report.details[0].section_hit is True
            # section_hit 应与 span hit 相同
            assert report.details[0].section_hit == report.details[0].hit
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# 测试: Keyword Coverage@K
# ---------------------------------------------------------------------------


class TestKeywordCoverage:
    """Keyword Coverage@K 计算测试"""

    def test_all_keywords_found(self) -> None:
        """所有关键词都找到 → coverage = 1.0"""
        details = [
            EvalDetail(
                id="q1", question="Q1", hit=True, first_rank=1,
                mode="ANY", keyword_coverage=1.0,
            ),
        ]
        items = [
            make_eval_item(
                "q1",
                sources=[{
                    "book": "必修第一册",
                    "page_start": 1,
                    "page_end": 10,
                    "required_keywords": ["集合", "子集"],
                }],
            ),
        ]
        assert _calc_keyword_coverage_at_k(details, items, 10) == pytest.approx(1.0)

    def test_no_keywords_items_excluded(self) -> None:
        """没有 required_keywords 的条目不参与计算"""
        details = [
            EvalDetail(
                id="q1", question="Q1", hit=True, first_rank=1,
                mode="ANY", keyword_coverage=0.5,
            ),
        ]
        items = [
            make_eval_item("q1", sources=[{"book": "必修第一册", "page_start": 1, "page_end": 10}]),
        ]
        # 没有 required_keywords → 不参与计算 → 返回 0.0
        assert _calc_keyword_coverage_at_k(details, items, 10) == pytest.approx(0.0)

    def test_partial_coverage(self) -> None:
        """部分覆盖"""
        details = [
            EvalDetail(
                id="q1", question="Q1", hit=True, first_rank=1,
                mode="ANY", keyword_coverage=0.5,
            ),
            EvalDetail(
                id="q2", question="Q2", hit=True, first_rank=1,
                mode="ANY", keyword_coverage=1.0,
            ),
        ]
        items = [
            make_eval_item(
                "q1",
                sources=[{
                    "book": "必修第一册",
                    "page_start": 1,
                    "page_end": 10,
                    "required_keywords": ["a"],
                }],
            ),
            make_eval_item(
                "q2",
                sources=[{
                    "book": "必修第一册",
                    "page_start": 1,
                    "page_end": 10,
                    "required_keywords": ["b"],
                }],
            ),
        ]
        assert _calc_keyword_coverage_at_k(details, items, 10) == pytest.approx(0.75)

    def test_empty_details(self) -> None:
        """空列表"""
        assert _calc_keyword_coverage_at_k([], [], 10) == pytest.approx(0.0)

    def test_keyword_coverage_integration(self) -> None:
        """Keyword Coverage 集成测试"""
        eval_data = [
            {
                "id": "q001",
                "question": "集合的概念",
                "retrieval_truth": {
                    "mode": "ANY",
                    "sources": [{
                        "book": "必修第一册",
                        "page_start": 1,
                        "page_end": 10,
                        "required_keywords": ["集合", "元素"],
                    }],
                },
            }
        ]

        # 结果文本包含 "集合" 但不包含 "元素"
        result = make_eval_query_result(book="必修第一册", page=5)
        result.text = "集合是由确定的、互不相同的对象组成的整体"
        query_results = [result]

        tmp_dir = create_eval_json_file(eval_data)
        try:
            mock_embedding, mock_store = create_mock_embedding_and_store(
                {"集合的概念": query_results}
            )
            loader = EvalSetLoader(eval_dir=tmp_dir)
            runner = EvalRunner(
                embedding_service=mock_embedding,
                vector_store=mock_store,
                eval_loader=loader,
            )
            report = runner.run(eval_filename="test_eval.json")

            # "集合" 找到，"元素" 未找到 → 1/2 = 0.5
            assert report.details[0].keyword_coverage == pytest.approx(0.5)
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_keyword_coverage_all_found(self) -> None:
        """所有关键词都找到的集成测试"""
        eval_data = [
            {
                "id": "q001",
                "question": "集合的概念",
                "retrieval_truth": {
                    "mode": "ANY",
                    "sources": [{
                        "book": "必修第一册",
                        "page_start": 1,
                        "page_end": 10,
                        "required_keywords": ["集合", "元素"],
                    }],
                },
            }
        ]

        result = make_eval_query_result(book="必修第一册", page=5)
        result.text = "集合是由确定的元素组成的整体"
        query_results = [result]

        tmp_dir = create_eval_json_file(eval_data)
        try:
            mock_embedding, mock_store = create_mock_embedding_and_store(
                {"集合的概念": query_results}
            )
            loader = EvalSetLoader(eval_dir=tmp_dir)
            runner = EvalRunner(
                embedding_service=mock_embedding,
                vector_store=mock_store,
                eval_loader=loader,
            )
            report = runner.run(eval_filename="test_eval.json")

            assert report.details[0].keyword_coverage == pytest.approx(1.0)
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_keyword_coverage_none_found(self) -> None:
        """关键词都没找到的集成测试"""
        eval_data = [
            {
                "id": "q001",
                "question": "集合的概念",
                "retrieval_truth": {
                    "mode": "ANY",
                    "sources": [{
                        "book": "必修第一册",
                        "page_start": 1,
                        "page_end": 10,
                        "required_keywords": ["导数", "微积分"],
                    }],
                },
            }
        ]

        result = make_eval_query_result(book="必修第一册", page=5)
        result.text = "集合是由确定的元素组成的整体"
        query_results = [result]

        tmp_dir = create_eval_json_file(eval_data)
        try:
            mock_embedding, mock_store = create_mock_embedding_and_store(
                {"集合的概念": query_results}
            )
            loader = EvalSetLoader(eval_dir=tmp_dir)
            runner = EvalRunner(
                embedding_service=mock_embedding,
                vector_store=mock_store,
                eval_loader=loader,
            )
            report = runner.run(eval_filename="test_eval.json")

            assert report.details[0].keyword_coverage == pytest.approx(0.0)
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_no_required_keywords_coverage_is_zero(self) -> None:
        """没有 required_keywords 时 keyword_coverage 为 0"""
        eval_data = [
            {
                "id": "q001",
                "question": "集合的概念",
                "retrieval_truth": {
                    "mode": "ANY",
                    "sources": [{"book": "必修第一册", "page_start": 1, "page_end": 10}],
                },
            }
        ]

        query_results = [make_eval_query_result(book="必修第一册", page=5)]

        tmp_dir = create_eval_json_file(eval_data)
        try:
            mock_embedding, mock_store = create_mock_embedding_and_store(
                {"集合的概念": query_results}
            )
            loader = EvalSetLoader(eval_dir=tmp_dir)
            runner = EvalRunner(
                embedding_service=mock_embedding,
                vector_store=mock_store,
                eval_loader=loader,
            )
            report = runner.run(eval_filename="test_eval.json")

            assert report.details[0].keyword_coverage == pytest.approx(0.0)
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# 测试: Negative Pass Rate
# ---------------------------------------------------------------------------


class TestNegativePassRate:
    """Negative Pass Rate 计算测试"""

    def test_all_negative_pass(self) -> None:
        """所有 NEGATIVE 条目 hit=False → pass rate = 1.0"""
        details = [
            EvalDetail(
                id="q1", question="Q1", hit=False, first_rank=0,
                mode="NEGATIVE",
            ),
            EvalDetail(
                id="q2", question="Q2", hit=False, first_rank=0,
                mode="NEGATIVE",
            ),
            EvalDetail(
                id="q3", question="Q3", hit=True, first_rank=1,
                mode="ANY",
            ),
        ]
        assert _calc_negative_pass_rate(details) == pytest.approx(1.0)

    def test_no_negative_items(self) -> None:
        """没有 NEGATIVE 条目 → pass rate = 0.0"""
        details = [
            EvalDetail(
                id="q1", question="Q1", hit=True, first_rank=1,
                mode="ANY",
            ),
        ]
        assert _calc_negative_pass_rate(details) == pytest.approx(0.0)

    def test_empty_details(self) -> None:
        """空列表 → pass rate = 0.0"""
        assert _calc_negative_pass_rate([]) == pytest.approx(0.0)

    def test_negative_pass_rate_integration(self) -> None:
        """NEGATIVE 模式集成测试"""
        eval_data = [
            {
                "id": "q001",
                "question": "不相关的问题",
                "retrieval_truth": {"mode": "NEGATIVE", "sources": []},
            },
        ]

        tmp_dir = create_eval_json_file(eval_data)
        try:
            mock_embedding, mock_store = create_mock_embedding_and_store({})
            loader = EvalSetLoader(eval_dir=tmp_dir)
            runner = EvalRunner(
                embedding_service=mock_embedding,
                vector_store=mock_store,
                eval_loader=loader,
            )
            report = runner.run(eval_filename="test_eval.json")

            assert report.details[0].mode == "NEGATIVE"
            assert report.details[0].hit is False
            assert report.overall.negative_pass_rate == pytest.approx(1.0)
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# 测试: EvalReport 包含所有新指标
# ---------------------------------------------------------------------------


class TestEvalReportNewMetrics:
    """EvalReport 新指标集成测试"""

    def test_report_to_dict_contains_new_metrics(self) -> None:
        """EvalReport.to_dict() 包含所有新指标"""
        report = EvalReport(
            overall=OverallMetrics(
                hit_rate_at_5=0.7,
                hit_rate_at_10=0.85,
                mrr=0.6,
                total_questions=10,
                section_hit_at_5=0.65,
                section_hit_at_10=0.80,
                keyword_coverage_at_10=0.75,
                negative_pass_rate=1.0,
            ),
            by_book={
                "必修第一册": BookMetrics(
                    hit_rate_at_5=0.8,
                    hit_rate_at_10=0.9,
                    mrr=0.7,
                    count=5,
                    section_hit_at_5=0.7,
                    section_hit_at_10=0.85,
                    keyword_coverage_at_10=0.8,
                ),
            },
            details=[
                EvalDetail(
                    id="q001",
                    question="测试问题",
                    hit=True,
                    first_rank=2,
                    mode="ANY",
                    section_hit=True,
                    keyword_coverage=1.0,
                ),
            ],
        )

        result = report.to_dict()

        # 验证可以 JSON 序列化
        json_str = json.dumps(result, ensure_ascii=False)
        parsed = json.loads(json_str)

        # 验证 overall 包含新指标
        assert "section_hit_at_5" in parsed["overall"]
        assert "section_hit_at_10" in parsed["overall"]
        assert "keyword_coverage_at_10" in parsed["overall"]
        assert "negative_pass_rate" in parsed["overall"]
        assert parsed["overall"]["section_hit_at_5"] == 0.65
        assert parsed["overall"]["negative_pass_rate"] == 1.0

        # 验证 by_book 包含新指标
        book_metrics = parsed["by_book"]["必修第一册"]
        assert "section_hit_at_5" in book_metrics
        assert "section_hit_at_10" in book_metrics
        assert "keyword_coverage_at_10" in book_metrics
        assert book_metrics["section_hit_at_5"] == 0.7

        # 验证 details 包含新字段
        assert "section_hit" in parsed["details"][0]
        assert "keyword_coverage" in parsed["details"][0]
        assert parsed["details"][0]["section_hit"] is True
        assert parsed["details"][0]["keyword_coverage"] == 1.0

    def test_backward_compatible_report(self) -> None:
        """旧格式数据的向后兼容测试"""
        # 使用旧格式（无 section_id/required_keywords）
        eval_data = [
            {
                "id": "q001",
                "question": "什么是集合？",
                "retrieval_truth": {
                    "mode": "ANY",
                    "sources": [{"book": "必修第一册", "page_start": 1, "page_end": 8}],
                },
            }
        ]

        query_results = [
            make_eval_query_result(book="必修第一册", page=3),
        ]

        tmp_dir = create_eval_json_file(eval_data)
        try:
            mock_embedding, mock_store = create_mock_embedding_and_store(
                {"什么是集合？": query_results}
            )
            loader = EvalSetLoader(eval_dir=tmp_dir)
            runner = EvalRunner(
                embedding_service=mock_embedding,
                vector_store=mock_store,
                eval_loader=loader,
            )
            report = runner.run(eval_filename="test_eval.json")

            # Span Hit 正常
            assert report.details[0].hit is True
            assert report.overall.hit_rate_at_5 == pytest.approx(1.0)
            # Section Hit fallback 到 Span Hit
            assert report.details[0].section_hit is True
            # Keyword Coverage 为 0（没有 required_keywords）
            assert report.details[0].keyword_coverage == pytest.approx(0.0)
            # Negative Pass Rate 为 0（没有 NEGATIVE 条目）
            assert report.overall.negative_pass_rate == pytest.approx(0.0)
            # 报告可序列化
            json.dumps(report.to_dict(), ensure_ascii=False)
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_mixed_eval_with_negative_and_keywords(self) -> None:
        """混合模式测试：ANY + NEGATIVE + required_keywords"""
        eval_data = [
            {
                "id": "q001",
                "question": "集合的概念",
                "retrieval_truth": {
                    "mode": "ANY",
                    "sources": [{
                        "book": "必修第一册",
                        "page_start": 1,
                        "page_end": 10,
                        "section_id": "必修第一册::1.1",
                        "required_keywords": ["集合"],
                    }],
                },
            },
            {
                "id": "q002",
                "question": "不相关的问题",
                "retrieval_truth": {"mode": "NEGATIVE", "sources": []},
            },
        ]

        result1 = make_eval_query_result(book="必修第一册", page=3)
        result1.text = "集合是数学的基本概念"
        query_results = [result1]

        tmp_dir = create_eval_json_file(eval_data)
        try:
            mock_embedding, mock_store = create_mock_embedding_and_store(
                {"集合的概念": query_results, "不相关的问题": []}
            )
            loader = EvalSetLoader(eval_dir=tmp_dir)
            runner = EvalRunner(
                embedding_service=mock_embedding,
                vector_store=mock_store,
                eval_loader=loader,
            )
            report = runner.run(eval_filename="test_eval.json")

            assert len(report.details) == 2

            # q001: section_id 匹配 + keyword 找到
            q001 = report.details[0]
            assert q001.hit is True
            assert q001.section_hit is True
            assert q001.keyword_coverage == pytest.approx(1.0)

            # q002: NEGATIVE
            q002 = report.details[1]
            assert q002.hit is False
            assert q002.mode == "NEGATIVE"

            # Overall 指标
            assert report.overall.total_questions == 2
            assert report.overall.hit_rate_at_5 == pytest.approx(1.0)
            assert report.overall.section_hit_at_5 == pytest.approx(1.0)
            assert report.overall.keyword_coverage_at_10 == pytest.approx(1.0)
            assert report.overall.negative_pass_rate == pytest.approx(1.0)
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)
