"""评估集数据模型定义

定义检索评估所需的核心数据结构：EvalSource, RetrievalTruth, EvalItem, EvalSetValidation。

Usage:
    from app.evaluation.eval_types import EvalItem, RetrievalTruth, EvalSource

    source = EvalSource(book="必修第一册", page_start=67, page_end=75)
    truth = RetrievalTruth(mode="ANY", sources=[source])
    item = EvalItem(id="q001", question="什么是函数？", retrieval_truth=truth)
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EvalSource:
    """评估集单个来源定义

    表示一个期望命中的来源范围，由书名和页码范围组成。
    检索时，如果返回的 chunk 的 book 和 page 落在某个 source 的范围内，
    则认为该 source 被命中。

    Attributes:
        book: 书名（如 "必修第一册"），需与 ChromaDB 中 ChunkMetadata.book 一致
        page_start: 起始页码（含）
        page_end: 结束页码（含）
    """

    book: str
    page_start: int
    page_end: int
    section_id: str | None = None
    required_keywords: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """转换为 JSON 可序列化的字典"""
        d: dict = {
            "book": self.book,
            "page_start": self.page_start,
            "page_end": self.page_end,
        }
        if self.section_id is not None:
            d["section_id"] = self.section_id
        if self.required_keywords:
            d["required_keywords"] = self.required_keywords
        return d

    @classmethod
    def from_dict(cls, data: dict) -> EvalSource:
        """从字典构造 EvalSource

        Args:
            data: 包含 book, page_start, page_end 的字典，
                  section_id 和 required_keywords 为可选

        Returns:
            EvalSource 实例

        Raises:
            ValueError: 缺少必要字段或字段类型错误
        """
        required_keys = ("book", "page_start", "page_end")
        missing = [k for k in required_keys if k not in data]
        if missing:
            raise ValueError(f"EvalSource 缺少字段: {', '.join(missing)}")

        book = data["book"]
        page_start = data["page_start"]
        page_end = data["page_end"]

        if not isinstance(book, str) or not book.strip():
            raise ValueError(f"EvalSource.book 必须是非空字符串, got: {book!r}")
        if not isinstance(page_start, int) or page_start < 1:
            raise ValueError(f"EvalSource.page_start 必须是正整数, got: {page_start!r}")
        if not isinstance(page_end, int) or page_end < 1:
            raise ValueError(f"EvalSource.page_end 必须是正整数, got: {page_end!r}")
        if page_start > page_end:
            raise ValueError(
                f"EvalSource.page_start ({page_start}) > page_end ({page_end})"
            )

        section_id = data.get("section_id")
        required_keywords = data.get("required_keywords", [])

        return cls(
            book=book,
            page_start=page_start,
            page_end=page_end,
            section_id=section_id,
            required_keywords=required_keywords,
        )

    def contains_page(self, book: str, page: int) -> bool:
        """判断指定的书名和页码是否落在当前来源范围内

        Args:
            book: 待判断的书名
            page: 待判断的页码

        Returns:
            是否命中
        """
        return self.book == book and self.page_start <= page <= self.page_end

    def overlaps_page_range(self, book: str, page_start: int, page_end: int) -> bool:
        """判断指定书名和页码区间是否与当前来源范围重叠"""
        if self.book != book:
            return False
        return max(self.page_start, page_start) <= min(self.page_end, page_end)


@dataclass
class RetrievalTruth:
    """检索真值定义

    定义一个评估问题的期望检索结果判定规则。

    Mode 说明:
        ANY: top-K 结果中，任意一个 source 命中即判定为 Hit
        ALL: top-K 结果中，全部 source 都至少命中一次才判定为 Hit
        NEGATIVE: top-K 结果中，不应包含任何相关来源，用于测试超纲/误导性问题的拒识能力

    Attributes:
        mode: 判定模式，"ANY"、"ALL" 或 "NEGATIVE"
        sources: 期望命中的来源列表（NEGATIVE 模式下为空）
    """

    mode: str  # "ANY" | "ALL" | "NEGATIVE"
    sources: list[EvalSource]

    def to_dict(self) -> dict:
        """转换为 JSON 可序列化的字典"""
        return {
            "mode": self.mode,
            "sources": [s.to_dict() for s in self.sources],
        }

    @classmethod
    def from_dict(cls, data: dict) -> RetrievalTruth:
        """从字典构造 RetrievalTruth

        Args:
            data: 包含 mode 和 sources 的字典

        Returns:
            RetrievalTruth 实例

        Raises:
            ValueError: mode 不合法或 sources 为空
        """
        mode = data.get("mode", "")
        if mode not in ("ANY", "ALL", "NEGATIVE"):
            raise ValueError(
                f"RetrievalTruth.mode 必须是 'ANY'、'ALL' 或 'NEGATIVE', got: {mode!r}"
            )

        sources_data = data.get("sources", [])
        if mode != "NEGATIVE" and not sources_data:
            raise ValueError("RetrievalTruth.sources 不能为空（NEGATIVE 模式除外）")

        sources = [EvalSource.from_dict(s) for s in sources_data]
        return cls(mode=mode, sources=sources)

    def check_hit(self, results: list[tuple[str, int]]) -> bool:
        """判断检索结果是否命中

        Args:
            results: 检索结果的列表，每项为 (book, page) 元组

        Returns:
            是否命中（根据 mode 决定判定逻辑）
        """
        if self.mode == "NEGATIVE":
            # NEGATIVE 模式不应调用 check_hit（eval_runner 中已早返回）
            return False
        elif self.mode == "ANY":
            # 任一 source 命中即可
            for source in self.sources:
                for book, page in results:
                    if source.contains_page(book, page):
                        return True
            return False
        else:  # ALL
            # 每个 source 都至少命中一次
            for source in self.sources:
                hit = False
                for book, page in results:
                    if source.contains_page(book, page):
                        hit = True
                        break
                if not hit:
                    return False
            return True

    def check_hit_ranges(self, results: list[tuple[str, int, int]]) -> bool:
        """判断带覆盖区间的检索结果是否命中

        Args:
            results: 检索结果列表，每项为 (book, page_start, page_end)

        Returns:
            是否命中（根据 mode 决定判定逻辑）
        """
        if self.mode == "NEGATIVE":
            return False
        elif self.mode == "ANY":
            for source in self.sources:
                for book, page_start, page_end in results:
                    if source.overlaps_page_range(book, page_start, page_end):
                        return True
            return False
        else:  # ALL
            for source in self.sources:
                hit = False
                for book, page_start, page_end in results:
                    if source.overlaps_page_range(book, page_start, page_end):
                        hit = True
                        break
                if not hit:
                    return False
            return True


@dataclass
class EvalItem:
    """评估集单条数据

    表示一个用于评估检索质量的问题及其期望的检索真值。

    Attributes:
        id: 唯一标识（如 "q001"）
        question: 查询问题文本
        retrieval_truth: 检索真值
    """

    id: str
    question: str
    retrieval_truth: RetrievalTruth

    def to_dict(self) -> dict:
        """转换为 JSON 可序列化的字典"""
        return {
            "id": self.id,
            "question": self.question,
            "retrieval_truth": self.retrieval_truth.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> EvalItem:
        """从字典构造 EvalItem

        Args:
            data: 包含 id, question, retrieval_truth 的字典

        Returns:
            EvalItem 实例

        Raises:
            ValueError: 缺少必要字段或字段校验失败
        """
        id_val = data.get("id", "")
        if not isinstance(id_val, str) or not id_val.strip():
            raise ValueError(f"EvalItem.id 必须是非空字符串, got: {id_val!r}")

        question = data.get("question", "")
        if not isinstance(question, str) or not question.strip():
            raise ValueError(f"EvalItem.question 必须是非空字符串, got: {question!r}")

        truth_data = data.get("retrieval_truth")
        if truth_data is None:
            raise ValueError("EvalItem.retrieval_truth 不能为空")

        retrieval_truth = RetrievalTruth.from_dict(truth_data)
        return cls(id=id_val, question=question, retrieval_truth=retrieval_truth)


@dataclass
class EvalSetValidation:
    """评估集验证结果

    Attributes:
        total_items: 总条目数
        unique_ids: ID 是否全部唯一
        books_covered: 覆盖的书名集合
        items_per_book: 每本书的条目数映射
        min_items_per_book: 每本书最少条目数
        errors: 验证错误列表（阻断性问题）
        warnings: 验证警告列表（非阻断性问题）
        passed: 是否通过全部验证（无 error）
    """

    total_items: int
    unique_ids: bool
    books_covered: set[str] = field(default_factory=set)
    items_per_book: dict[str, int] = field(default_factory=dict)
    min_items_per_book: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    passed: bool = True
