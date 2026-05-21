import pytest
from unittest.mock import MagicMock


@pytest.mark.asyncio
async def test_health_returns_healthy(client):
    """health 端点返回 healthy 状态"""
    response = await client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["chromadb"]["connected"] is True
    assert data["chromadb"]["document_count"] == 42
    assert data["embedding"]["available"] is True


@pytest.mark.asyncio
async def test_health_unhealthy_when_chromadb_fails(client):
    """ChromaDB 异常时返回 unhealthy"""
    # 修改 mock 使 count 抛出异常
    from app.main import app

    mock_store = app.state.vector_store
    mock_store.count.side_effect = Exception("connection refused")

    response = await client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "unhealthy"
    assert data["chromadb"]["connected"] is False
    assert data["chromadb"]["document_count"] == 0

    # 恢复 mock
    mock_store.count.side_effect = None
    mock_store.count.return_value = 42


@pytest.mark.asyncio
async def test_health_empty_chromadb(client):
    """ChromaDB 为空时返回 healthy + document_count=0"""
    from app.main import app

    mock_store = app.state.vector_store
    original_count = mock_store.count.return_value
    mock_store.count.return_value = 0

    response = await client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["chromadb"]["document_count"] == 0

    # 恢复
    mock_store.count.return_value = original_count
