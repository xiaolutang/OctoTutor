"""评估集数据模型和加载器测试

测试 EvalSource, RetrievalTruth, EvalItem 的构造和序列化，
以及 EvalSetLoader 的加载、验证功能。
"""

import json
import os
import tempfile

import pytest

from app.evaluation.eval_types import (
    EvalItem,
    EvalSetValidation,
    EvalSource,
    RetrievalTruth,
)
from app.evaluation.eval_set_loader import EvalSetLoader


# ============================================================================
# EvalSource 测试
# ============================================================================


class TestEvalSource:
    """EvalSource 数据模型测试"""

    def test_construct_normal(self) -> None:
        """正常构造 EvalSource"""
        source = EvalSource(book="必修第一册", page_start=10, page_end=20)
        assert source.book == "必修第一册"
        assert source.page_start == 10
        assert source.page_end == 20

    def test_to_dict(self) -> None:
        """to_dict 序列化"""
        source = EvalSource(book="必修第一册", page_start=10, page_end=20)
        d = source.to_dict()
        assert d == {"book": "必修第一册", "page_start": 10, "page_end": 20}

    def test_from_dict_normal(self) -> None:
        """from_dict 正常解析"""
        data = {"book": "必修第二册", "page_start": 5, "page_end": 15}
        source = EvalSource.from_dict(data)
        assert source.book == "必修第二册"
        assert source.page_start == 5
        assert source.page_end == 15

    def test_from_dict_missing_fields(self) -> None:
        """from_dict 缺少字段"""
        with pytest.raises(ValueError, match="缺少字段"):
            EvalSource.from_dict({"book": "test"})

    def test_from_dict_empty_book(self) -> None:
        """from_dict 书名为空"""
        with pytest.raises(ValueError, match="book"):
            EvalSource.from_dict({"book": "", "page_start": 1, "page_end": 5})

    def test_from_dict_invalid_page_start(self) -> None:
        """from_dict page_start 非正整数"""
        with pytest.raises(ValueError, match="page_start"):
            EvalSource.from_dict({"book": "test", "page_start": 0, "page_end": 5})

    def test_from_dict_page_start_greater_than_end(self) -> None:
        """from_dict page_start > page_end"""
        with pytest.raises(ValueError, match="page_start.*page_end"):
            EvalSource.from_dict({"book": "test", "page_start": 10, "page_end": 5})

    def test_contains_page_hit(self) -> None:
        """contains_page 命中"""
        source = EvalSource(book="必修第一册", page_start=10, page_end=20)
        assert source.contains_page("必修第一册", 15) is True

    def test_contains_page_boundary(self) -> None:
        """contains_page 边界值"""
        source = EvalSource(book="必修第一册", page_start=10, page_end=20)
        assert source.contains_page("必修第一册", 10) is True
        assert source.contains_page("必修第一册", 20) is True

    def test_contains_page_miss_book(self) -> None:
        """contains_page 书名不匹配"""
        source = EvalSource(book="必修第一册", page_start=10, page_end=20)
        assert source.contains_page("必修第二册", 15) is False

    def test_contains_page_miss_page(self) -> None:
        """contains_page 页码不在范围内"""
        source = EvalSource(book="必修第一册", page_start=10, page_end=20)
        assert source.contains_page("必修第一册", 5) is False
        assert source.contains_page("必修第一册", 25) is False

    def test_roundtrip(self) -> None:
        """to_dict → from_dict 往返"""
        original = EvalSource(book="选择性必修第一册", page_start=50, page_end=80)
        restored = EvalSource.from_dict(original.to_dict())
        assert restored.book == original.book
        assert restored.page_start == original.page_start
        assert restored.page_end == original.page_end


# ============================================================================
# RetrievalTruth 测试
# ============================================================================


