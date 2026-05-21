"""入库抽检模块

验证入库数据质量：页码范围、内容完整性、Parent-Child 分块结构、元数据正确性。

Usage:
    from app.ingestion.spot_check import SpotChecker

    checker = SpotChecker(vector_store=store, sample_pages=3)
    summary = checker.run()
    print(f"抽检通过: {summary.all_passed}")
"""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field

from app.rag.models import ChunkMetadata
from app.rag.vector_store import ChromaDBStore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 抽检结果数据类
# ---------------------------------------------------------------------------


@dataclass
class PageRangeCheck:
    """页码范围检查结果

    Attributes:
        book: 书名
        min_page: ChromaDB 中该书的最低页码
        max_page: ChromaDB 中该书的最高页码
        expected_max: 预期最高页码（None 表示无法获取 PDF 页数）
        passed: 是否通过
        detail: 检查详情
    """

    book: str
    min_page: int
    max_page: int
    expected_max: int | None
    passed: bool
    detail: str


@dataclass
class ContentCheck:
    """内容完整性检查结果

    Attributes:
        book: 书名
        page: 抽查的页码
        chunks_found: 该页找到的 chunk 数量
        has_content: 是否有非空内容
        passed: 是否通过
        detail: 检查详情
    """

    book: str
    page: int
    chunks_found: int
    has_content: bool
    passed: bool
    detail: str


@dataclass
class ParentChildCheck:
    """Parent-Child 结构检查结果

    Attributes:
        parent_id: Parent chunk ID
        child_count: 该 Parent 下的 Child 数量
        passed: 是否通过
        detail: 检查详情
    """

    parent_id: str
    child_count: int
    passed: bool
    detail: str


@dataclass
class MetadataCheck:
    """元数据完整性检查结果

    Attributes:
        chunk_id: Chunk ID
        missing_fields: 缺失的字段列表
        passed: 是否通过
        detail: 检查详情
    """

    chunk_id: str
    missing_fields: list[str]
    passed: bool
    detail: str


@dataclass
class SpotCheckSummary:
    """抽检汇总

    Attributes:
        total_books: 涉及的书籍数量
        total_chunks: 总 chunk 数量
        page_range_checks: 页码范围检查结果列表
        content_checks: 内容完整性检查结果列表
        parent_child_checks: Parent-Child 结构检查结果列表
        metadata_checks: 元数据完整性检查结果列表
        all_passed: 所有检查是否全部通过
        duration_seconds: 抽检总耗时（秒）
    """

    total_books: int = 0
    total_chunks: int = 0
    page_range_checks: list[PageRangeCheck] = field(default_factory=list)
    content_checks: list[ContentCheck] = field(default_factory=list)
    parent_child_checks: list[ParentChildCheck] = field(default_factory=list)
    metadata_checks: list[MetadataCheck] = field(default_factory=list)
    all_passed: bool = True
    duration_seconds: float = 0.0


# ---------------------------------------------------------------------------
# SpotChecker
# ---------------------------------------------------------------------------


# 需要检查的元数据字段
_REQUIRED_METADATA_FIELDS = ["book", "chapter", "section", "page"]


def _parse_source_pages(raw: str | list) -> list[int]:
    """将 source_pages 从逗号分隔字符串或列表解析为 int 列表"""
    if isinstance(raw, list):
        return [int(p) for p in raw]
    if isinstance(raw, str) and raw.strip():
        return [int(p.strip()) for p in raw.split(",") if p.strip()]
    return []


