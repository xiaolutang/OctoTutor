import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass

from app.rag.models import QueryResult
from app.domain.protocols import Reranker, Generator
from app.chat.schemas import ChatResponse, StreamEvent, StatusPayload
from app.chat.errors import ChatErrorCode, make_error
from app.domain.models import SourceReference
from app.chat.question_classifier import classify_question


@dataclass
class RetrieveResult:
    """_retrieve() 返回类型：携带检索结果 + 降级状态"""
    chunks: list[QueryResult]
    degraded: bool = False
    degradation_reason: str | None = None


class ChatService:
    def __init__(self, embedding, vector_store, bm25, reranker: Reranker, generator: Generator, settings):
        self._embedding = embedding
        self._vector_store = vector_store
        self._bm25 = bm25
        self._reranker = reranker
        self._generator = generator
        self._settings = settings

    # ------------------------------------------------------------------
    # 同步对话入口（已有）
    # ------------------------------------------------------------------

    def handle_chat(self, question: str, top_k: int) -> ChatResponse | None:
        # 意图分类：问候/闲聊等走 direct，不检索教材
        if classify_question(question) == "direct":
            answer, _ = self._generator.generate(question, [])
            return ChatResponse(
                answer=answer,
                sources=[],
                context_used=0,
                degraded=False,
                degradation_reason=None,
            )

        result = self._retrieve(question, top_k)
        if not result.chunks:
            return None
        answer, sources = self._generator.generate(question, result.chunks)
        return ChatResponse(
            answer=answer,
            sources=sources,
            context_used=len(result.chunks),
            degraded=result.degraded,
            degradation_reason=result.degradation_reason,
        )

    # ------------------------------------------------------------------
    # 异步流式对话入口
    # ------------------------------------------------------------------

    async def stream_chat(
        self, question: str, top_k: int
    ) -> AsyncIterator[StreamEvent]:
        """异步流式对话：意图分类 → 检索(可选) → 生成，逐事件 yield StreamEvent"""
        # -- 意图分类 --
        intent = classify_question(question)

        # -- 阶段 1：检索（仅 retrieval 意图） --
        context_chunks: list[QueryResult] = []

        if intent == "retrieval":
            yield StreamEvent(
                type="status",
                data=StatusPayload(stage="retrieving", message="正在检索教材..."),
            )

            try:
                result = await asyncio.to_thread(self._retrieve, question, top_k)
            except Exception as e:
                err_str = str(e).lower()
                if "embedding" in err_str or "dashscope" in err_str:
                    yield StreamEvent(type="error", data=make_error(ChatErrorCode.EMBEDDING_FAILED))
                else:
                    yield StreamEvent(type="error", data=make_error(ChatErrorCode.VECTOR_STORE_ERROR))
                return

            context_chunks = result.chunks

            # -- 检索结果处理 --
            if context_chunks:
                sources = [
                    SourceReference(
                        chunk_id=chunk.chunk_id,
                        book=chunk.metadata.book,
                        section=chunk.metadata.section,
                        page_start=chunk.metadata.page_start,
                        page_end=chunk.metadata.page_end,
                    )
                    for chunk in context_chunks
                ]
                yield StreamEvent(type="sources", data=sources)

        # -- 阶段 2：生成 --
        yield StreamEvent(
            type="status",
            data=StatusPayload(stage="generating", message="正在生成回答..."),
        )

        try:
            has_token = False
            async for token in self._generator.generate_stream(question, context_chunks):
                has_token = True
                yield StreamEvent(type="token", data=token)

            if not has_token:
                yield StreamEvent(type="error", data=make_error(ChatErrorCode.LLM_EMPTY_RESPONSE))
                return

            yield StreamEvent(type="done", data=None)

        except ConnectionError:
            yield StreamEvent(type="error", data=make_error(ChatErrorCode.LLM_CONNECT_FAILED))
        except TimeoutError:
            yield StreamEvent(type="error", data=make_error(ChatErrorCode.LLM_TIMEOUT))
        except Exception:
            yield StreamEvent(type="error", data=make_error(ChatErrorCode.LLM_STREAM_ERROR))

    # ------------------------------------------------------------------
    # 私有方法
    # ------------------------------------------------------------------

    def _retrieve(self, question: str, top_k: int) -> RetrieveResult:
        """检索管线：Embed -> Vector -> Threshold -> BM25 -> RRF -> Rerank -> Truncate"""
        embedding = self._embedding.embed_query(question)
        vector_results = self._vector_store.query(embedding, self._settings.retrieval_top_k)

        # 相似度阈值过滤（在 RRF 融合前）
        vector_results = [
            r for r in vector_results if r.score >= self._settings.similarity_threshold
        ]

        # BM25 检索
        if self._settings.bm25_enabled:
            bm25_results = self._bm25.query(question, self._settings.retrieval_top_k)
            fused = self._rrf_fuse(vector_results, bm25_results, self._settings.rrf_k)
        else:
            fused = vector_results

        if not fused:
            return RetrieveResult(chunks=[])

        # Rerank 精炼（失败降级）
        try:
            reranked = self._reranker.rerank(question, fused, self._settings.rerank_top_n)
            if not reranked:
                reranked = fused[: self._settings.rerank_top_n]
                return RetrieveResult(
                    chunks=self._truncate_by_chars(reranked, self._settings.chat_max_context_tokens),
                    degraded=True,
                    degradation_reason="rerank_empty",
                )
        except Exception:
            reranked = fused[: self._settings.rerank_top_n]
            return RetrieveResult(
                chunks=self._truncate_by_chars(reranked, self._settings.chat_max_context_tokens),
                degraded=True,
                degradation_reason="rerank_failed",
            )

        context_chunks = self._truncate_by_chars(reranked, self._settings.chat_max_context_tokens)
        return RetrieveResult(chunks=context_chunks)

    @staticmethod
    def _rrf_fuse(vector_results, bm25_results, k=60):
        scores = {}
        chunk_map = {}
        for rank, r in enumerate(vector_results, 1):
            scores[r.chunk_id] = scores.get(r.chunk_id, 0) + 1.0 / (k + rank)
            chunk_map[r.chunk_id] = r
        for rank, r in enumerate(bm25_results, 1):
            scores[r.chunk_id] = scores.get(r.chunk_id, 0) + 1.0 / (k + rank)
            if r.chunk_id not in chunk_map:
                chunk_map[r.chunk_id] = r
        sorted_ids = sorted(scores, key=scores.get, reverse=True)
        return [chunk_map[cid] for cid in sorted_ids if cid in chunk_map]

    def _truncate_by_chars(self, chunks, max_chars):
        if not chunks:
            return []
        if max_chars <= 0:
            return [chunks[0]]
        total = 0
        result = []
        for chunk in chunks:
            if not chunk.text:
                continue
            est = len(chunk.text)
            if total + est > max_chars:
                break
            result.append(chunk)
            total += est
        if not result:
            result = [chunks[0]]
        return result
