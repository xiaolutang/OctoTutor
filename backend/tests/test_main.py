import pytest


@pytest.mark.asyncio
async def test_app_starts(client):
    """应用可启动且响应请求"""
    response = await client.get("/api/health")
    assert response.status_code == 200
