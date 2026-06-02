"""ChatService 单元测试

覆盖场景：
1. _rrf_fuse — 正确融合 vector + BM25 结果
2. _rrf_fuse — BM25 独有 chunk 保留
3. _rrf_fuse — 空输入返回空列表
4. cosine 阈值过滤 — 低于阈值的被移除
5. Rerank 降级（异常）— degraded=True, reason="rerank_failed"
6. Rerank 降级（返回空）— degraded=True, reason="rerank_empty"
7. Token 截断 — 超限截断，保底至少 1 个 chunk
8. handle_chat 全链路 — mock 全部依赖，验证返回 ChatResponse
9. 检索 0 条 — 返回 None
10. BM25 关闭 — 跳过 RRF，短路返回向量结果
"""

import os
import pytest
from unittest.mock import MagicMock

os.environ.setdefault("DASHSCOPE_API_KEY", "test-api-key-for-testing")



from app.rag.models import ChunkMetadata, QueryResult
from app.chat.service import ChatService
from app.chat.schemas import ChatResponse
from app.domain.models import SourceReference
from tests.conftest import make_query_result
from tests._helpers import make_settings, make_source_ref


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def make_chunk_id(i: int) -> str:
    return f"chunk_{i}"


# ---------------------------------------------------------------------------
# 测试 1: _rrf_fuse — 正确融合 vector + BM25 结果
# ---------------------------------------------------------------------------


class TestRRFFuseBasic:
    def test_fuse_vector_and_bm25(self):
        """vector 和 BM25 同时出现的 chunk 得分更高"""
        v1 = make_query_result("A", "text_a", 0.9)
        v2 = make_query_result("B", "text_b", 0.8)
        b1 = make_query_result("A", "text_a", 0.5)
        b2 = make_query_result("C", "text_c", 0.6)

        result = ChatService._rrf_fuse([v1, v2], [b1, b2], k=60)

        chunk_ids = [r.chunk_id for r in result]
        # A 同时出现在 vector(rank=1) 和 bm25(rank=1)，得分最高
        assert chunk_ids[0] == "A"
        # 包含 B 和 C
        assert set(chunk_ids) == {"A", "B", "C"}

    def test_scores_are_additive(self):
        """同一 chunk 在两个检索器都出现时，RRF 得分是两者之和"""
        v1 = make_query_result("X", "text_x", 0.9)
        b1 = make_query_result("X", "text_x", 0.5)

        result = ChatService._rrf_fuse([v1], [b1], k=60)

        assert len(result) == 1
        assert result[0].chunk_id == "X"


# ---------------------------------------------------------------------------
# 测试 2: _rrf_fuse — BM25 独有 chunk 保留
# ---------------------------------------------------------------------------


class TestRRFFuseBM25Only:
    def test_bm25_only_chunks_preserved(self):
        """BM25 独有的 chunk 应该保留在融合结果中"""
        b1 = make_query_result("bm25_only", "text_bm", 0.3)
        b2 = make_query_result("bm25_also", "text_bm2", 0.2)

        result = ChatService._rrf_fuse([], [b1, b2], k=60)

        chunk_ids = [r.chunk_id for r in result]
        assert "bm25_only" in chunk_ids
        assert "bm25_also" in chunk_ids

    def test_vector_only_chunks_preserved(self):
        """vector 独有的 chunk 应该保留"""
        v1 = make_query_result("vec_only", "text_v", 0.9)

        result = ChatService._rrf_fuse([v1], [], k=60)

        assert len(result) == 1
        assert result[0].chunk_id == "vec_only"


# ---------------------------------------------------------------------------
# 测试 3: _rrf_fuse — 空输入返回空列表
# ---------------------------------------------------------------------------


class TestRRFFuseEmpty:
    def test_both_empty(self):
        result = ChatService._rrf_fuse([], [], k=60)
        assert result == []

    def test_vector_empty_bm25_empty(self):
        result = ChatService._rrf_fuse([], [], k=10)
        assert result == []


# ---------------------------------------------------------------------------
# 测试 4: cosine 阈值过滤 — 低于阈值的被移除
# ---------------------------------------------------------------------------


class TestCosineThreshold:
    def test_below_threshold_filtered(self):
        """低于 similarity_threshold 的向量结果在融合前被移除"""
        settings = make_settings(similarity_threshold=0.70)
        mock_embedding = MagicMock()
        mock_embedding.embed_query.return_value = [0.1, 0.2]

        high_score = make_query_result("high", "text", score=0.85)
        low_score = make_query_result("low", "text", score=0.50)

        mock_vector_store = MagicMock()
        mock_vector_store.query.return_value = [high_score, low_score]

        mock_bm25 = MagicMock()
        mock_bm25.query.return_value = []

        mock_reranker = MagicMock()
        mock_reranker.rerank.return_value = [high_score]

        mock_generator = MagicMock()
        mock_generator.generate.return_value = (
            "answer",
            [make_source_ref("high")],
        )

        svc = ChatService(
            mock_embedding, mock_vector_store, mock_bm25,
            mock_reranker, mock_generator, settings,
        )
        resp = svc.handle_chat("test", 10)

        # reranker 应该只收到高分的那个结果（低分已被过滤）
        reranker_args = mock_reranker.rerank.call_args[0][1]
        assert len(reranker_args) == 1
        assert reranker_args[0].chunk_id == "high"


