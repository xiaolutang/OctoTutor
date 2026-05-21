"""入库抽检模块单元测试

使用 mock ChromaDBStore 验证抽检逻辑。
不需要真实 PDF 或 ChromaDB。
"""

from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock

import pytest

from app.ingestion.spot_check import (
    ContentCheck,
    MetadataCheck,
    PageRangeCheck,
    ParentChildCheck,
    SpotCheckSummary,
    SpotChecker,
)


# ---------- 辅助函数 ----------


def _make_meta(**overrides) -> dict:
    """创建 metadata 字典，提供合理默认值"""
    defaults = dict(
        book="必修第一册",
        chapter="第一章 集合与函数概念",
        section="1.1 集合",
        page=12,
        chunk_type="child",
        has_formula=False,
        parent_id="必修第一册::1.1集合::p12_s0::parent",
        child_index=0,
    )
    defaults.update(overrides)
    return defaults


def _make_store_mock(chunks_data: list[tuple[str, str, dict]]) -> MagicMock:
    """创建 mock ChromaDBStore

    Args:
        chunks_data: [(chunk_id, text, metadata_dict), ...] 列表
    """
    store = MagicMock()

    ids = [c[0] for c in chunks_data]
    documents = [c[1] for c in chunks_data]
    metadatas = [c[2] for c in chunks_data]

    store.count.return_value = len(chunks_data)
    store._collection.get.return_value = {
        "ids": ids,
        "documents": documents,
        "metadatas": metadatas,
    }

    return store


def _normal_chunks() -> list[tuple[str, str, dict]]:
    """构造一组正常的 chunks 数据（完整 parent-child 结构）"""
    return [
        (
            "必修第一册::1.1集合::p12_s0::parent",
            "1.1 集合\n集合的概念与基本运算",
            _make_meta(
                chunk_type="parent",
                parent_id="必修第一册::1.1集合::p12_s0::parent",
                child_index=0,
            ),
        ),
        (
            "必修第一册::1.1集合::p12_s0::child::0",
            "集合的概念：一般地，把一些能够确定的不同对象看成一个整体。",
            _make_meta(child_index=0),
        ),
        (
            "必修第一册::1.1集合::p12_s0::child::1",
            "集合中的每个对象叫做这个集合的元素。",
            _make_meta(child_index=1),
        ),
        (
            "必修第一册::1.1集合::p13_s1::parent",
            "1.1 集合（续）\n子集与真子集",
            _make_meta(
                page=13,
                chunk_type="parent",
                parent_id="必修第一册::1.1集合::p13_s1::parent",
                child_index=0,
                section="1.1 集合（续）",
            ),
        ),
        (
            "必修第一册::1.1集合::p13_s1::child::0",
            "子集的定义和性质。",
            _make_meta(
                page=13,
                child_index=0,
                parent_id="必修第一册::1.1集合::p13_s1::parent",
                section="1.1 集合（续）",
            ),
        ),
    ]


# ---------- 页码范围检查 ----------


class TestPageRangeCheck:
    """页码范围检查测试"""

    def test_normal_range(self) -> None:
        """正常页码范围通过检查"""
        store = _make_store_mock(_normal_chunks())
        checker = SpotChecker(store)
        summary = checker.run()

        assert len(summary.page_range_checks) == 1
        check = summary.page_range_checks[0]
        assert check.book == "必修第一册"
        assert check.min_page == 12
        assert check.max_page == 13
        assert check.passed is True

    def test_page_zero_fails(self) -> None:
        """page=0 的 chunk 导致检查失败"""
        chunks = [
            (
                "book::s::p0_s0::child::0",
                "内容",
                _make_meta(page=0),
            ),
        ]
        store = _make_store_mock(chunks)
        checker = SpotChecker(store)
        summary = checker.run()

        assert len(summary.page_range_checks) == 1
        assert summary.page_range_checks[0].passed is False
        assert "min_page=0" in summary.page_range_checks[0].detail

    def test_negative_page_fails(self) -> None:
        """负页码导致检查失败"""
        chunks = [
            (
                "book::s::p-1_s0::child::0",
                "内容",
                _make_meta(page=-1),
            ),
        ]
        store = _make_store_mock(chunks)
        checker = SpotChecker(store)
        summary = checker.run()

        assert summary.page_range_checks[0].passed is False

    def test_multiple_books(self) -> None:
        """多本书分别检查"""
        chunks = [
            (
                "必修第一册::s::p1_s0::child::0",
                "内容1",
                _make_meta(book="必修第一册", page=5),
            ),
            (
                "必修第二册::s::p1_s0::child::0",
                "内容2",
                _make_meta(book="必修第二册", page=10),
            ),
        ]
        store = _make_store_mock(chunks)
        checker = SpotChecker(store)
        summary = checker.run()

        assert len(summary.page_range_checks) == 2
        assert summary.total_books == 2