class TestRetrievalTruth:
    """RetrievalTruth 数据模型测试"""

    def test_construct_any(self) -> None:
        """ANY 模式构造"""
        sources = [EvalSource(book="必修第一册", page_start=1, page_end=10)]
        truth = RetrievalTruth(mode="ANY", sources=sources)
        assert truth.mode == "ANY"
        assert len(truth.sources) == 1

    def test_construct_all(self) -> None:
        """ALL 模式构造"""
        sources = [
            EvalSource(book="必修第一册", page_start=1, page_end=10),
            EvalSource(book="必修第一册", page_start=20, page_end=30),
        ]
        truth = RetrievalTruth(mode="ALL", sources=sources)
        assert truth.mode == "ALL"
        assert len(truth.sources) == 2

    def test_from_dict_invalid_mode(self) -> None:
        """from_dict mode 不合法"""
        with pytest.raises(ValueError, match="mode"):
            RetrievalTruth.from_dict({"mode": "INVALID", "sources": [{"book": "a", "page_start": 1, "page_end": 5}]})

    def test_from_dict_empty_sources(self) -> None:
        """from_dict sources 为空"""
        with pytest.raises(ValueError, match="sources"):
            RetrievalTruth.from_dict({"mode": "ANY", "sources": []})

    def test_to_dict(self) -> None:
        """to_dict 序列化"""
        sources = [EvalSource(book="test", page_start=1, page_end=5)]
        truth = RetrievalTruth(mode="ANY", sources=sources)
        d = truth.to_dict()
        assert d["mode"] == "ANY"
        assert len(d["sources"]) == 1

    def test_check_hit_any_hit(self) -> None:
        """ANY 模式：命中"""
        truth = RetrievalTruth(
            mode="ANY",
            sources=[EvalSource(book="必修第一册", page_start=10, page_end=20)],
        )
        results = [("必修第一册", 15)]
        assert truth.check_hit(results) is True

    def test_check_hit_any_miss(self) -> None:
        """ANY 模式：未命中"""
        truth = RetrievalTruth(
            mode="ANY",
            sources=[EvalSource(book="必修第一册", page_start=10, page_end=20)],
        )
        results = [("必修第二册", 15)]
        assert truth.check_hit(results) is False

    def test_check_hit_all_all_hit(self) -> None:
        """ALL 模式：全部命中"""
        truth = RetrievalTruth(
            mode="ALL",
            sources=[
                EvalSource(book="必修第一册", page_start=10, page_end=20),
                EvalSource(book="必修第二册", page_start=30, page_end=40),
            ],
        )
        results = [("必修第一册", 15), ("必修第二册", 35)]
        assert truth.check_hit(results) is True

    def test_check_hit_all_partial_hit(self) -> None:
        """ALL 模式：部分命中"""
        truth = RetrievalTruth(
            mode="ALL",
            sources=[
                EvalSource(book="必修第一册", page_start=10, page_end=20),
                EvalSource(book="必修第二册", page_start=30, page_end=40),
            ],
        )
        results = [("必修第一册", 15), ("必修第三册", 35)]
        assert truth.check_hit(results) is False

    def test_check_hit_empty_results(self) -> None:
        """空结果列表"""
        truth = RetrievalTruth(
            mode="ANY",
            sources=[EvalSource(book="必修第一册", page_start=10, page_end=20)],
        )
        assert truth.check_hit([]) is False

    def test_roundtrip(self) -> None:
        """to_dict → from_dict 往返"""
        original = RetrievalTruth(
            mode="ALL",
            sources=[
                EvalSource(book="test1", page_start=1, page_end=10),
                EvalSource(book="test2", page_start=20, page_end=30),
            ],
        )
        restored = RetrievalTruth.from_dict(original.to_dict())
        assert restored.mode == original.mode
        assert len(restored.sources) == len(original.sources)


# ============================================================================
# EvalItem 测试
# ============================================================================


