"""domain 层共享数据模型"""
from __future__ import annotations
from pydantic import BaseModel

class SourceReference(BaseModel):
    chunk_id: str
    book: str
    section: str
    page_start: int
    page_end: int