# ---------- 内容完整性检查 ----------


class TestContentCheck:
    """内容完整性检查测试"""

    def test_normal_content(self) -> None:
        """有内容的页通过检查"""
        store = _make_store_mock(_normal_chunks())
        checker = SpotChecker(store, sample_pages=3)
        summary = checker.run()

        assert len(summary.content_checks) > 0
        assert all(c.passed for c in summary.content_checks)

    def test_empty_content_fails(self) -> None:
        """空内容的 chunk 导致检查失败"""
        chunks = [
            (
                "book::s::p5_s0::parent",
                "",
                _make_meta(
                    page=5,
                    chunk_type="parent",
                    parent_id="book::s::p5_s0::parent",
                ),
            ),
            (
                "book::s::p5_s0::child::0",
                "",
                _make_meta(page=5),
            ),
        ]
        store = _make_store_mock(chunks)
        checker = SpotChecker(store, sample_pages=3)
        summary = checker.run()

        assert any(not c.passed for c in summary.content_checks)

    def test_no_chunks_for_page(self) -> None:
        """抽查的页没有 chunks 时检查失败"""
        # 只有 page=1 的数据，但 sample 会选中 page=1
        chunks = [
            (
                "book::s::p1_s0::parent",
                "内容",
                _make_meta(
                    page=1,
                    chunk_type="parent",
                    parent_id="book::s::p1_s0::parent",
                ),
            ),
        ]
        store = _make_store_mock(chunks)
        checker = SpotChecker(store, sample_pages=1)
        summary = checker.run()

        assert len(summary.content_checks) >= 1


# ---------- Parent-Child 结构检查 ----------


class TestParentChildCheck:
    """Parent-Child 结构检查测试"""

    def test_normal_structure(self) -> None:
        """正常的 parent-child 结构通过检查"""
        store = _make_store_mock(_normal_chunks())
        checker = SpotChecker(store)
        summary = checker.run()

        assert len(summary.parent_child_checks) >= 2  # 2 个 parent
        assert all(c.passed for c in summary.parent_child_checks)

    def test_orphan_parent_fails(self) -> None:
        """孤儿 parent（无 child）检查失败"""
        chunks = [
            (
                "book::s::p1_s0::parent",
                "内容",
                _make_meta(
                    page=1,
                    chunk_type="parent",
                    parent_id="book::s::p1_s0::parent",
                ),
            ),
            # 没有 child
        ]
        store = _make_store_mock(chunks)
        checker = SpotChecker(store)
        summary = checker.run()

        orphan_checks = [c for c in summary.parent_child_checks if "孤儿" in c.detail]
        assert len(orphan_checks) >= 1
        assert orphan_checks[0].passed is False
        assert orphan_checks[0].child_count == 0

    def test_dangling_child_fails(self) -> None:
        """悬空 child（parent_id 指向不存在的 parent）检查失败"""
        chunks = [
            (
                "book::s::p1_s0::child::0",
                "内容",
                _make_meta(
                    page=1,
                    parent_id="nonexistent_parent_id",
                ),
            ),
        ]
        store = _make_store_mock(chunks)
        checker = SpotChecker(store)
        summary = checker.run()

        dangling_checks = [c for c in summary.parent_child_checks if "悬空" in c.detail]
        assert len(dangling_checks) >= 1
        assert dangling_checks[0].passed is False

    def test_parent_with_multiple_children(self) -> None:
        """一个 parent 有多个 child 通过检查"""
        chunks = [
            (
                "book::s::p1_s0::parent",
                "父内容",
                _make_meta(
                    page=1,
                    chunk_type="parent",
                    parent_id="book::s::p1_s0::parent",
                ),
            ),
            (
                "book::s::p1_s0::child::0",
                "子内容1",
                _make_meta(
                    page=1, child_index=0,
                    parent_id="book::s::p1_s0::parent",
                ),
            ),
            (
                "book::s::p1_s0::child::1",
                "子内容2",
                _make_meta(
                    page=1, child_index=1,
                    parent_id="book::s::p1_s0::parent",
                ),
            ),
            (
                "book::s::p1_s0::child::2",
                "子内容3",
                _make_meta(
                    page=1, child_index=2,
                    parent_id="book::s::p1_s0::parent",
                ),
            ),
        ]
        store = _make_store_mock(chunks)
        checker = SpotChecker(store)
        summary = checker.run()

        parent_checks = [
            c for c in summary.parent_child_checks
            if c.parent_id == "book::s::p1_s0::parent"
        ]
        assert len(parent_checks) == 1
        assert parent_checks[0].child_count == 3
        assert parent_checks[0].passed is True