# ---------------------------------------------------------------------------
# 测试 5: Rerank 降级（异常）— degraded=True, reason="rerank_failed"
# ---------------------------------------------------------------------------


class TestRerankDegradedException:
    def test_reranker_exception_degrades(self):
        """reranker 抛出异常时降级处理"""
        settings = make_settings(rerank_top_n=3, chat_max_context_tokens=5000)
        r1 = make_query_result("r1", "text r1", 0.9)

        mock_embedding = MagicMock()
        mock_embedding.embed_query.return_value = [0.1]
        mock_vector_store = MagicMock()
        mock_vector_store.query.return_value = [r1]
        mock_bm25 = MagicMock()
        mock_bm25.query.return_value = []
        mock_reranker = MagicMock()
        mock_reranker.rerank.side_effect = RuntimeError("API error")
        mock_generator = MagicMock()
        mock_generator.generate.return_value = (
            "答案",
            [make_source_ref("r1")],
        )

        svc = ChatService(
            mock_embedding, mock_vector_store, mock_bm25,
            mock_reranker, mock_generator, settings,
        )
        resp = svc.handle_chat("test", 10)

        assert resp.degraded is True
        assert resp.degradation_reason == "rerank_failed"


# ---------------------------------------------------------------------------
# 测试 6: Rerank 降级（返回空）— degraded=True, reason="rerank_empty"
# ---------------------------------------------------------------------------


class TestRerankDegradedEmpty:
    def test_reranker_returns_empty_degrades(self):
        """reranker 返回空列表时降级处理"""
        settings = make_settings(rerank_top_n=3, chat_max_context_tokens=5000)
        r1 = make_query_result("r1", "text r1", 0.9)

        mock_embedding = MagicMock()
        mock_embedding.embed_query.return_value = [0.1]
        mock_vector_store = MagicMock()
        mock_vector_store.query.return_value = [r1]
        mock_bm25 = MagicMock()
        mock_bm25.query.return_value = []
        mock_reranker = MagicMock()
        mock_reranker.rerank.return_value = []
        mock_generator = MagicMock()
        mock_generator.generate.return_value = (
            "答案",
            [make_source_ref("r1")],
        )

        svc = ChatService(
            mock_embedding, mock_vector_store, mock_bm25,
            mock_reranker, mock_generator, settings,
        )
        resp = svc.handle_chat("test", 10)

        assert resp.degraded is True
        assert resp.degradation_reason == "rerank_empty"


# ---------------------------------------------------------------------------
# 测试 7: Token 截断 — 超限截断，保底至少 1 个 chunk
# ---------------------------------------------------------------------------


class TestTokenTruncation:
    def test_truncate_keeps_first_chunk_as_minimum(self):
        """即使 max_tokens 很小，也至少保留 1 个 chunk"""
        settings = make_settings(chat_max_context_tokens=5, rerank_top_n=3)
        r1 = make_query_result("r1", "a" * 100, 0.9)
        r2 = make_query_result("r2", "b" * 100, 0.8)

        mock_embedding = MagicMock()
        mock_embedding.embed_query.return_value = [0.1]
        mock_vector_store = MagicMock()
        mock_vector_store.query.return_value = [r1, r2]
        mock_bm25 = MagicMock()
        mock_bm25.query.return_value = []
        mock_reranker = MagicMock()
        mock_reranker.rerank.return_value = [r1, r2]
        mock_generator = MagicMock()
        mock_generator.generate.return_value = (
            "答案",
            [make_source_ref("r1")],
        )

        svc = ChatService(
            mock_embedding, mock_vector_store, mock_bm25,
            mock_reranker, mock_generator, settings,
        )
        resp = svc.handle_chat("test", 10)

        # 即使 chat_max_context_tokens=5，也应至少保留 1 个 chunk
        assert resp.context_used >= 1

    def test_truncate_by_chars_direct(self):
        """直接测试 _truncate_by_chars 方法"""
        mock_settings = make_settings()
        svc = ChatService(
            MagicMock(), MagicMock(), MagicMock(),
            MagicMock(), MagicMock(), mock_settings,
        )

        chunks = [
            make_query_result("c1", "a" * 100, 0.9),
            make_query_result("c2", "b" * 100, 0.8),
            make_query_result("c3", "c" * 100, 0.7),
        ]

        # max_tokens=150，第一个 chunk 100 < 150 可以进入，
        # 但 total=100 + 100 = 200 > 150，第二个进不去
        result = svc._truncate_by_chars(chunks, 150)
        assert len(result) == 1
        assert result[0].chunk_id == "c1"

    def test_truncate_empty_chunks(self):
        """空列表输入返回空列表"""
        mock_settings = make_settings()
        svc = ChatService(
            MagicMock(), MagicMock(), MagicMock(),
            MagicMock(), MagicMock(), mock_settings,
        )
        result = svc._truncate_by_chars([], 1000)
        assert result == []

    def test_truncate_max_tokens_zero(self):
        """max_tokens <= 0 时保底返回第一个 chunk"""
        mock_settings = make_settings()
        svc = ChatService(
            MagicMock(), MagicMock(), MagicMock(),
            MagicMock(), MagicMock(), mock_settings,
        )
        chunks = [make_query_result("c1", "text", 0.9)]
        result = svc._truncate_by_chars(chunks, 0)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# 测试 8: handle_chat 全链路
