"""DashScopeReranker 单元测试"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.infra.reranker import DashScopeReranker
from app.rag.models import ChunkMetadata, QueryResult
from tests.conftest import make_query_result


# ---------- 辅助函数 ----------


def _make_metadata(**overrides) -> ChunkMetadata:
    """创建 ChunkMetadata，提供合理默认值"""
    defaults = dict(
        book="测试书",
        chapter="第一章",
        section="第一节",
        section_id="测试书::1.1",
        page=1,
        page_start=1,
        page_end=2,
        source_pages=[1, 2],
        chunk_type="parent",
        block_type="unknown",
        has_formula=False,
        parent_id="",
        child_index=0,
    )
    defaults.update(overrides)
    return ChunkMetadata(**defaults)


def _mock_response(status_code: int = 200, results: list | None = None) -> MagicMock:
    """构造 DashScope TextReRank mock response"""
    resp = MagicMock()
    resp.status_code = status_code
    if status_code == 200:
        resp.output.results = results or []
    else:
        resp.code = "InternalError"
        resp.message = "something went wrong"
    return resp


# ---------- 测试 ----------


class TestDashScopeReranker:
    """DashScopeReranker 单元测试"""

    @patch("app.infra.reranker.TextReRank")
    @patch("app.infra.reranker.dashscope")
    def test_normal_rerank(self, mock_dashscope: MagicMock, mock_text_rerank: MagicMock) -> None:
        """正常 rerank：返回排序后子集，score 为 relevance_score"""
        # 准备输入
        results = [
            make_query_result("c1", "集合的概念", score=0.3),
            make_query_result("c2", "函数的定义", score=0.7),
            make_query_result("c3", "三角函数", score=0.5),
        ]

        # mock API 返回：按相关性排序后返回 top 2
        mock_text_rerank.call.return_value = _mock_response(
            status_code=200,
            results=[
                {"index": 2, "relevance_score": 0.95, "document": {"text": "三角函数"}},
                {"index": 0, "relevance_score": 0.80, "document": {"text": "集合的概念"}},
            ],
        )

        reranker = DashScopeReranker(api_key="test-key")
        reranked = reranker.rerank(query="三角", results=results, top_n=2)

        assert len(reranked) == 2
        # 排序后第一条是 c3（index=2）
        assert reranked[0].chunk_id == "c3"
        assert reranked[0].score == 0.95
        # 第二条是 c1（index=0）
        assert reranked[1].chunk_id == "c1"
        assert reranked[1].score == 0.80

    def test_empty_results_input(self) -> None:
        """空结果输入：返回空列表"""
        reranker = DashScopeReranker(api_key="test-key")
        reranked = reranker.rerank(query="任意查询", results=[], top_n=3)
        assert reranked == []

    @patch("app.infra.reranker.TextReRank")
    @patch("app.infra.reranker.dashscope")
    def test_api_error_raises_runtime_error(
        self, mock_dashscope: MagicMock, mock_text_rerank: MagicMock
    ) -> None:
        """API 错误：抛出 RuntimeError"""
        results = [make_query_result("c1", "文本")]
        mock_text_rerank.call.return_value = _mock_response(
            status_code=500,
        )

        reranker = DashScopeReranker(api_key="test-key")
        with pytest.raises(RuntimeError, match="DashScope Reranker API error"):
            reranker.rerank(query="查询", results=results, top_n=3)

    @patch("app.infra.reranker.TextReRank")
    @patch("app.infra.reranker.dashscope")
    def test_index_mapping_preserves_metadata(
        self, mock_dashscope: MagicMock, mock_text_rerank: MagicMock
    ) -> None:
        """返回结果的 index 映射正确：保持原始 QueryResult 的 chunk_id/metadata"""
        meta1 = _make_metadata(book="书A", chapter="第一章")
        meta2 = _make_metadata(book="书B", chapter="第二章")
        results = [
            QueryResult(chunk_id="id_alpha", text="文本一", metadata=meta1, score=0.3),
            QueryResult(chunk_id="id_beta", text="文本二", metadata=meta2, score=0.6),
        ]

        mock_text_rerank.call.return_value = _mock_response(
            status_code=200,
            results=[
                {"index": 1, "relevance_score": 0.99, "document": {"text": "文本二"}},
                {"index": 0, "relevance_score": 0.50, "document": {"text": "文本一"}},
            ],
        )

        reranker = DashScopeReranker(api_key="test-key")
        reranked = reranker.rerank(query="查询", results=results, top_n=2)

        assert len(reranked) == 2
        # index=1 → id_beta, 书B
        assert reranked[0].chunk_id == "id_beta"
        assert reranked[0].metadata.book == "书B"
        assert reranked[0].metadata.chapter == "第二章"
        assert reranked[0].score == 0.99
        # index=0 → id_alpha, 书A
        assert reranked[1].chunk_id == "id_alpha"
        assert reranked[1].metadata.book == "书A"
        assert reranked[1].score == 0.50

    @patch("app.infra.reranker.TextReRank")
    @patch("app.infra.reranker.dashscope")
    def test_api_called_with_correct_params(
        self, mock_dashscope: MagicMock, mock_text_rerank: MagicMock
    ) -> None:
        """验证 TextReRank.call 参数正确"""
        results = [
            make_query_result("c1", "文本一"),
            make_query_result("c2", "文本二"),
        ]
        mock_text_rerank.call.return_value = _mock_response(
            status_code=200, results=[]
        )

        reranker = DashScopeReranker(api_key="test-key", model="gte-rerank-v2")
        reranker.rerank(query="测试查询", results=results, top_n=5)

        mock_text_rerank.call.assert_called_once_with(
            model="gte-rerank-v2",
            query="测试查询",
            documents=["文本一", "文本二"],
            return_documents=True,
            top_n=5,
        )

    @patch("app.infra.reranker.TextReRank")
    @patch("app.infra.reranker.dashscope")
    def test_empty_api_results(
        self, mock_dashscope: MagicMock, mock_text_rerank: MagicMock
    ) -> None:
        """API 返回空结果列表时返回空列表"""
        results = [make_query_result("c1", "文本")]
        mock_text_rerank.call.return_value = _mock_response(
            status_code=200, results=[]
        )

        reranker = DashScopeReranker(api_key="test-key")
        reranked = reranker.rerank(query="查询", results=results, top_n=3)
        assert reranked == []

    @patch("app.infra.reranker.TextReRank")
    @patch("app.infra.reranker.dashscope")
    def test_out_of_range_index_skipped(
        self, mock_dashscope: MagicMock, mock_text_rerank: MagicMock
    ) -> None:
        """越界 index 被安全跳过"""
        results = [make_query_result("c1", "文本一")]
        mock_text_rerank.call.return_value = _mock_response(
            status_code=200,
            results=[
                {"index": 0, "relevance_score": 0.9, "document": {"text": "文本一"}},
                {"index": 5, "relevance_score": 0.8, "document": {"text": "不存在"}},
            ],
        )

        reranker = DashScopeReranker(api_key="test-key")
        reranked = reranker.rerank(query="查询", results=results, top_n=3)

        assert len(reranked) == 1
        assert reranked[0].chunk_id == "c1"