# ---------- 元数据完整性检查 ----------


class TestMetadataCheck:
    """元数据完整性检查测试"""

    def test_complete_metadata(self) -> None:
        """完整元数据通过检查"""
        store = _make_store_mock(_normal_chunks())
        checker = SpotChecker(store)
        summary = checker.run()

        assert all(c.passed for c in summary.metadata_checks)

    def test_missing_book_fails(self) -> None:
        """缺少 book 字段导致检查失败"""
        chunks = [
            (
                "id1",
                "内容",
                _make_meta(book=""),
            ),
        ]
        store = _make_store_mock(chunks)
        checker = SpotChecker(store)
        summary = checker.run()

        assert len(summary.metadata_checks) == 1
        assert summary.metadata_checks[0].passed is False
        assert "book" in summary.metadata_checks[0].missing_fields

    def test_missing_chapter_fails(self) -> None:
        """缺少 chapter 字段导致检查失败"""
        chunks = [
            (
                "id1",
                "内容",
                _make_meta(chapter=""),
            ),
        ]
        store = _make_store_mock(chunks)
        checker = SpotChecker(store)
        summary = checker.run()

        assert summary.metadata_checks[0].passed is False
        assert "chapter" in summary.metadata_checks[0].missing_fields

    def test_missing_section_fails(self) -> None:
        """缺少 section 字段导致检查失败"""
        chunks = [
            (
                "id1",
                "内容",
                _make_meta(section=""),
            ),
        ]
        store = _make_store_mock(chunks)
        checker = SpotChecker(store)
        summary = checker.run()

        assert summary.metadata_checks[0].passed is False
        assert "section" in summary.metadata_checks[0].missing_fields

    def test_missing_page_fails(self) -> None:
        """page=0 视为缺失"""
        chunks = [
            (
                "id1",
                "内容",
                _make_meta(page=0),
            ),
        ]
        store = _make_store_mock(chunks)
        checker = SpotChecker(store)
        summary = checker.run()

        assert summary.metadata_checks[0].passed is False
        assert "page" in summary.metadata_checks[0].missing_fields

    def test_multiple_missing_fields(self) -> None:
        """同时缺少多个字段"""
        chunks = [
            (
                "id1",
                "内容",
                {
                    "book": "",
                    "chapter": "",
                    "section": "",
                    "page": 0,
                    "chunk_type": "child",
                    "has_formula": False,
                    "parent_id": "p1",
                    "child_index": 0,
                },
            ),
        ]
        store = _make_store_mock(chunks)
        checker = SpotChecker(store)
        summary = checker.run()

        assert summary.metadata_checks[0].passed is False
        assert len(summary.metadata_checks[0].missing_fields) == 4


# ---------- 全量抽检汇总 ----------


