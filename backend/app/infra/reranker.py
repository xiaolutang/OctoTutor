"""DashScope Reranker 实现

基于阿里云 DashScope TextReRank API 的检索结果重排序，
使用 gte-rerank 模型对初始检索结果进行语义精炼。

职责边界：reranker 只负责调用 API 并返回结果
- API 调用失败 → 抛出异常（由 ChatService 捕获并降级）
- API 返回空 → 返回空列表（由 ChatService 处理降级）
降级决策权统一在 ChatService，infra 层不做降级兜底
"""

from __future__ import annotations

import dashscope
from dashscope import TextReRank

from app.rag.models import QueryResult


class DashScopeReranker:
    """DashScope gte-rerank 实现

    Usage::

        reranker = DashScopeReranker(api_key="sk-xxx", model="gte-rerank")
        reranked = reranker.rerank(query="数学问题", results=query_results, top_n=3)
    """

    def __init__(self, api_key: str, model: str = "gte-rerank") -> None:
        dashscope.api_key = api_key
        self._model = model

    def rerank(
        self, query: str, results: list[QueryResult], top_n: int
    ) -> list[QueryResult]:
        """对检索结果进行重排序

        Args:
            query: 用户查询文本
            results: 初始检索结果列表
            top_n: 返回前 top_n 个最相关结果

        Returns:
            按 relevance_score 降序排列的 QueryResult 列表

        Raises:
            RuntimeError: DashScope API 调用失败时抛出
        """
        if not results:
            return []

        documents = [r.text for r in results]
        resp = TextReRank.call(
            model=self._model,
            query=query,
            documents=documents,
            return_documents=True,
            top_n=top_n,
        )

        if resp.status_code != 200:
            raise RuntimeError(
                f"DashScope Reranker API error: {resp.code} - {resp.message}"
            )

        reranked: list[QueryResult] = []
        for item in resp.output.results:
            idx = item["index"]
            if 0 <= idx < len(results):
                original = results[idx]
                reranked.append(
                    QueryResult(
                        chunk_id=original.chunk_id,
                        text=original.text,
                        metadata=original.metadata,
                        score=float(item["relevance_score"]),
                    )
                )

        return reranked
