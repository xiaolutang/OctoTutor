"""ChatService.stream_chat() 异步流式测试

覆盖场景：
1. 正常流程事件序列：status(retrieving) → sources → status(generating) → token×N → done
2. 检索异常 → error event (EMBEDDING_FAILED / VECTOR_STORE_ERROR)
3. Reranker 失败降级 → degraded 正常继续
4. 空检索 → 无 sources event → LLM 兜底 → done
5. LLM 空响应 → error event (LLM_EMPTY_RESPONSE)
6. handle_chat 空检索返回 None（回归验证）
"""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("DASHSCOPE_API_KEY", "test-api-key-for-testing")

from app.rag.models import ChunkMetadata, QueryResult
from app.chat.service import ChatService
from app.chat.schemas import StreamEvent, StatusPayload
from app.chat.errors import ChatErrorCode
from app.domain.models import SourceReference


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def make_query_result(
    chunk_id: str = "test::chunk",
    text: str = "test text",
    score: float = 0.95,
) -> QueryResult:
    return QueryResult(
        chunk_id=chunk_id,
        text=text,
        score=score,
        metadata=ChunkMetadata(
            book="必修第一册",
            chapter="第一章 集合与函数概念",
            section="1.1 集合",
            section_id="必修第一册::1.1",
            page=1,
            page_start=1,
            page_end=1,
            source_pages=[1],
            chunk_type="child",
            block_type="definition",
            has_formula=False,
            parent_id="test::parent",
            child_index=0,
        ),
    )


def make_settings(**overrides):
    """构造 mock Settings 对象"""
    defaults = dict(
        retrieval_top_k=20,
        similarity_threshold=0.70,
        bm25_enabled=True,
        rrf_k=60,
        rerank_top_n=3,
        chat_max_context_tokens=3000,
    )
    defaults.update(overrides)
    return MagicMock(**defaults)


def make_source_ref(chunk_id: str = "ref_1") -> SourceReference:
    return SourceReference(
        chunk_id=chunk_id,
        book="必修第一册",
        section="1.1 集合",
        page_start=1,
        page_end=2,
    )


async def _collect_events(svc, question: str = "什么是集合？", top_k: int = 10):
    """收集 stream_chat yield 的所有事件"""
    events = []
    async for event in svc.stream_chat(question, top_k):
        events.append(event)
    return events


def _build_normal_service(reranked=None, tokens=None):
    """构建全 mock 的 ChatService，正常链路"""
    settings = make_settings()
    r1 = make_query_result("r1", "text r1", 0.9)
    r2 = make_query_result("r2", "text r2", 0.8)

    mock_embedding = MagicMock()
    mock_embedding.embed_query.return_value = [0.1, 0.2]

    mock_vector_store = MagicMock()
    mock_vector_store.query.return_value = [r1, r2]

    mock_bm25 = MagicMock()
    mock_bm25.query.return_value = [r1]

    mock_reranker = MagicMock()
    mock_reranker.rerank.return_value = reranked or [r1, r2]

    mock_generator = MagicMock()
    # generate_stream 是异步生成器
    if tokens is None:
        tokens = ["你", "好", "！"]

    async def _fake_stream(query, chunks):
        for t in tokens:
            yield t

    mock_generator.generate_stream = _fake_stream
    mock_generator.generate.return_value = ("回答", [make_source_ref("r1")])

    svc = ChatService(
        mock_embedding, mock_vector_store, mock_bm25,
        mock_reranker, mock_generator, settings,
    )
    return svc


# ---------------------------------------------------------------------------
# 测试 1: 正常流程事件序列
# ---------------------------------------------------------------------------


class TestNormalFlowEventSequence:
    def test_event_order(self):
        """验证事件顺序：status(retrieving) → sources → status(generating) → token×N → done"""
        svc = _build_normal_service(tokens=["你", "好"])
        events = asyncio.run(_collect_events(svc))

        types = [e.type for e in events]
        assert types[0] == "status"
        assert events[0].data.stage == "retrieving"

        assert types[1] == "sources"
        assert len(events[1].data) == 2  # r1, r2
        assert isinstance(events[1].data[0], SourceReference)

        assert types[2] == "status"
        assert events[2].data.stage == "generating"

        assert types[3] == "token"
        assert events[3].data == "你"
        assert types[4] == "token"
        assert events[4].data == "好"

        assert types[5] == "done"
        assert events[5].data is None

        # 无 error event
        assert "error" not in types


# ---------------------------------------------------------------------------
# 测试 2: 检索异常 → error event
# ---------------------------------------------------------------------------


