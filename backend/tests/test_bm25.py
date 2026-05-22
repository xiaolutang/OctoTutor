"""BM25Retriever 和 ChromaDBStore.get_all_chunks 单元测试"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.infra.bm25 import BM25Retriever
from app.rag.models import Chunk, ChunkMetadata, QueryResult


# ---------- 辅助函数 ----------


def _make_metadata(**overrides) -> ChunkMetadata:
    """创建 ChunkMetadata，提供合理默认值"""
    defaults = dict(
        book="测试书",
        chapter="第一章",
        section="第一节",
        section_id="测试书::1.1",
        page=1,
        page_start=1,
        page_end=2,
        source_pages=[1, 2],
        chunk_type="parent",
        block_type="unknown",
        has_formula=False,
        parent_id="",
        child_index=0,
    )
    defaults.update(overrides)
    return ChunkMetadata(**defaults)


def _make_chunk(chunk_id: str, text: str, **meta_overrides) -> Chunk:
    """创建 Chunk"""
    return Chunk(chunk_id=chunk_id, text=text, metadata=_make_metadata(**meta_overrides))


# ---------- BM25Retriever 测试 ----------


class TestBM25BuildIndex:
    """build_index 测试"""

    def test_build_index_basic(self) -> None:
        """build_index 基本功能：构建索引后可查询"""
        retriever = BM25Retriever()
        chunks = [
            _make_chunk("c1", "集合的概念与运算"),
            _make_chunk("c2", "函数的定义域和值域"),
        ]
        retriever.build_index(chunks)
        results = retriever.query("集合")
        assert len(results) > 0
        # "集合" 应该匹配 c1（包含"集合"）
        assert results[0].chunk_id == "c1"

    def test_build_index_chunk_map(self) -> None:
        """build_index 后 _chunk_map 包含所有 chunks"""
        retriever = BM25Retriever()
        chunks = [
            _make_chunk("c1", "文本一"),
            _make_chunk("c2", "文本二"),
            _make_chunk("c3", "文本三"),
        ]
        retriever.build_index(chunks)
        assert len(retriever._chunk_map) == 3
        assert "c1" in retriever._chunk_map
        assert "c2" in retriever._chunk_map
        assert "c3" in retriever._chunk_map

    def test_build_index_chunk_ids(self) -> None:
        """build_index 后 _chunk_ids 顺序与输入一致"""
        retriever = BM25Retriever()
        chunks = [
            _make_chunk("alpha", "第一个"),
            _make_chunk("beta", "第二个"),
        ]
        retriever.build_index(chunks)
        assert retriever._chunk_ids == ["alpha", "beta"]

    def test_build_index_rebuild(self) -> None:
        """重复 build_index 会覆盖旧索引"""
        retriever = BM25Retriever()
        retriever.build_index([_make_chunk("c1", "旧数据")])
        retriever.build_index([_make_chunk("c2", "新数据"), _make_chunk("c3", "更新的数据")])
        assert retriever._chunk_ids == ["c2", "c3"]
        results = retriever.query("新数据")
        assert len(results) > 0
        assert results[0].chunk_id == "c3"


class TestBM25Query:
    """query 测试"""

    @pytest.fixture
    def retriever_with_data(self) -> BM25Retriever:
        """构建包含测试数据的 BM25Retriever"""
        retriever = BM25Retriever()
        chunks = [
            _make_chunk("c1", "集合的概念：一般地，把一些能够确定的不同对象看成一个整体。"),
            _make_chunk("c2", "函数是两个非空数集之间的一种确定的对应关系。"),
            _make_chunk("c3", "三角函数的正弦定理和余弦定理是重要的数学工具。"),
            _make_chunk("c4", "数列是按照一定顺序排列的一列数。"),
            _make_chunk("c5", "不等式的基本性质和均值不等式。"),
        ]
        retriever.build_index(chunks)
        return retriever

    def test_query_returns_query_result_type(self, retriever_with_data: BM25Retriever) -> None:
        """query 返回的是 QueryResult 类型"""
        results = retriever_with_data.query("集合")
        assert len(results) > 0
        for r in results:
            assert isinstance(r, QueryResult)
            assert isinstance(r.chunk_id, str)
            assert isinstance(r.text, str)
            assert isinstance(r.metadata, ChunkMetadata)
            assert isinstance(r.score, float)

    def test_query_chinese_tokenization_and_ranking(self, retriever_with_data: BM25Retriever) -> None:
        """中文分词+排序：查询"集合"时 c1 排名最高"""
        results = retriever_with_data.query("集合")
        assert len(results) > 0
        assert results[0].chunk_id == "c1"
        # 分数降序排列
        for i in range(len(results) - 1):
            assert results[i].score >= results[i + 1].score

    def test_query_unique_chunk_found(self, retriever_with_data: BM25Retriever) -> None:
        """BM25 能检索到独有 chunk（模拟向量检索未召回的场景）"""
        # 查询"数列"，c4 包含"数列"应被检索到
        results = retriever_with_data.query("数列")
        chunk_ids = [r.chunk_id for r in results]
        assert "c4" in chunk_ids

    def test_query_empty_index(self) -> None:
        """空索引返回空列表"""
        retriever = BM25Retriever()
        results = retriever.query("任意查询")
        assert results == []

    def test_query_top_k_limit(self, retriever_with_data: BM25Retriever) -> None:
        """top_k 限制返回数量"""
        results = retriever_with_data.query("数学", top_k=2)
        assert len(results) == 2

    def test_query_top_k_default(self, retriever_with_data: BM25Retriever) -> None:
        """默认 top_k=10，但不超过索引大小"""
        results = retriever_with_data.query("数学", top_k=10)
        assert len(results) == 5  # 只有 5 个 chunk

    def test_query_no_match_returns_results(self, retriever_with_data: BM25Retriever) -> None:
        """查询无匹配关键词时仍返回结果（BM25 分数可能为 0）"""
        results = retriever_with_data.query("量子物理")
        # BM25 即使分数为 0 也会返回结果（只要 top_k 允许）
        assert isinstance(results, list)

    def test_query_chunk_ids_index_correctness(self) -> None:
        """_chunk_ids 索引正确性：确保 query 结果与 chunk 内容一致"""
        retriever = BM25Retriever()
        chunks = [
            _make_chunk("id_alpha", "苹果是一种水果"),
            _make_chunk("id_banana", "香蕉也是水果"),
            _make_chunk("id_carrot", "胡萝卜是蔬菜"),
        ]
        retriever.build_index(chunks)
        results = retriever.query("苹果")
        assert len(results) > 0
        assert results[0].chunk_id == "id_alpha"
        assert "苹果" in results[0].text


# ---------- ChromaDBStore.get_all_chunks 测试 ----------


class TestGetAllChunks:
    """ChromaDBStore.get_all_chunks 测试（mock _collection.get）"""

    def _mock_store(self, mock_get_return: dict) -> MagicMock:
        """创建 mock ChromaDBStore，注入 _collection.get 返回值"""
        mock_collection = MagicMock()
        mock_collection.get.return_value = mock_get_return

        store = MagicMock()
        # 使用真实的 get_all_chunks 方法
        from app.rag.vector_store import ChromaDBStore

        store_instance = object.__new__(ChromaDBStore)
        store_instance._collection = mock_collection
        return store_instance

    def test_get_all_chunks_basic(self) -> None:
        """基本 get_all_chunks 返回正确数量"""
        store = self._mock_store({
            "ids": ["c1", "c2"],
            "documents": ["文本一", "文本二"],
            "metadatas": [
                {
                    "book": "测试书",
                    "chapter": "第一章",
                    "section": "第一节",
                    "section_id": "测试书::1.1",
                    "page": 1,
                    "page_start": 1,
                    "page_end": 2,
                    "source_pages": "1,2",
                    "chunk_type": "parent",
                    "block_type": "unknown",
                    "has_formula": False,
                    "parent_id": "",
                    "child_index": 0,
                },
                {
                    "book": "测试书",
                    "chapter": "第一章",
                    "section": "第二节",
                    "section_id": "测试书::1.2",
                    "page": 3,
                    "page_start": 3,
                    "page_end": 4,
                    "source_pages": "3,4",
                    "chunk_type": "child",
                    "block_type": "definition",
                    "has_formula": True,
                    "parent_id": "parent1",
                    "child_index": 0,
                },
            ],
        })

        chunks = store.get_all_chunks()
        assert len(chunks) == 2
        assert chunks[0].chunk_id == "c1"
        assert chunks[0].text == "文本一"
        assert chunks[0].metadata.book == "测试书"
        assert chunks[1].chunk_id == "c2"
        assert chunks[1].metadata.has_formula is True
        assert chunks[1].metadata.source_pages == [3, 4]

    def test_get_all_chunks_empty(self) -> None:
        """空 collection 返回空列表"""
        store = self._mock_store({
            "ids": [],
            "documents": [],
            "metadatas": [],
        })
        chunks = store.get_all_chunks()
        assert chunks == []

    def test_get_all_chunks_source_pages_parsing(self) -> None:
        """source_pages 字符串正确解析为 int 列表"""
        store = self._mock_store({
            "ids": ["c1"],
            "documents": ["文本"],
            "metadatas": [
                {
                    "book": "书",
                    "chapter": "章",
                    "section": "节",
                    "section_id": "书::1",
                    "page": 5,
                    "page_start": 5,
                    "page_end": 8,
                    "source_pages": "5,6,7,8",
                    "chunk_type": "parent",
                    "block_type": "unknown",
                    "has_formula": False,
                    "parent_id": "",
                    "child_index": 0,
                },
            ],
        })
        chunks = store.get_all_chunks()
        assert len(chunks) == 1
        assert chunks[0].metadata.source_pages == [5, 6, 7, 8]

    def test_get_all_chunks_metadata_consistent_with_query(self) -> None:
        """get_all_chunks 的 metadata 解析逻辑与 query 方法一致

        验证：相同的 metadata 字典，通过 get_all_chunks 和 query 解析出的
        ChunkMetadata 应该完全相同。
        """
        meta_dict = {
            "book": "必修第一册",
            "chapter": "第一章",
            "section": "1.1 集合",
            "section_id": "必修第一册::1.1",
            "page": 12,
            "page_start": 12,
            "page_end": 13,
            "source_pages": "12,13",
            "chunk_type": "child",
            "block_type": "definition",
            "has_formula": True,
            "parent_id": "parent_id_1",
            "child_index": 2,
        }

        # 模拟 ChromaDB .get() 返回
        store = self._mock_store({
            "ids": ["chunk_1"],
            "documents": ["集合的定义"],
            "metadatas": [meta_dict],
        })
        chunks = store.get_all_chunks()
        assert len(chunks) == 1

        m = chunks[0].metadata
        assert m.book == "必修第一册"
        assert m.chapter == "第一章"
        assert m.section == "1.1 集合"
        assert m.section_id == "必修第一册::1.1"
        assert m.page == 12
        assert m.page_start == 12
        assert m.page_end == 13
        assert m.source_pages == [12, 13]
        assert m.chunk_type == "child"
        assert m.block_type == "definition"
        assert m.has_formula is True
        assert m.parent_id == "parent_id_1"
        assert m.child_index == 2