class TestEvalItem:
    """EvalItem 数据模型测试"""

    def test_construct_normal(self) -> None:
        """正常构造"""
        truth = RetrievalTruth(
            mode="ANY",
            sources=[EvalSource(book="test", page_start=1, page_end=5)],
        )
        item = EvalItem(id="q001", question="什么是集合？", retrieval_truth=truth)
        assert item.id == "q001"
        assert item.question == "什么是集合？"

    def test_from_dict_normal(self) -> None:
        """from_dict 正常解析"""
        data = {
            "id": "q001",
            "question": "什么是函数？",
            "retrieval_truth": {
                "mode": "ANY",
                "sources": [{"book": "必修第一册", "page_start": 43, "page_end": 55}],
            },
        }
        item = EvalItem.from_dict(data)
        assert item.id == "q001"
        assert item.question == "什么是函数？"
        assert item.retrieval_truth.mode == "ANY"

    def test_from_dict_empty_id(self) -> None:
        """from_dict id 为空"""
        data = {
            "id": "",
            "question": "test",
            "retrieval_truth": {"mode": "ANY", "sources": [{"book": "a", "page_start": 1, "page_end": 5}]},
        }
        with pytest.raises(ValueError, match="id"):
            EvalItem.from_dict(data)

    def test_from_dict_empty_question(self) -> None:
        """from_dict question 为空"""
        data = {
            "id": "q001",
            "question": "",
            "retrieval_truth": {"mode": "ANY", "sources": [{"book": "a", "page_start": 1, "page_end": 5}]},
        }
        with pytest.raises(ValueError, match="question"):
            EvalItem.from_dict(data)

    def test_from_dict_missing_truth(self) -> None:
        """from_dict 缺少 retrieval_truth"""
        data = {"id": "q001", "question": "test"}
        with pytest.raises(ValueError, match="retrieval_truth"):
            EvalItem.from_dict(data)

    def test_to_dict(self) -> None:
        """to_dict 序列化"""
        truth = RetrievalTruth(
            mode="ANY",
            sources=[EvalSource(book="test", page_start=1, page_end=5)],
        )
        item = EvalItem(id="q001", question="test", retrieval_truth=truth)
        d = item.to_dict()
        assert d["id"] == "q001"
        assert d["question"] == "test"
        assert d["retrieval_truth"]["mode"] == "ANY"

    def test_roundtrip(self) -> None:
        """to_dict → from_dict 往返"""
        truth = RetrievalTruth(
            mode="ALL",
            sources=[
                EvalSource(book="test1", page_start=1, page_end=10),
                EvalSource(book="test2", page_start=20, page_end=30),
            ],
        )
        original = EvalItem(id="q099", question="test question", retrieval_truth=truth)
        restored = EvalItem.from_dict(original.to_dict())
        assert restored.id == original.id
        assert restored.question == original.question
        assert restored.retrieval_truth.mode == original.retrieval_truth.mode
        assert len(restored.retrieval_truth.sources) == len(original.retrieval_truth.sources)


# ============================================================================
# EvalSetLoader 测试
# ============================================================================


