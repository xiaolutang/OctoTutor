"""domain 层共享数据模型

跨域共享的数据结构，infra / chat / evaluation 均可依赖。
"""

from __future__ import annotations

from pydantic import BaseModel


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
