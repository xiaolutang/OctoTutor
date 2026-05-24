"""RAG context 构建工具"""

from app.rag.models import QueryResult


def build_numbered_context(chunks: list[QueryResult]) -> str:
    """构建带编号标记的 context 文本"""
    parts = []
    for i, chunk in enumerate(chunks, 1):
        parts.append(
            f"[{i}] ({chunk.metadata.book} - {chunk.metadata.section}, "
            f"第{chunk.metadata.page_start}-{chunk.metadata.page_end}页)\n"
            f"{chunk.text}"
        )
    return "\n\n".join(parts)


from app.domain.models import SourceReference


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