class TestSpotCheckSummary:
    """抽检汇总测试"""

    def test_all_passed(self) -> None:
        """正常数据全部检查通过"""
        store = _make_store_mock(_normal_chunks())
        checker = SpotChecker(store)
        summary = checker.run()

        assert summary.all_passed is True
        assert summary.total_books == 1
        assert summary.total_chunks == 5
        assert summary.duration_seconds >= 0

    def test_not_all_passed(self) -> None:
        """有异常数据时 all_passed 为 False"""
        chunks = [
            # orphan parent
            (
                "book::s::p1_s0::parent",
                "内容",
                _make_meta(
                    page=1,
                    chunk_type="parent",
                    parent_id="book::s::p1_s0::parent",
                ),
            ),
            # empty content child
            (
                "book::s::p1_s0::child::0",
                "",
                _make_meta(page=1),
            ),
        ]
        store = _make_store_mock(chunks)
        checker = SpotChecker(store)
        summary = checker.run()

        assert summary.all_passed is False

    def test_empty_store(self) -> None:
        """空库抽检通过（无数据可检查）"""
        store = _make_store_mock([])
        checker = SpotChecker(store)
        summary = checker.run()

        assert summary.total_books == 0
        assert summary.total_chunks == 0
        assert summary.all_passed is True
        assert len(summary.page_range_checks) == 0
        assert len(summary.content_checks) == 0
        assert len(summary.parent_child_checks) == 0
        assert len(summary.metadata_checks) == 0


# ---------- sample_pages 选取 ----------


class TestSamplePageSelection:
    """均匀抽样页码选取测试"""

    def test_select_fewer_than_sample(self) -> None:
        """页数少于 sample_pages 时返回全部"""
        result = SpotChecker._select_sample_pages([1, 2], 5)
        assert result == [1, 2]

    def test_select_equal_to_sample(self) -> None:
        """页数等于 sample_pages 时返回全部"""
        result = SpotChecker._select_sample_pages([1, 2, 3], 3)
        assert result == [1, 2, 3]

    def test_select_more_than_sample(self) -> None:
        """页数多于 sample_pages 时均匀选取"""
        result = SpotChecker._select_sample_pages([1, 2, 3, 4, 5, 6, 7, 8, 9], 3)
        assert len(result) == 3
        # 验证选取的是均匀分布的
        assert result[0] == 1
        assert result[-1] <= 9

    def test_select_single_page(self) -> None:
        """单页时返回该页"""
        result = SpotChecker._select_sample_pages([5], 3)
        assert result == [5]

    def test_select_from_many(self) -> None:
        """从大量页码中抽样"""
        pages = list(range(1, 201))
        result = SpotChecker._select_sample_pages(pages, 5)
        assert len(result) == 5


# ---------- spot_check 汇总 JSON 结构验证 ----------


class TestSpotCheckSummaryDataclass:
    """验证 SpotCheckSummary 数据结构"""

    def test_default_values(self) -> None:
        """默认值正确"""
        summary = SpotCheckSummary()
        assert summary.total_books == 0
        assert summary.total_chunks == 0
        assert summary.all_passed is True
        assert summary.duration_seconds == 0.0
        assert isinstance(summary.page_range_checks, list)
        assert isinstance(summary.content_checks, list)
        assert isinstance(summary.parent_child_checks, list)
        assert isinstance(summary.metadata_checks, list)

    def test_result_dataclass_fields(self) -> None:
        """各检查结果数据类字段完整"""
        pr = PageRangeCheck(
            book="test", min_page=1, max_page=10, expected_max=None,
            passed=True, detail="ok",
        )
        assert pr.book == "test"

        cc = ContentCheck(
            book="test", page=5, chunks_found=3, has_content=True,
            passed=True, detail="ok",
        )
        assert cc.page == 5

        pc = ParentChildCheck(
            parent_id="p1", child_count=2, passed=True, detail="ok",
        )
        assert pc.child_count == 2

        mc = MetadataCheck(
            chunk_id="c1", missing_fields=[], passed=True, detail="ok",
        )
        assert mc.missing_fields == []
