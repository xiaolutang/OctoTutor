"""VectorStore 和 ChromaDBStore 单元测试

使用临时目录隔离测试数据，避免污染生产环境。
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from app.rag.models import Chunk, ChunkMetadata, QueryResult
from app.rag.vector_store import ChromaDBStore, VectorStore


# ---------- fixtures ----------


def _make_metadata(**overrides) -> ChunkMetadata:
    """创建 ChunkMetadata，提供合理默认值"""
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
    return ChunkMetadata(**defaults)


def _make_chunk(chunk_id: str, text: str, **meta_overrides) -> Chunk:
    """创建 Chunk"""
    return Chunk(chunk_id=chunk_id, text=text, metadata=_make_metadata(**meta_overrides))


def _make_embedding(seed: int, dim: int = 8) -> list[float]:
    """生成确定性伪 embedding 向量（用于测试，非真实 embedding）"""
    import math

    return [math.sin(seed + i * 0.1) * 0.5 for i in range(dim)]


@pytest.fixture
def store(tmp_path: Path) -> ChromaDBStore:
    """创建使用临时目录的 ChromaDBStore"""
    return ChromaDBStore(
        persist_directory=str(tmp_path / "chroma_db"),
        collection_name="test_chunks",
    )


@pytest.fixture
def sample_chunks() -> list[Chunk]:
    """创建测试用 chunks"""
    return [
        _make_chunk(
            "必修第一册::1.1集合::p12_s0::parent",
            "集合的概念：一般地，把一些能够确定的不同对象看成一个整体，就说这个整体是由这些对象的全体构成的集合。",
            chunk_type="parent",
            child_index=0,
        ),
        _make_chunk(
            "必修第一册::1.1集合::p12_s0::child::0",
            "集合的概念：一般地，把一些能够确定的不同对象看成一个整体。",
            child_index=0,
        ),
        _make_chunk(
            "必修第一册::1.1集合::p12_s0::child::1",
            "集合中的每个对象叫做这个集合的元素。",
            child_index=1,
        ),
        _make_chunk(
            "必修第一册::1.1集合::p13_s1::child::0",
            "二次函数 $f(x)=ax^2+bx+c$ 的顶点坐标公式。",
            page=13,
            has_formula=True,
            child_index=0,
        ),
    ]


@pytest.fixture
def sample_embeddings() -> list[list[float]]:
    """创建与 sample_chunks 对应的 embedding 向量"""
    return [_make_embedding(i) for i in range(4)]


# ---------- Protocol 验证 ----------


class TestVectorStoreProtocol:
    """验证 ChromaDBStore 实现了 VectorStore Protocol"""

    def test_implements_protocol(self, store: ChromaDBStore) -> None:
        assert isinstance(store, VectorStore)

    def test_has_upsert(self, store: ChromaDBStore) -> None:
        assert callable(getattr(store, "upsert", None))

    def test_has_query(self, store: ChromaDBStore) -> None:
        assert callable(getattr(store, "query", None))

    def test_has_delete(self, store: ChromaDBStore) -> None:
        assert callable(getattr(store, "delete", None))


# ---------- Upsert 测试 ----------


class TestUpsert:
    """upsert 操作测试"""

    def test_upsert_basic(self, store: ChromaDBStore) -> None:
        """基本 upsert 操作"""
        chunks = [_make_chunk("id1", "hello world")]
        embeddings = [_make_embedding(0)]
        store.upsert(chunks, embeddings)
        assert store.count() == 1

    def test_upsert_multiple(self, store: ChromaDBStore) -> None:
        """批量 upsert"""
        chunks = [
            _make_chunk("id1", "text 1"),
            _make_chunk("id2", "text 2"),
            _make_chunk("id3", "text 3"),
        ]
        embeddings = [_make_embedding(i) for i in range(3)]
        store.upsert(chunks, embeddings)
        assert store.count() == 3

    def test_upsert_empty(self, store: ChromaDBStore) -> None:
        """空列表 upsert 不报错"""
        store.upsert([], [])
        assert store.count() == 0

    def test_upsert_length_mismatch(self, store: ChromaDBStore) -> None:
        """chunks 和 embeddings 长度不一致时抛出 ValueError"""
        chunks = [_make_chunk("id1", "text")]
        embeddings = [[1.0, 2.0], [3.0, 4.0]]  # 比 chunks 多
        with pytest.raises(ValueError, match="长度不一致"):
            store.upsert(chunks, embeddings)

    def test_upsert_idempotent(self, store: ChromaDBStore) -> None:
        """相同 ID 重复 upsert 是幂等的"""
        chunks = [_make_chunk("id1", "text version 1")]
        embeddings = [_make_embedding(0)]
        store.upsert(chunks, embeddings)

        # 用相同 ID 更新
        chunks2 = [_make_chunk("id1", "text version 2")]
        embeddings2 = [_make_embedding(1)]
        store.upsert(chunks2, embeddings2)

        assert store.count() == 1

    def test_upsert_full_metadata(self, store: ChromaDBStore) -> None:
        """upsert 保留完整 metadata"""
        chunk = _make_chunk(
            "test::id",
            "content",
            book="必修第二册",
            chapter="第二章",
            section="2.1",
            page=20,
            chunk_type="parent",
            has_formula=True,
            parent_id="test::parent",
            child_index=0,
        )
        store.upsert([chunk], [_make_embedding(0)])

        results = store.query(_make_embedding(0), top_k=1)
        assert len(results) == 1
        assert results[0].metadata.book == "必修第二册"
        assert results[0].metadata.page == 20
        assert results[0].metadata.has_formula is True
        assert results[0].metadata.chunk_type == "parent"


# ---------- Query 测试 ----------


class TestQuery:
    """query 操作测试"""

    def test_query_basic(
        self, store: ChromaDBStore, sample_chunks: list[Chunk], sample_embeddings: list[list[float]]
    ) -> None:
        """基本 query 返回正确结果"""
        store.upsert(sample_chunks, sample_embeddings)

        # 用与 chunk 0 相同的 embedding 查询
        results = store.query(sample_embeddings[0], top_k=2)
        assert len(results) == 2
        # 第一个结果应该是最相似的（自己）
        assert results[0].chunk_id == "必修第一册::1.1集合::p12_s0::parent"

    def test_query_returns_query_result(
        self, store: ChromaDBStore, sample_chunks: list[Chunk], sample_embeddings: list[list[float]]
    ) -> None:
        """query 返回 QueryResult 对象"""
        store.upsert(sample_chunks, sample_embeddings)
        results = store.query(sample_embeddings[0], top_k=1)
        assert len(results) == 1
        r = results[0]
        assert isinstance(r, QueryResult)
        assert isinstance(r.chunk_id, str)
        assert isinstance(r.text, str)
        assert isinstance(r.metadata, ChunkMetadata)
        assert isinstance(r.score, float)

    def test_query_score_range(
        self, store: ChromaDBStore, sample_chunks: list[Chunk], sample_embeddings: list[list[float]]
    ) -> None:
        """query score 为 float 且计算正确（score = 1 - cosine_distance）"""
        store.upsert(sample_chunks, sample_embeddings)
        results = store.query(sample_embeddings[0], top_k=4)
        assert len(results) > 0
        for r in results:
            assert isinstance(r.score, float)
        # 第一个结果（自己）应该 score 最高
        assert results[0].score >= results[-1].score

    def test_query_top_k(
        self, store: ChromaDBStore, sample_chunks: list[Chunk], sample_embeddings: list[list[float]]
    ) -> None:
        """top_k 限制返回数量"""
        store.upsert(sample_chunks, sample_embeddings)
        results = store.query(sample_embeddings[0], top_k=2)
        assert len(results) == 2

    def test_query_top_k_more_than_total(
        self, store: ChromaDBStore, sample_chunks: list[Chunk], sample_embeddings: list[list[float]]
    ) -> None:
        """top_k 超过总数时返回全部"""
        store.upsert(sample_chunks, sample_embeddings)
        results = store.query(sample_embeddings[0], top_k=100)
        assert len(results) == len(sample_chunks)

    def test_query_empty_collection(self, store: ChromaDBStore) -> None:
        """空 collection query 返回空列表"""
        results = store.query(_make_embedding(0), top_k=5)
        assert results == []

    def test_query_where_book(
        self, store: ChromaDBStore, sample_chunks: list[Chunk], sample_embeddings: list[list[float]]
    ) -> None:
        """按 book 过滤"""
        store.upsert(sample_chunks, sample_embeddings)

        # 添加另一本书的数据
        other_chunks = [
            _make_chunk(
                "必修第二册::1.1::p1_s0::child::0",
                "其他书内容",
                book="必修第二册",
            )
        ]
        other_embeddings = [_make_embedding(10)]
        store.upsert(other_chunks, other_embeddings)

        results = store.query(sample_embeddings[0], top_k=10, where={"book": "必修第一册"})
        assert all(r.metadata.book == "必修第一册" for r in results)

    def test_query_where_chunk_type(
        self, store: ChromaDBStore, sample_chunks: list[Chunk], sample_embeddings: list[list[float]]
    ) -> None:
        """按 chunk_type 过滤"""
        store.upsert(sample_chunks, sample_embeddings)

        results = store.query(sample_embeddings[0], top_k=10, where={"chunk_type": "parent"})
        assert all(r.metadata.chunk_type == "parent" for r in results)

    def test_query_where_page(
        self, store: ChromaDBStore, sample_chunks: list[Chunk], sample_embeddings: list[list[float]]
    ) -> None:
        """按 page 过滤"""
        store.upsert(sample_chunks, sample_embeddings)

        results = store.query(sample_embeddings[0], top_k=10, where={"page": 13})
        assert len(results) >= 1
        assert all(r.metadata.page == 13 for r in results)

    def test_query_where_has_formula(
        self, store: ChromaDBStore, sample_chunks: list[Chunk], sample_embeddings: list[list[float]]
    ) -> None:
        """按 has_formula 过滤"""
        store.upsert(sample_chunks, sample_embeddings)

        results = store.query(sample_embeddings[0], top_k=10, where={"has_formula": True})
        assert all(r.metadata.has_formula is True for r in results)

    def test_query_where_combined(
        self, store: ChromaDBStore, sample_chunks: list[Chunk], sample_embeddings: list[list[float]]
    ) -> None:
        """组合 where 条件过滤"""
        store.upsert(sample_chunks, sample_embeddings)

        results = store.query(
            sample_embeddings[0],
            top_k=10,
            where={"$and": [{"book": "必修第一册"}, {"chunk_type": "child"}]},
        )
        assert all(
            r.metadata.book == "必修第一册" and r.metadata.chunk_type == "child"
            for r in results
        )


# ---------- Delete 测试 ----------


class TestDelete:
    """delete 操作测试"""

    def test_delete_by_book(
        self, store: ChromaDBStore, sample_chunks: list[Chunk], sample_embeddings: list[list[float]]
    ) -> None:
        """按 book 删除后 query 不再返回"""
        store.upsert(sample_chunks, sample_embeddings)
        initial_count = store.count()

        store.delete(where={"book": "必修第一册"})
        assert store.count() == 0

    def test_delete_by_chunk_type(
        self, store: ChromaDBStore, sample_chunks: list[Chunk], sample_embeddings: list[list[float]]
    ) -> None:
        """按 chunk_type 删除后只剩下另一种类型"""
        store.upsert(sample_chunks, sample_embeddings)

        store.delete(where={"chunk_type": "parent"})
        remaining = store.count()
        assert remaining == len(sample_chunks) - 1

    def test_delete_by_page(
        self, store: ChromoDBStore, sample_chunks: list[Chunk], sample_embeddings: list[list[float]]
    ) -> None:
        """按 page 删除后只剩其他页"""
        store.upsert(sample_chunks, sample_embeddings)

        store.delete(where={"page": 13})
        results = store.query(sample_embeddings[0], top_k=10)
        assert all(r.metadata.page != 13 for r in results)

    def test_delete_nonexistent_where(self, store: ChromaDBStore) -> None:
        """删除不存在的 where 条件不报错"""
        store.delete(where={"book": "不存在的书"})  # 不应抛异常


# ---------- 持久化测试 ----------


class TestPersistence:
    """PersistentClient 数据持久化测试"""

    def test_data_persists_after_restart(
        self, tmp_path: Path, sample_chunks: list[Chunk], sample_embeddings: list[list[float]]
    ) -> None:
        """重启客户端后数据仍在"""
        db_path = str(tmp_path / "chroma_persist")

        # 第一次写入
        store1 = ChromaDBStore(persist_directory=db_path, collection_name="test_persist")
        store1.upsert(sample_chunks, sample_embeddings)
        count1 = store1.count()
        assert count1 == len(sample_chunks)

        # 模拟重启：创建新实例指向同一目录
        store2 = ChromaDBStore(persist_directory=db_path, collection_name="test_persist")
        count2 = store2.count()
        assert count2 == count1

        # 验证可以 query 到数据
        results = store2.query(sample_embeddings[0], top_k=1)
        assert len(results) == 1
        assert results[0].chunk_id == sample_chunks[0].chunk_id

    def test_persist_directory_created(self, tmp_path: Path) -> None:
        """持久化目录自动创建"""
        db_path = str(tmp_path / "auto_created_dir" / "chroma")
        ChromaDBStore(persist_directory=db_path, collection_name="test_dir")
        assert Path(db_path).exists()


# ---------- Count 测试 ----------


class TestCount:
    """count 操作测试"""

    def test_count_empty(self, store: ChromaDBStore) -> None:
        """空 collection count 为 0"""
        assert store.count() == 0

    def test_count_after_upsert(
        self, store: ChromaDBStore, sample_chunks: list[Chunk], sample_embeddings: list[list[float]]
    ) -> None:
        """upsert 后 count 正确"""
        store.upsert(sample_chunks, sample_embeddings)
        assert store.count() == len(sample_chunks)

    def test_count_after_delete(
        self, store: ChromaDBStore, sample_chunks: list[Chunk], sample_embeddings: list[list[float]]
    ) -> None:
        """delete 后 count 减少"""
        store.upsert(sample_chunks, sample_embeddings)
        store.delete(where={"chunk_type": "parent"})
        assert store.count() == len(sample_chunks) - 1