class TestEvalSetLoader:
    """EvalSetLoader 加载和验证测试"""

    def _make_eval_json(self, tmpdir: str, data: list[dict]) -> str:
        """辅助：写入评估集 JSON 到临时目录"""
        filepath = os.path.join(tmpdir, "eval_set.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return tmpdir

    def _sample_items(self) -> list[dict]:
        """辅助：生成样本评估数据"""
        return [
            {
                "id": "q001",
                "question": "什么是集合？",
                "retrieval_truth": {
                    "mode": "ANY",
                    "sources": [{"book": "必修第一册", "page_start": 1, "page_end": 8}],
                },
            },
            {
                "id": "q002",
                "question": "什么是函数？",
                "retrieval_truth": {
                    "mode": "ANY",
                    "sources": [{"book": "必修第一册", "page_start": 43, "page_end": 55}],
                },
            },
        ]

    def test_load_normal(self) -> None:
        """正常加载"""
        with tempfile.TemporaryDirectory() as tmpdir:
            self._make_eval_json(tmpdir, self._sample_items())
            loader = EvalSetLoader(eval_dir=tmpdir)
            items = loader.load()
            assert len(items) == 2
            assert items[0].id == "q001"
            assert items[1].id == "q002"

    def test_load_file_not_found(self) -> None:
        """文件不存在"""
        loader = EvalSetLoader(eval_dir="/nonexistent")
        with pytest.raises(FileNotFoundError):
            loader.load()

    def test_load_invalid_json(self) -> None:
        """JSON 格式错误"""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "eval_set.json")
            with open(filepath, "w") as f:
                f.write("not valid json {{{")
            loader = EvalSetLoader(eval_dir=tmpdir)
            with pytest.raises(ValueError, match="JSON"):
                loader.load()

    def test_load_non_array_root(self) -> None:
        """根元素不是数组"""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "eval_set.json")
            with open(filepath, "w") as f:
                json.dump({"not": "array"}, f)
            loader = EvalSetLoader(eval_dir=tmpdir)
            with pytest.raises(ValueError, match="数组"):
                loader.load()

    def test_load_empty_array(self) -> None:
        """空数组"""
        with tempfile.TemporaryDirectory() as tmpdir:
            self._make_eval_json(tmpdir, [])
            loader = EvalSetLoader(eval_dir=tmpdir)
            with pytest.raises(ValueError, match="为空"):
                loader.load()

    def test_load_invalid_item(self) -> None:
        """条目数据格式错误"""
        with tempfile.TemporaryDirectory() as tmpdir:
            data = [
                {"id": "q001", "question": "test", "retrieval_truth": {"mode": "ANY", "sources": [{"book": "a", "page_start": 1, "page_end": 5}]}},
                {"id": "", "question": "bad item"},  # id 为空
            ]
            self._make_eval_json(tmpdir, data)
            loader = EvalSetLoader(eval_dir=tmpdir)
            with pytest.raises(ValueError, match="解析错误"):
                loader.load()

    def test_load_non_dict_item(self) -> None:
        """条目不是 JSON 对象"""
        with tempfile.TemporaryDirectory() as tmpdir:
            self._make_eval_json(tmpdir, ["not a dict"])
            loader = EvalSetLoader(eval_dir=tmpdir)
            with pytest.raises(ValueError, match="不是 JSON 对象"):
                loader.load()

    def test_validate_normal(self) -> None:
        """正常验证"""
        loader = EvalSetLoader(eval_dir="/tmp")
        items = [
            EvalItem(
                id="q001",
                question="test1",
                retrieval_truth=RetrievalTruth(
                    mode="ANY",
                    sources=[EvalSource(book="必修第一册", page_start=1, page_end=10)],
                ),
            ),
            EvalItem(
                id="q002",
                question="test2",
                retrieval_truth=RetrievalTruth(
                    mode="ALL",
                    sources=[
                        EvalSource(book="必修第二册", page_start=1, page_end=10),
                        EvalSource(book="必修第二册", page_start=20, page_end=30),
                    ],
                ),
            ),
        ]
        validation = loader.validate(items)
        assert validation.passed is True
        assert validation.total_items == 2
        assert validation.unique_ids is True
        assert "必修第一册" in validation.books_covered
        assert "必修第二册" in validation.books_covered
        assert len(validation.errors) == 0

    def test_validate_duplicate_ids(self) -> None:
        """ID 重复"""
        loader = EvalSetLoader(eval_dir="/tmp")
        items = [
            EvalItem(
                id="q001",
                question="test1",
                retrieval_truth=RetrievalTruth(
                    mode="ANY",
                    sources=[EvalSource(book="test", page_start=1, page_end=5)],
                ),
            ),
            EvalItem(
                id="q001",
                question="test2",
                retrieval_truth=RetrievalTruth(
                    mode="ANY",
                    sources=[EvalSource(book="test", page_start=6, page_end=10)],
                ),
            ),
        ]
        validation = loader.validate(items)
        assert validation.passed is False
        assert validation.unique_ids is False
        assert any("不唯一" in e for e in validation.errors)

    def test_validate_min_per_book_warning(self) -> None:
        """每本书条目不足时产生警告"""
        loader = EvalSetLoader(eval_dir="/tmp")
        items = [
            EvalItem(
                id="q001",
                question="test",
                retrieval_truth=RetrievalTruth(
                    mode="ANY",
                    sources=[EvalSource(book="test_book", page_start=1, page_end=5)],
                ),
            ),
        ]
        validation = loader.validate(items, min_per_book=3)
        assert validation.passed is True  # 警告不影响 passed
        assert len(validation.warnings) > 0

    def test_validate_empty_items(self) -> None:
        """空列表验证"""
        loader = EvalSetLoader(eval_dir="/tmp")
        validation = loader.validate([])
        assert validation.passed is True
        assert validation.total_items == 0
        assert validation.min_items_per_book == 0