class SpotChecker:
    """入库抽检器

    从 ChromaDB 拉取全部入库数据，执行以下检查：
    1. 页码范围检查：每本书的 min(page) >= 1
    2. 内容完整性检查：抽查 N 页，验证有内容
    3. Parent-Child 结构检查：每个 parent 至少有 1 个 child
    4. 元数据完整性检查：每个 chunk 的关键字段非空

    Args:
        vector_store: ChromaDB 向量存储
        sample_pages: 每本书抽查的页数，默认 3
    """

    def __init__(
        self,
        vector_store: ChromaDBStore,
        sample_pages: int = 3,
    ) -> None:
        self._store = vector_store
        self._sample_pages = sample_pages

    def run(self) -> SpotCheckSummary:
        """执行抽检

        Returns:
            SpotCheckSummary 抽检汇总
        """
        start_time = time.time()
        summary = SpotCheckSummary()

        # 1. 从 ChromaDB 拉取全部数据
        chunks_data = self._fetch_all_chunks()

        if not chunks_data:
            summary.duration_seconds = time.time() - start_time
            logger.info("ChromaDB 为空，抽检跳过")
            return summary

        # chunks_data: list[tuple[chunk_id, text, metadata_dict]]
        summary.total_chunks = len(chunks_data)

        # 2. 解析 ChunkMetadata
        all_metadata: list[tuple[str, str, ChunkMetadata]] = []
        for chunk_id, text, meta_dict in chunks_data:
            metadata = ChunkMetadata(
                book=meta_dict.get("book", ""),
                chapter=meta_dict.get("chapter", ""),
                section=meta_dict.get("section", ""),
                section_id=meta_dict.get("section_id", ""),
                page=int(meta_dict.get("page", 0)),
                page_start=int(meta_dict.get("page_start", meta_dict.get("page", 0))),
                page_end=int(meta_dict.get("page_end", meta_dict.get("page", 0))),
                source_pages=_parse_source_pages(meta_dict.get("source_pages", "")),
                chunk_type=meta_dict.get("chunk_type", ""),
                block_type=meta_dict.get("block_type", "unknown"),
                has_formula=bool(meta_dict.get("has_formula", False)),
                parent_id=meta_dict.get("parent_id", ""),
                child_index=int(meta_dict.get("child_index", 0)),
            )
            all_metadata.append((chunk_id, text, metadata))

        # 3. 按书分组
        books: dict[str, list[tuple[str, str, ChunkMetadata]]] = {}
        for item in all_metadata:
            book = item[2].book
            if book not in books:
                books[book] = []
            books[book].append(item)

        summary.total_books = len(books)

        # 4. 页码范围检查
        summary.page_range_checks = self._check_page_ranges(books)

        # 5. 内容完整性检查
        summary.content_checks = self._check_content(books)

        # 6. Parent-Child 结构检查
        summary.parent_child_checks = self._check_parent_child(all_metadata)

        # 7. 元数据完整性检查
        summary.metadata_checks = self._check_metadata(all_metadata)

        # 8. 汇总
        summary.all_passed = (
            all(c.passed for c in summary.page_range_checks)
            and all(c.passed for c in summary.content_checks)
            and all(c.passed for c in summary.parent_child_checks)
            and all(c.passed for c in summary.metadata_checks)
        )

        summary.duration_seconds = time.time() - start_time

        logger.info(
            "抽检完成: %d 本书, %d chunks, 通过=%s, 耗时 %.2fs",
            summary.total_books,
            summary.total_chunks,
            summary.all_passed,
            summary.duration_seconds,
        )

        return summary

    def _fetch_all_chunks(self) -> list[tuple[str, str, dict]]:
        """从 ChromaDB 拉取全部 chunk 数据

        Returns:
            [(chunk_id, text, metadata_dict), ...] 列表
        """
        total = self._store.count()
        if total == 0:
            return []

        # 使用 collection.get() 拉取全部数据
        results = self._store._collection.get(
            include=["documents", "metadatas"],
        )

        if not results["ids"]:
            return []

        chunks_data: list[tuple[str, str, dict]] = []
        ids = results["ids"]
        documents = results["documents"] if results["documents"] else [""] * len(ids)
        metadatas = results["metadatas"] if results["metadatas"] else [{}] * len(ids)

        for chunk_id, text, meta in zip(ids, documents, metadatas):
            chunks_data.append((chunk_id, text or "", meta or {}))

        return chunks_data

    def _check_page_ranges(
        self,
        books: dict[str, list[tuple[str, str, ChunkMetadata]]],
    ) -> list[PageRangeCheck]:
        """页码范围检查

        每本书的 min_page >= 1，max_page 合理。
        """
        checks: list[PageRangeCheck] = []

        for book, items in books.items():
            pages = [item[2].page for item in items]
            min_page = min(pages)
            max_page = max(pages)

            passed = min_page >= 1 and max_page >= 1

            if min_page < 1:
                detail = f"min_page={min_page} < 1，页码异常"
            else:
                detail = f"页码范围 [{min_page}, {max_page}]，正常"

            checks.append(
                PageRangeCheck(
                    book=book,
                    min_page=min_page,
                    max_page=max_page,
                    expected_max=None,
                    passed=passed,
                    detail=detail,
                )
            )

        return checks

    def _check_content(
        self,
        books: dict[str, list[tuple[str, str, ChunkMetadata]]],
    ) -> list[ContentCheck]:
        """内容完整性检查

        每本书抽查 sample_pages 页，验证该页的 chunks 有非空内容。
        """
        checks: list[ContentCheck] = []

        for book, items in books.items():
            # 收集该书所有出现的页码
            pages = sorted(set(item[2].page for item in items))

            if not pages:
                continue

            # 均匀选取 sample_pages 页
            sample = self._select_sample_pages(pages, self._sample_pages)

            for page in sample:
                # 找到该页的所有 chunks
                page_items = [
                    (cid, text) for cid, text, meta in items if meta.page == page
                ]
                chunks_found = len(page_items)

                # 检查内容是否非空
                has_content = all(
                    text.strip() for _, text in page_items
                ) if page_items else False

                passed = chunks_found > 0 and has_content

                if passed:
                    detail = f"第 {page} 页有 {chunks_found} 个 chunks，内容完整"
                elif chunks_found == 0:
                    detail = f"第 {page} 页无 chunks"
                else:
                    detail = f"第 {page} 页有 {chunks_found} 个 chunks，但存在空内容"

                checks.append(
                    ContentCheck(
                        book=book,
                        page=page,
                        chunks_found=chunks_found,
                        has_content=has_content,
                        passed=passed,
                        detail=detail,
                    )
                )

        return checks

    def _check_parent_child(
        self,
        all_metadata: list[tuple[str, str, ChunkMetadata]],
    ) -> list[ParentChildCheck]:
        """Parent-Child 结构检查

        验证每个 parent 至少有 1 个 child，child 的 parent_id 指向存在的 parent。
        """
        checks: list[ParentChildCheck] = []

        # 收集所有 parent 和 child 的 ID
        parent_ids: set[str] = set()
        child_to_parent: dict[str, str] = {}  # child_id -> parent_id
        parent_child_count: dict[str, int] = {}  # parent_id -> child_count

        for chunk_id, _text, meta in all_metadata:
            if meta.chunk_type == "parent":
                parent_ids.add(chunk_id)
                parent_child_count[chunk_id] = 0
            elif meta.chunk_type == "child":
                child_to_parent[chunk_id] = meta.parent_id

        # 统计每个 parent 的 child 数量
        for _child_id, parent_id in child_to_parent.items():
            if parent_id in parent_child_count:
                parent_child_count[parent_id] += 1

        # 检查每个 parent
        for parent_id in parent_ids:
            child_count = parent_child_count.get(parent_id, 0)
            passed = child_count >= 1

            if passed:
                detail = f"parent {parent_id} 有 {child_count} 个 children"
            else:
                detail = f"parent {parent_id} 无 children（孤儿 parent）"

            checks.append(
                ParentChildCheck(
                    parent_id=parent_id,
                    child_count=child_count,
                    passed=passed,
                    detail=detail,
                )
            )

        # 检查悬空 child（parent_id 指向不存在的 parent）
        for child_id, parent_id in child_to_parent.items():
            if parent_id not in parent_ids:
                checks.append(
                    ParentChildCheck(
                        parent_id=parent_id,
                        child_count=0,
                        passed=False,
                        detail=f"child {child_id} 的 parent_id={parent_id} 不存在（悬空 child）",
                    )
                )

        return checks

    def _check_metadata(
        self,
        all_metadata: list[tuple[str, str, ChunkMetadata]],
    ) -> list[MetadataCheck]:
        """元数据完整性检查

        验证每个 chunk 的 book/chapter/section/page 字段非空。
        """
        checks: list[MetadataCheck] = []

        for chunk_id, _text, meta in all_metadata:
            missing: list[str] = []

            if not meta.book:
                missing.append("book")
            if not meta.chapter:
                missing.append("chapter")
            if not meta.section:
                missing.append("section")
            if meta.page <= 0:
                missing.append("page")

            passed = len(missing) == 0
            detail = (
                "元数据完整"
                if passed
                else f"缺失字段: {', '.join(missing)}"
            )

            checks.append(
                MetadataCheck(
                    chunk_id=chunk_id,
                    missing_fields=missing,
                    passed=passed,
                    detail=detail,
                )
            )

        return checks

    @staticmethod
    def _select_sample_pages(pages: list[int], sample_count: int) -> list[int]:
        """从页码列表中均匀选取 sample_count 页

        如果页数 <= sample_count，返回全部。
        否则均匀间隔选取。

        Args:
            pages: 已排序的页码列表
            sample_count: 要选取的数量

        Returns:
            选中的页码列表
        """
        if len(pages) <= sample_count:
            return pages

        # 均匀间隔选取
        step = len(pages) / sample_count
        selected = []
        for i in range(sample_count):
            idx = int(i * step)
            selected.append(pages[idx])

        return selected
