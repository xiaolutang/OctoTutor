"""EvalItem 向后兼容与往返一致性测试

覆盖场景：
1. 旧数据（无新字段）仍可正常构造
2. 新字段有正确默认值
3. to_dict / from_dict 往返一致
4. 部分新字段提供、部分省略
"""

from __future__ import annotations

import pytest

from app.evaluation.eval_types import EvalItem, RetrievalTruth, EvalSource


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _base_truth() -> RetrievalTruth:
    return RetrievalTruth(
        mode="ANY",
        sources=[EvalSource(book="必修第一册", page_start=1, page_end=10)],
    )


def _base_item(**overrides) -> EvalItem:
    kwargs = dict(
        id="q001",
        question="什么是函数？",
        retrieval_truth=_base_truth(),
    )
    kwargs.update(overrides)
    return EvalItem(**kwargs)


# ---------------------------------------------------------------------------
# 测试：旧数据兼容（不含新字段）
# ---------------------------------------------------------------------------

class TestBackwardCompat:
    """旧格式数据（不含 key_facts / reference_answer / suite）仍可正常加载"""

    def test_old_dict_loads_ok(self) -> None:
        """缺少新字段时 from_dict 不报错"""
        old_data = {
            "id": "q001",
            "question": "什么是函数？",
            "retrieval_truth": {
                "mode": "ANY",
                "sources": [{"book": "必修第一册", "page_start": 1, "page_end": 10}],
            },
        }
        item = EvalItem.from_dict(old_data)
        assert item.id == "q001"
        assert item.key_facts == []
        assert item.reference_answer == ""
        assert item.suite == "regression"

    def test_construct_without_new_fields(self) -> None:
        """只传必填字段时新字段使用默认值"""
        item = _base_item()
        assert item.key_facts == []
        assert item.reference_answer == ""
        assert item.suite == "regression"


# ---------------------------------------------------------------------------
# 测试：新字段赋值
# ---------------------------------------------------------------------------

class TestNewFields:
    """新字段正确赋值和读取"""

    def test_key_facts(self) -> None:
        item = _base_item(key_facts=["函数定义", "定义域"])
        assert item.key_facts == ["函数定义", "定义域"]

    def test_reference_answer(self) -> None:
        item = _base_item(reference_answer="函数是一种映射关系")
        assert item.reference_answer == "函数是一种映射关系"

    def test_suite(self) -> None:
        item = _base_item(suite="smoke")
        assert item.suite == "smoke"

    def test_all_new_fields(self) -> None:
        item = _base_item(
            key_facts=["a", "b"],
            reference_answer="ref",
            suite="custom",
        )
        assert item.key_facts == ["a", "b"]
        assert item.reference_answer == "ref"
        assert item.suite == "custom"


# ---------------------------------------------------------------------------
# 测试：to_dict / from_dict 往返一致性
# ---------------------------------------------------------------------------

class TestRoundTrip:
    """to_dict → from_dict → to_dict 一致"""

    def test_roundtrip_minimal(self) -> None:
        """只填必填字段，往返一致"""
        item = _base_item()
        d = item.to_dict()
        item2 = EvalItem.from_dict(d)
        assert item2.to_dict() == d

    def test_roundtrip_full(self) -> None:
        """填满所有字段，往返一致"""
        item = _base_item(
            key_facts=["x", "y"],
            reference_answer="answer",
            suite="smoke",
        )
        d = item.to_dict()
        item2 = EvalItem.from_dict(d)
        assert item2.to_dict() == d
        assert item2.key_facts == ["x", "y"]
        assert item2.reference_answer == "answer"
        assert item2.suite == "smoke"

    def test_roundtrip_old_data_new_dict(self) -> None:
        """旧格式数据加载后再序列化，包含新字段默认值"""
        old_data = {
            "id": "q001",
            "question": "test",
            "retrieval_truth": {
                "mode": "ANY",
                "sources": [{"book": "书A", "page_start": 1, "page_end": 5}],
            },
        }
        item = EvalItem.from_dict(old_data)
        d = item.to_dict()
        assert "key_facts" in d
        assert "reference_answer" in d
        assert "suite" in d
        # 再从 dict 加载，仍然一致
        item2 = EvalItem.from_dict(d)
        assert item2.to_dict() == d

    def test_from_dict_partial_new_fields(self) -> None:
        """部分提供新字段"""
        data = {
            "id": "q001",
            "question": "test",
            "retrieval_truth": {
                "mode": "ANY",
                "sources": [{"book": "书A", "page_start": 1, "page_end": 5}],
            },
            "suite": "custom",
            # key_facts 和 reference_answer 未提供
        }
        item = EvalItem.from_dict(data)
        assert item.suite == "custom"
        assert item.key_facts == []
        assert item.reference_answer == ""


# ---------------------------------------------------------------------------
# 测试：现有验证逻辑未被破坏
# ---------------------------------------------------------------------------

class TestExistingValidation:
    """确保原有的 id / question / retrieval_truth 校验仍然生效"""

    def test_empty_id_raises(self) -> None:
        with pytest.raises(ValueError, match="id"):
            EvalItem.from_dict({
                "id": "",
                "question": "q",
                "retrieval_truth": {
                    "mode": "ANY",
                    "sources": [{"book": "书A", "page_start": 1, "page_end": 5}],
                },
            })

    def test_empty_question_raises(self) -> None:
        with pytest.raises(ValueError, match="question"):
            EvalItem.from_dict({
                "id": "q001",
                "question": "",
                "retrieval_truth": {
                    "mode": "ANY",
                    "sources": [{"book": "书A", "page_start": 1, "page_end": 5}],
                },
            })

    def test_missing_truth_raises(self) -> None:
        with pytest.raises(ValueError, match="retrieval_truth"):
            EvalItem.from_dict({
                "id": "q001",
                "question": "test",
            })
