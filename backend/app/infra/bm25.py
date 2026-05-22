"""BM25 稀疏检索器

基于 rank_bm25 + jieba 中文分词的 BM25 检索实现，
用于与向量检索结果进行混合检索（Hybrid Search）。
"""

from __future__ import annotations

import heapq

import jieba
from rank_bm25 import BM25Okapi

from app.rag.models import Chunk, QueryResult


class BM25Retriever:
    """BM25 稀疏检索器

    使用 jieba 分词 + BM25Okapi 算法进行关键词检索，
    支持中文文本的 BM25 分数排序。

    Usage::

        retriever = BM25Retriever()
        retriever.build_index(chunks)          # 启动时调用一次
        results = retriever.query("集合概念")  # 返回 list[QueryResult]
    """

    def __init__(self) -> None:
        self._bm25: BM25Okapi | None = None
        self._chunk_map: dict[str, Chunk] = {}
        self._chunk_ids: list[str] = []

    def build_index(self, chunks: list[Chunk]) -> None:
        """构建 BM25 索引（启动时调用一次）

        Args:
            chunks: 全量 Chunk 列表，通常来自 ChromaDBStore.get_all_chunks()
        """
        self._chunk_map = {c.chunk_id: c for c in chunks}
        self._chunk_ids = [c.chunk_id for c in chunks]
        tokenized = [list(jieba.cut(c.text)) for c in chunks]
        self._bm25 = BM25Okapi(tokenized)

    def query(self, query: str, top_k: int = 10) -> list[QueryResult]:
        """查询 BM25，返回 list[QueryResult] 按 BM25 分数降序

        Args:
            query: 查询文本
            top_k: 返回前 top_k 个结果

        Returns:
            按 BM25 分数降序排列的 QueryResult 列表
        """
        if self._bm25 is None:
            return []

        tokenized_query = list(jieba.cut(query))
        scores = self._bm25.get_scores(tokenized_query)
        ranked = heapq.nlargest(top_k, enumerate(scores), key=lambda x: x[1])

        results: list[QueryResult] = []
        for i, score in ranked:
            if i < len(self._chunk_ids):
                chunk_id = self._chunk_ids[i]
                chunk = self._chunk_map[chunk_id]
                results.append(
                    QueryResult(
                        chunk_id=chunk_id,
                        text=chunk.text,
                        metadata=chunk.metadata,
                        score=float(score),
                    )
                )
        return results