# ============================================================================
# 真实评估集文件测试
# ============================================================================


class TestRealEvalSet:
    """加载真实 eval_set.json 并验证格式"""

    def test_load_real_eval_set(self) -> None:
        """加载 data/evaluation/eval_set.json"""
        eval_dir = os.path.join(
            os.path.dirname(__file__), "..", "data", "evaluation"
        )
        if not os.path.exists(os.path.join(eval_dir, "eval_set.json")):
            pytest.skip("eval_set.json 不存在（尚未构建）")

        loader = EvalSetLoader(eval_dir=eval_dir)
        items = loader.load("eval_set.json")

        # 至少有 20 条
        assert len(items) >= 20

    def test_real_eval_set_format(self) -> None:
        """验证 eval_set.json 数据格式"""
        eval_dir = os.path.join(
            os.path.dirname(__file__), "..", "data", "evaluation"
        )
        if not os.path.exists(os.path.join(eval_dir, "eval_set.json")):
            pytest.skip("eval_set.json 不存在（尚未构建）")

        loader = EvalSetLoader(eval_dir=eval_dir)
        items = loader.load("eval_set.json")

        # 验证格式
        for item in items:
            assert isinstance(item.id, str) and item.id.startswith("q")
            assert isinstance(item.question, str) and len(item.question) > 0
            assert item.retrieval_truth.mode in ("ANY", "ALL", "NEGATIVE")
            if item.retrieval_truth.mode == "NEGATIVE":
                assert len(item.retrieval_truth.sources) == 0
                continue
            assert len(item.retrieval_truth.sources) > 0
            for source in item.retrieval_truth.sources:
                assert isinstance(source.book, str) and len(source.book) > 0
                assert isinstance(source.page_start, int) and source.page_start >= 1
                assert isinstance(source.page_end, int) and source.page_end >= source.page_start

    def test_real_eval_set_coverage(self) -> None:
        """验证 eval_set.json 覆盖度"""
        eval_dir = os.path.join(
            os.path.dirname(__file__), "..", "data", "evaluation"
        )
        if not os.path.exists(os.path.join(eval_dir, "eval_set.json")):
            pytest.skip("eval_set.json 不存在（尚未构建）")

        loader = EvalSetLoader(eval_dir=eval_dir)
        items = loader.load("eval_set.json")
        validation = loader.validate(items, min_per_book=3)

        # 应覆盖 5 本书
        expected_books = {
            "必修第一册",
            "必修第二册",
            "选择性必修第一册",
            "选择性必修第二册",
            "选择性必修第三册",
        }
        assert validation.books_covered == expected_books
        assert validation.passed is True
        assert validation.unique_ids is True

    def test_real_eval_set_unique_ids(self) -> None:
        """验证 eval_set.json ID 唯一"""
        eval_dir = os.path.join(
            os.path.dirname(__file__), "..", "data", "evaluation"
        )
        if not os.path.exists(os.path.join(eval_dir, "eval_set.json")):
            pytest.skip("eval_set.json 不存在（尚未构建）")

        loader = EvalSetLoader(eval_dir=eval_dir)
        items = loader.load("eval_set.json")
        ids = [item.id for item in items]
        assert len(ids) == len(set(ids)), f"ID 不唯一: {ids}"

    def test_real_eval_set_any_all_modes(self) -> None:
        """验证 eval_set.json 中 ANY 和 ALL 模式都存在"""
        eval_dir = os.path.join(
            os.path.dirname(__file__), "..", "data", "evaluation"
        )
        if not os.path.exists(os.path.join(eval_dir, "eval_set.json")):
            pytest.skip("eval_set.json 不存在（尚未构建）")

        loader = EvalSetLoader(eval_dir=eval_dir)
        items = loader.load("eval_set.json")
        modes = {item.retrieval_truth.mode for item in items}
        assert "ANY" in modes
        assert "ALL" in modes
