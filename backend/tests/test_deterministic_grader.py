"""DeterministicGrader 全场景测试

覆盖场景：
1. 全部通过
2. answer 为空
3. sources 为空
4. 页码范围不在 context 中
5. 重复 chunk_id
6. 多个检查同时失败
7. 边界条件
"""

from __future__ import annotations

import pytest

from app.domain.models import SourceReference
from app.evaluation.graders.deterministic import DeterministicGrader, GradingResult
from app.rag.models import ChunkMetadata, QueryResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_source(
    chunk_id: str = "chunk_1",
    book: str = "必修第一册",
    section: str = "1.1 集合",
    page_start: int = 1,
    page_end: int = 5,
) -> SourceReference:
    return SourceReference(
        chunk_id=chunk_id,
        book=book,
        section=section,
        page_start=page_start,
        page_end=page_end,
    )


def _make_chunk(
    chunk_id: str = "chunk_1",
    book: str = "必修第一册",
    page_start: int = 1,
    page_end: int = 5,
    score: float = 0.9,
) -> QueryResult:
    meta = ChunkMetadata(
        book=book,
        chapter="第一章",
        section="1.1 集合",
        section_id="必修第一册::1.1",
        page=page_start,
        page_start=page_start,
        page_end=page_end,
    )
    return QueryResult(
        chunk_id=chunk_id,
        text="示例文本",
        metadata=meta,
        score=score,
    )


# ---------------------------------------------------------------------------
# 测试：全部通过
# ---------------------------------------------------------------------------

class TestAllPass:
    """所有检查项均通过"""

    def test_happy_path(self) -> None:
        grader = DeterministicGrader()
        result = grader.check(
            answer="函数是一种映射关系",
            sources=[_make_source()],
            context=[_make_chunk()],
        )
        assert result.passed is True
        assert result.failures == []

    def test_multiple_sources_all_match(self) -> None:
        grader = DeterministicGrader()
        result = grader.check(
            answer="answer",
            sources=[
                _make_source(chunk_id="c1", page_start=1, page_end=5),
                _make_source(chunk_id="c2", page_start=10, page_end=15),
            ],
            context=[
                _make_chunk(chunk_id="c1", page_start=1, page_end=5),
                _make_chunk(chunk_id="c2", page_start=10, page_end=15),
            ],
        )
        assert result.passed is True


# ---------------------------------------------------------------------------
# 测试：answer 为空
# ---------------------------------------------------------------------------

class TestEmptyAnswer:
    def test_empty_string(self) -> None:
        grader = DeterministicGrader()
        result = grader.check(
            answer="",
            sources=[_make_source()],
            context=[_make_chunk()],
        )
        assert result.passed is False
        assert any("answer 为空" in f for f in result.failures)

    def test_whitespace_only(self) -> None:
        grader = DeterministicGrader()
        result = grader.check(
            answer="   ",
            sources=[_make_source()],
            context=[_make_chunk()],
        )
        assert result.passed is False
        assert any("answer 为空" in f for f in result.failures)


# ---------------------------------------------------------------------------
# 测试：sources 为空
# ---------------------------------------------------------------------------

class TestEmptySources:
    def test_no_sources(self) -> None:
        grader = DeterministicGrader()
        result = grader.check(
            answer="有内容",
            sources=[],
            context=[_make_chunk()],
        )
        assert result.passed is False
        assert any("sources 为空" in f for f in result.failures)


# ---------------------------------------------------------------------------
# 测试：页码范围不在 context 中
# ---------------------------------------------------------------------------

