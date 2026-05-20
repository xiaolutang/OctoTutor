"""RAG 数据模型定义

包含章节识别和分块所需的核心数据结构。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SectionBoundary:
    """章节边界

    表示 Markdown 文本中识别到的一个章节标题及其覆盖范围。

    Attributes:
        title: 章节标题文本（如 "1.1 集合"）
        level: 层级: 1=章, 2=节, 3=习题/补充, 4=子节
        start_pos: 在文本中的起始字符位置（含标题行）
        end_pos: 在文本中的结束字符位置（不含，到下一个 section 起始或文本末尾）
        page: 所在页码
        section_index: 该页内第几个章节（0-based）
    """

    title: str
    level: int
    start_pos: int
    end_pos: int
    page: int
    section_index: int


@dataclass
class ChunkMetadata:
    """分块元数据

    每条 Chunk 携带的完整元信息，用于 ChromaDB 存储、过滤和展示。

    Attributes:
        book: 书名
        chapter: 章名（level=1 标题）
        section: 节名（level=2 标题）
        page: 页码
        chunk_type: "parent" | "child"
        has_formula: 是否含 LaTeX 公式
        parent_id: parent chunk 的 ID
        child_index: child 在 parent 内的序号（0-based，parent 类型为 0）
    """

    book: str
    chapter: str
    section: str
    page: int
    chunk_type: str  # "parent" | "child"
    has_formula: bool
    parent_id: str
    child_index: int

    def to_dict(self) -> dict:
        """转换为 ChromaDB metadata 字典"""
        return {
            "book": self.book,
            "chapter": self.chapter,
            "section": self.section,
            "page": self.page,
            "chunk_type": self.chunk_type,
            "has_formula": self.has_formula,
            "parent_id": self.parent_id,
            "child_index": self.child_index,
        }


@dataclass
class Chunk:
    """分块结果

    Attributes:
        chunk_id: 唯一标识，格式: {book}::{section_clean}::p{page}_s{section_index}::{type}
        text: 分块文本内容
        metadata: 元数据
    """

    chunk_id: str
    text: str
    metadata: ChunkMetadata


@dataclass
class QueryResult:
    """向量查询结果

    Attributes:
        chunk_id: chunk 唯一标识
        text: 分块文本内容
        metadata: 元数据
        score: 相似度分数（0~1，越大越相似，1 = 完全匹配）
    """

    chunk_id: str
    text: str
    metadata: ChunkMetadata
    score: float