class TestRetrievalException:
    def test_embedding_error(self):
        """embedding 异常 → EMBEDDING_FAILED error"""
        settings = make_settings()

        mock_embedding = MagicMock()
        mock_embedding.embed_query.side_effect = RuntimeError("dashscope API failed")

        mock_vector_store = MagicMock()
        mock_bm25 = MagicMock()
        mock_reranker = MagicMock()
        mock_generator = MagicMock()

        svc = ChatService(
            mock_embedding, mock_vector_store, mock_bm25,
            mock_reranker, mock_generator, settings,
        )
        events = asyncio.run(_collect_events(svc))

        types = [e.type for e in events]
        # 第一个是 status(retrieving)，第二个是 error
        assert types[0] == "status"
        assert types[1] == "error"
        assert events[1].data["code"] == ChatErrorCode.EMBEDDING_FAILED.value

    def test_vector_store_error(self):
        """向量库异常 → VECTOR_STORE_ERROR error"""
        settings = make_settings()

        mock_embedding = MagicMock()
        mock_embedding.embed_query.return_value = [0.1]

        mock_vector_store = MagicMock()
        mock_vector_store.query.side_effect = RuntimeError("milvus connection lost")

        mock_bm25 = MagicMock()
        mock_reranker = MagicMock()
        mock_generator = MagicMock()

        svc = ChatService(
            mock_embedding, mock_vector_store, mock_bm25,
            mock_reranker, mock_generator, settings,
        )
        events = asyncio.run(_collect_events(svc))

        types = [e.type for e in events]
        assert types[1] == "error"
        assert events[1].data["code"] == ChatErrorCode.VECTOR_STORE_ERROR.value


# ---------------------------------------------------------------------------
# 测试 3: Reranker 失败降级 → degraded 正常继续
# ---------------------------------------------------------------------------


class TestRerankerFailureDegraded:
    def test_reranker_exception_stream_continues(self):
        """reranker 异常 → degraded=True，stream 正常产出 sources + tokens + done"""
        settings = make_settings()
        r1 = make_query_result("r1", "text r1", 0.9)

        mock_embedding = MagicMock()
        mock_embedding.embed_query.return_value = [0.1]

        mock_vector_store = MagicMock()
        mock_vector_store.query.return_value = [r1]

        mock_bm25 = MagicMock()
        mock_bm25.query.return_value = []

        mock_reranker = MagicMock()
        mock_reranker.rerank.side_effect = RuntimeError("rerank API down")

        async def _fake_stream(query, chunks):
            yield "回答"

        mock_generator = MagicMock()
        mock_generator.generate_stream = _fake_stream

        svc = ChatService(
            mock_embedding, mock_vector_store, mock_bm25,
            mock_reranker, mock_generator, settings,
        )
        events = asyncio.run(_collect_events(svc))

        types = [e.type for e in events]
        # 应有 sources event（降级但仍有结果）
        assert "sources" in types
        # 应有 token
        assert "token" in types
        # 应有 done
        assert "done" in types
        # 无 error
        assert "error" not in types


# ---------------------------------------------------------------------------
# 测试 4: 空检索 → 无 sources event → LLM 兜底 → done
# ---------------------------------------------------------------------------


class TestEmptyRetrievalNoSources:
    def test_no_sources_event_on_empty(self):
        """空检索结果 → 无 sources event → LLM 仍被调用（兜底）→ token + done"""
        settings = make_settings(similarity_threshold=0.99)

        # 模拟所有结果被阈值过滤
        r1 = make_query_result("r1", "text", score=0.50)

        mock_embedding = MagicMock()
        mock_embedding.embed_query.return_value = [0.1]

        mock_vector_store = MagicMock()
        mock_vector_store.query.return_value = [r1]  # score 0.50 < threshold 0.99

        mock_bm25 = MagicMock()
        mock_bm25.query.return_value = []

        mock_reranker = MagicMock()
        mock_generator = MagicMock()

        async def _fake_stream(query, chunks):
            # 空 chunks 时 LLM 兜底生成
            assert chunks == []
            yield "这是一个数学问题"

        mock_generator.generate_stream = _fake_stream

        svc = ChatService(
            mock_embedding, mock_vector_store, mock_bm25,
            mock_reranker, mock_generator, settings,
        )
        events = asyncio.run(_collect_events(svc))

        types = [e.type for e in events]
        # 无 sources event（chunks 为空）
        assert "sources" not in types
        # 仍有 status(generating)
        assert "status" in types
        # 仍有 token
        assert "token" in types
        # 有 done
        assert "done" in types


# ---------------------------------------------------------------------------
# 测试 5: LLM 空响应 → error event
# ---------------------------------------------------------------------------


class TestLLMEmptyResponse:
    def test_no_tokens_yields_error(self):
        """generate_stream 不 yield 任何 token → LLM_EMPTY_RESPONSE error"""
        svc = _build_normal_service(tokens=[])
        events = asyncio.run(_collect_events(svc))

        types = [e.type for e in events]
        # 应该有 error
        assert "error" in types
        error_event = [e for e in events if e.type == "error"][0]
        assert error_event.data["code"] == ChatErrorCode.LLM_EMPTY_RESPONSE.value
        # 不应有 done
        assert "done" not in types


# ---------------------------------------------------------------------------
# 测试 6: handle_chat 空检索返回 None（回归验证）
# ---------------------------------------------------------------------------


class TestHandleChatEmptyRetrieval:
    def test_returns_none_on_empty(self):
        """重构后 handle_chat 空检索仍返回 None"""
        settings = make_settings(similarity_threshold=0.70)

        mock_embedding = MagicMock()
        mock_embedding.embed_query.return_value = [0.1]

        mock_vector_store = MagicMock()
        mock_vector_store.query.return_value = [
            make_query_result("low", "text", score=0.30),
        ]

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