class TestPageOutOfRange:
    def test_source_book_not_in_context(self) -> None:
        """source 的书名在 context 中完全不存在"""
        grader = DeterministicGrader()
        result = grader.check(
            answer="answer",
            sources=[_make_source(book="必修第二册", page_start=1, page_end=5)],
            context=[_make_chunk(book="必修第一册", page_start=1, page_end=5)],
        )
        assert result.passed is False
        assert any("页码范围无匹配" in f for f in result.failures)

    def test_source_page_no_overlap(self) -> None:
        """source 书名相同但页码无交集"""
        grader = DeterministicGrader()
        result = grader.check(
            answer="answer",
            sources=[_make_source(page_start=100, page_end=110)],
            context=[_make_chunk(page_start=1, page_end=5)],
        )
        assert result.passed is False
        assert any("页码范围无匹配" in f for f in result.failures)

    def test_partial_overlap_passes(self) -> None:
        """页码有部分交集时通过"""
        grader = DeterministicGrader()
        result = grader.check(
            answer="answer",
            sources=[_make_source(page_start=3, page_end=8)],
            context=[_make_chunk(page_start=1, page_end=5)],
        )
        # 交集: 3-5, 所以通过
        assert result.passed is True

    def test_one_source_out_of_two_fails(self) -> None:
        """两个 source 中只有一个页码匹配"""
        grader = DeterministicGrader()
        result = grader.check(
            answer="answer",
            sources=[
                _make_source(chunk_id="c1", page_start=1, page_end=5),
                _make_source(chunk_id="c2", page_start=100, page_end=110),
            ],
            context=[
                _make_chunk(chunk_id="c1", page_start=1, page_end=5),
            ],
        )
        assert result.passed is False
        assert sum(1 for f in result.failures if "页码范围无匹配" in f) == 1


# ---------------------------------------------------------------------------
# 测试：重复 chunk_id
# ---------------------------------------------------------------------------

class TestDuplicateChunkId:
    def test_duplicate_sources(self) -> None:
        grader = DeterministicGrader()
        result = grader.check(
            answer="answer",
            sources=[
                _make_source(chunk_id="c1"),
                _make_source(chunk_id="c1"),  # 重复
            ],
            context=[_make_chunk(chunk_id="c1")],
        )
        assert result.passed is False
        assert any("重复 chunk_id" in f for f in result.failures)

    def test_three_sources_two_duplicate(self) -> None:
        grader = DeterministicGrader()
        result = grader.check(
            answer="answer",
            sources=[
                _make_source(chunk_id="c1", page_start=1, page_end=5),
                _make_source(chunk_id="c2", page_start=10, page_end=15),
                _make_source(chunk_id="c2", page_start=10, page_end=15),  # 与 c2 重复
            ],
            context=[
                _make_chunk(chunk_id="c1", page_start=1, page_end=5),
                _make_chunk(chunk_id="c2", page_start=10, page_end=15),
            ],
        )
        assert result.passed is False
        assert any("重复 chunk_id" in f for f in result.failures)

    def test_unique_chunk_ids_pass(self) -> None:
        grader = DeterministicGrader()
        result = grader.check(
            answer="answer",
            sources=[
                _make_source(chunk_id="c1", page_start=1, page_end=5),
                _make_source(chunk_id="c2", page_start=10, page_end=15),
            ],
            context=[
                _make_chunk(chunk_id="c1", page_start=1, page_end=5),
                _make_chunk(chunk_id="c2", page_start=10, page_end=15),
            ],
        )
        assert result.passed is True


# ---------------------------------------------------------------------------
# 测试：多个检查同时失败
# ---------------------------------------------------------------------------

class TestMultipleFailures:
    def test_all_fail(self) -> None:
        """answer 为空 + sources 为空"""
        grader = DeterministicGrader()
        result = grader.check(
            answer="",
            sources=[],
            context=[_make_chunk()],
        )
        assert result.passed is False
        assert len(result.failures) == 2

    def test_empty_answer_and_page_out_of_range(self) -> None:
        """answer 为空 + 页码超范围"""
        grader = DeterministicGrader()
        result = grader.check(
            answer="",
            sources=[_make_source(page_start=100, page_end=110)],
            context=[_make_chunk(page_start=1, page_end=5)],
        )
        assert result.passed is False
        assert len(result.failures) >= 2


# ---------------------------------------------------------------------------
# 测试：GradingResult dataclass
# ---------------------------------------------------------------------------

class TestGradingResult:
    def test_default_failures_empty(self) -> None:
        r = GradingResult(passed=True)
        assert r.failures == []

    def test_passed_false_with_failures(self) -> None:
        r = GradingResult(passed=False, failures=["a", "b"])
        assert r.passed is False
        assert len(r.failures) == 2
