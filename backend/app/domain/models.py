"""domain 层共享数据模型

跨域共享的数据结构，infra / chat / evaluation 均可依赖。
"""

from __future__ import annotations

from pydantic import BaseModel

from app.rag.models import QueryResult


class SourceReference(BaseModel):
    """引用来源 — 跨域共享（infra + chat + evaluation 都依赖）

    Attributes:
        chunk_id: chunk 唯一标识，格式: {book}::{section_clean}::p{page}_s{section_index}::{type}
        book: 书名
        section: 节名（level=2 标题）
        page_start: 内容覆盖起始页（含）
        page_end: 内容覆盖结束页（含）
    """

    chunk_id: str
    book: str
    section: str
    page_start: int
    page_end: int


def chunks_to_sources(chunks: list[QueryResult]) -> list[SourceReference]:
    """从检索结果构建引用来源列表"""
    return [
        SourceReference(
            chunk_id=c.chunk_id,
            book=c.metadata.book,
            section=c.metadata.section,
            page_start=c.metadata.page_start,
            page_end=c.metadata.page_end,
        )
        for c in chunks
    ]
