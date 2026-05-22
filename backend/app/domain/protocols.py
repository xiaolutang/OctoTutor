"""domain 层 Protocol 接口定义

业务契约属于领域层，具体实现在 infra/。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from app.domain.models import SourceReference
from app.rag.models import QueryResult


class Reranker(Protocol):
    """检索结果重排序接口

    对初始检索结果进行语义精炼，返回最相关的 top_n 条。
    """

    def rerank(self, query: str, results: list[QueryResult], top_n: int) -> list[QueryResult]: ...


class Generator(Protocol):
    """LLM 回答生成接口

    基于 context chunks 生成助教式回答，返回回答文本和引用来源。
    """

    def generate(self, query: str, context_chunks: list[QueryResult]) -> tuple[str, list[SourceReference]]: ...

    async def generate_stream(self, query: str, context_chunks: list[QueryResult]) -> AsyncIterator[str]: ...
