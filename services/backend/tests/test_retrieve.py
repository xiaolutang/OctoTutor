import pytest
from unittest.mock import MagicMock

from tests.conftest import make_query_result


# ---------------------------------------------------------------------------
# POST /api/retrieve 正常场景
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retrieve_returns_top_k_chunks(client):
    """正常检索返回 top-K chunks"""
    from app.main import app

    mock_embedding = app.state.embedding_service
    mock_store = app.state.vector_store

    mock_embedding.embed_query.return_value = [0.1] * 768
    mock_store.query.return_value = [
        make_query_result(chunk_id="c1", text="chunk 1", score=0.95),
        make_query_result(chunk_id="c2", text="chunk 2", score=0.88),
        make_query_result(chunk_id="c3", text="chunk 3", score=0.72),
    ]

    response = await client.post(
        "/api/retrieve",
        json={"query": "二次函数的顶点公式", "top_k": 3},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["chunks"]) == 3
    assert data["total"] == 3
    assert data["chunks"][0]["chunk_id"] == "c1"
    assert data["chunks"][0]["score"] == 0.95
    assert "metadata" in data["chunks"][0]
    assert data["chunks"][0]["metadata"]["book"] == "必修第一册"

    # 验证调用参数
    mock_embedding.embed_query.assert_called_once_with("二次函数的顶点公式")
    mock_store.query.assert_called_once()
    call_kwargs = mock_store.query.call_args
    assert call_kwargs.kwargs["top_k"] == 3


@pytest.mark.asyncio
async def test_retrieve_default_top_k(client):
    """默认 top_k=5"""
    from app.main import app

    mock_embedding = app.state.embedding_service
    mock_store = app.state.vector_store

    mock_embedding.embed_query.return_value = [0.1] * 768
    mock_store.query.return_value = []

    response = await client.post(
        "/api/retrieve",
        json={"query": "集合的定义"},
    )
    assert response.status_code == 200
    call_kwargs = mock_store.query.call_args
    assert call_kwargs.kwargs["top_k"] == 5


@pytest.mark.asyncio
async def test_retrieve_chunk_metadata_complete(client):
    """返回的 chunk 包含完整 metadata"""
    from app.main import app

    mock_embedding = app.state.embedding_service
    mock_store = app.state.vector_store

    mock_embedding.embed_query.return_value = [0.1] * 768
    mock_store.query.return_value = [make_query_result()]

    response = await client.post(
        "/api/retrieve",
        json={"query": "test"},
    )
    assert response.status_code == 200
    chunk = response.json()["chunks"][0]
    meta = chunk["metadata"]
    assert meta["book"] == "必修第一册"
    assert meta["chapter"] == "第一章 集合与函数概念"
    assert meta["section"] == "1.1 集合"
    assert meta["page"] == 1
    assert meta["chunk_type"] == "child"
    assert meta["has_formula"] is False
    assert meta["parent_id"] == "test::parent"
    assert meta["child_index"] == 0


# ---------------------------------------------------------------------------
# 空/无结果场景
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retrieve_empty_result(client):
    """空库返回 chunks=[], total=0"""
    from app.main import app

    mock_embedding = app.state.embedding_service
    mock_store = app.state.vector_store

    mock_embedding.embed_query.return_value = [0.1] * 768
    mock_store.query.return_value = []

    response = await client.post(
        "/api/retrieve",
        json={"query": "不存在的查询内容"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["chunks"] == []
    assert data["total"] == 0


# ---------------------------------------------------------------------------
# 参数校验
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retrieve_missing_query_returns_422(client):
    """缺少 query 返回 422"""
    response = await client.post("/api/retrieve", json={})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_retrieve_empty_query_returns_422(client):
    """空 query 返回 422"""
    response = await client.post("/api/retrieve", json={"query": ""})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_retrieve_top_k_too_large_returns_422(client):
    """top_k > 20 返回 422"""
    response = await client.post(
        "/api/retrieve",
        json={"query": "test", "top_k": 21},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_retrieve_top_k_zero_returns_422(client):
    """top_k=0 返回 422"""
    response = await client.post(
        "/api/retrieve",
        json={"query": "test", "top_k": 0},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_retrieve_top_k_negative_returns_422(client):
    """top_k < 0 返回 422"""
    response = await client.post(
        "/api/retrieve",
        json={"query": "test", "top_k": -1},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# 边界值
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retrieve_top_k_boundary_1(client):
    """top_k=1 正常"""
    from app.main import app

    mock_embedding = app.state.embedding_service
    mock_store = app.state.vector_store

    mock_embedding.embed_query.return_value = [0.1] * 768
    mock_store.query.return_value = [make_query_result()]

    response = await client.post(
        "/api/retrieve",
        json={"query": "test", "top_k": 1},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_retrieve_top_k_boundary_20(client):
    """top_k=20 正常"""
    from app.main import app

    mock_embedding = app.state.embedding_service
    mock_store = app.state.vector_store

    mock_embedding.embed_query.return_value = [0.1] * 768
    mock_store.query.return_value = [make_query_result()] * 20

    response = await client.post(
        "/api/retrieve",
        json={"query": "test", "top_k": 20},
    )
    assert response.status_code == 200
    assert response.json()["total"] == 20


# ---------------------------------------------------------------------------
# 服务异常
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retrieve_embedding_failure_returns_500(client):
    """Embedding 服务失败返回 500"""
    from app.main import app

    mock_embedding = app.state.embedding_service
    mock_embedding.embed_query.side_effect = RuntimeError("API down")

    response = await client.post(
        "/api/retrieve",
        json={"query": "test"},
    )
    assert response.status_code == 500

    # 恢复
    mock_embedding.embed_query.side_effect = None


@pytest.mark.asyncio
async def test_retrieve_chromadb_failure_returns_500(client):
    """ChromaDB 查询失败返回 500"""
    from app.main import app

    mock_embedding = app.state.embedding_service
    mock_store = app.state.vector_store

    mock_embedding.embed_query.return_value = [0.1] * 768
    mock_store.query.side_effect = Exception("connection lost")

    response = await client.post(
        "/api/retrieve",
        json={"query": "test"},
    )
    assert response.status_code == 500

    # 恢复
    mock_store.query.side_effect = None