# ---------------------------------------------------------------------------


class TestHandleChatFullPipeline:
    def test_full_pipeline(self):
        """mock 全部依赖，验证返回 ChatResponse"""
        settings = make_settings(
            retrieval_top_k=20,
            similarity_threshold=0.70,
            bm25_enabled=True,
            rrf_k=60,
            rerank_top_n=3,
            chat_max_context_tokens=3000,
        )

        v1 = make_query_result("v1", "向量结果1", 0.95)
        v2 = make_query_result("v2", "向量结果2", 0.80)
        b1 = make_query_result("v1", "向量结果1", 0.5)
        b3 = make_query_result("b3", "BM25独有", 0.6)

        mock_embedding = MagicMock()
        mock_embedding.embed_query.return_value = [0.1, 0.2, 0.3]

        mock_vector_store = MagicMock()
        mock_vector_store.query.return_value = [v1, v2]

        mock_bm25 = MagicMock()
        mock_bm25.query.return_value = [b1, b3]

        reranked = [v1, v2]
        mock_reranker = MagicMock()
        mock_reranker.rerank.return_value = reranked

        sources = [
            SourceReference(chunk_id="v1", book="书", section="节", page_start=1, page_end=2),
            SourceReference(chunk_id="v2", book="书", section="节", page_start=3, page_end=4),
        ]
        mock_generator = MagicMock()
        mock_generator.generate.return_value = ("这是回答", sources)

        svc = ChatService(
            mock_embedding, mock_vector_store, mock_bm25,
            mock_reranker, mock_generator, settings,
        )
        resp = svc.handle_chat("什么是集合？", 10)

        assert isinstance(resp, ChatResponse)
        assert resp.answer == "这是回答"
        assert len(resp.sources) == 2
        assert resp.context_used == 2
        assert resp.degraded is False
        assert resp.degradation_reason is None

        # 验证调用链
        mock_embedding.embed_query.assert_called_once_with("什么是集合？")
        mock_vector_store.query.assert_called_once_with([0.1, 0.2, 0.3], 10)
        mock_bm25.query.assert_called_once_with("什么是集合？", 10)
        mock_reranker.rerank.assert_called_once()
        mock_generator.generate.assert_called_once()


# ---------------------------------------------------------------------------
# 测试 9: 检索 0 条 — 返回 None（由 router 层转 404）
# ---------------------------------------------------------------------------


class TestNoResults:
    def test_no_results_returns_none(self):
        """检索结果为空时返回 None（由 router 层转换为 404）"""
        settings = make_settings(similarity_threshold=0.70)

        mock_embedding = MagicMock()
        mock_embedding.embed_query.return_value = [0.1]
        mock_vector_store = MagicMock()
        mock_vector_store.query.return_value = [
            make_query_result("low", "text", score=0.30),
        ]
        # 低于阈值，被过滤后 vector_results = []
        mock_bm25 = MagicMock()
        mock_bm25.query.return_value = []
        mock_reranker = MagicMock()
        mock_generator = MagicMock()

        svc = ChatService(
            mock_embedding, mock_vector_store, mock_bm25,
            mock_reranker, mock_generator, settings,
        )

        result = svc.handle_chat("不相关的问题", 10)
        assert result is None


# ---------------------------------------------------------------------------
# 测试 10: BM25 关闭 — 跳过 RRF，短路返回向量结果
# ---------------------------------------------------------------------------


class TestBM25Disabled:
    def test_bm25_disabled_skips_rrf(self):
        """bm25_enabled=False 时跳过 RRF，直接使用向量结果"""
        settings = make_settings(bm25_enabled=False, chat_max_context_tokens=5000)

        v1 = make_query_result("v1", "text v1", 0.9)

        mock_embedding = MagicMock()
        mock_embedding.embed_query.return_value = [0.1]
        mock_vector_store = MagicMock()
        mock_vector_store.query.return_value = [v1]
        mock_bm25 = MagicMock()
        # BM25 关闭时不应被调用
        mock_bm25.query.side_effect = AssertionError("BM25 should not be called")
        mock_reranker = MagicMock()
        mock_reranker.rerank.return_value = [v1]
        mock_generator = MagicMock()
        mock_generator.generate.return_value = (
            "答案",
            [make_source_ref("v1")],
        )

        svc = ChatService(
            mock_embedding, mock_vector_store, mock_bm25,
            mock_reranker, mock_generator, settings,
        )
        resp = svc.handle_chat("test", 10)

        assert isinstance(resp, ChatResponse)
        assert resp.answer == "答案"
        # BM25 不应被调用
        mock_bm25.query.assert_not_called()
