"""BB001 Router Depends 注入集成测试

7 个测试场景：
- T1: 无 token POST /api/chat → 401
- T2: 无 token POST /api/chat/stream → 401
- T3: 无 token POST /api/retrieve → 401
- T4: 无 token GET /api/health → 200
- T5: 有效 token POST /api/chat → 200
- T6: 有效 token POST /api/chat/stream → 200 (SSE)
- T7: 有效 token POST /api/retrieve → 200

使用 TestClient + mock JWT + dependency_overrides mock service 层。
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from jose import jwt

from app.middleware.auth import ALGORITHM

# ---------------------------------------------------------------------------
# 测试辅助工具
# ---------------------------------------------------------------------------

TEST_SECRET = "test-jwt-secret-key"


def _make_token(
    sub: str = "user-001",
    client_id: str = "testuser",
    exp: int = 9999999999,
    token_type: str = "access",
) -> str:
    """构造有效 JWT token"""
    return jwt.encode(
        {"sub": sub, "client_id": client_id, "exp": exp, "type": token_type},
        TEST_SECRET,
        algorithm=ALGORITHM,
    )


def _auth_headers(token: str | None = None) -> dict:
    """构造 Authorization header"""
    if token is None:
        return {}
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Fixture: TestClient with mocked dependencies
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    """同步 TestClient，mock 所有 service 层依赖"""
    from langgraph.checkpoint.memory import MemorySaver

    from app.main import app
    from app.chat.service import ChatService
    from app.chat.dependencies import get_chat_service, get_graph, get_checkpointer, get_db
    from app.rag.embeddings import DashScopeEmbedding
    from app.rag.vector_store import ChromaDBStore
    from app.api.routes.retrieve import get_vector_store as get_vs_retrieve
    from app.api.routes.retrieve import get_embedding_service as get_emb_retrieve

    # --- Mock ChatService ---
    mock_chat_service = MagicMock(spec=ChatService)
    mock_chat_service.handle_chat.return_value = {
        "answer": "mock answer",
        "sources": [],
        "context_used": 0,
    }

    # --- Mock ChromaDBStore ---
    mock_store = MagicMock(spec=ChromaDBStore)
    mock_store.count.return_value = 42
    mock_store.query.return_value = []

    # --- Mock DashScopeEmbedding ---
    mock_embedding = MagicMock(spec=DashScopeEmbedding)
    mock_embedding.embed_query.return_value = [0.1] * 1024

    # --- Mock Graph + Checkpointer ---
    from app.agent.graph import create_graph
    from app.rag.models import QueryResult, ChunkMetadata

    mock_graph_service = MagicMock()
    mock_graph_service.retrieve.return_value = MagicMock(
        chunks=[], degraded=False, degradation_reason=None
    )

    mock_gen = MagicMock()
    async def _fake_stream(*args, **kwargs):
        yield "mock answer"
    mock_gen.generate_stream = _fake_stream
    mock_gen.generate_title = AsyncMock(return_value=None)
    mock_gen.get_chat_model.return_value = MagicMock()

    checkpointer = MemorySaver()
    graph = create_graph(
        checkpointer=checkpointer,
        chat_service=mock_graph_service,
        generator=mock_gen,
    )

    # --- app.state 注入（health/stream_router 需要访问）---
    app.state.vector_store = mock_store
    app.state.embedding_service = mock_embedding
    app.state.generator = mock_gen

    # --- dependency_overrides ---
    app.dependency_overrides[get_chat_service] = lambda: mock_chat_service
    app.dependency_overrides[get_vs_retrieve] = lambda: mock_store
    app.dependency_overrides[get_emb_retrieve] = lambda: mock_embedding
    app.dependency_overrides[get_graph] = lambda: graph
    app.dependency_overrides[get_checkpointer] = lambda: checkpointer

    # --- Mock DB session ---
    mock_db = AsyncMock()

    async def _override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = _override_get_db

    with patch("app.middleware.auth.settings") as mock_settings:
        mock_settings.auth_jwt_secret = TEST_SECRET
        tc = TestClient(app)
        yield tc

    # 清理
    app.dependency_overrides.clear()


# ===================================================================
# T1: 无 token POST /api/chat → 401
# ===================================================================


def test_chat_no_token_401(client: TestClient):
    """无 Authorization header → POST /api/chat 返回 401"""
    response = client.post(
        "/api/chat",
        json={"question": "test", "top_k": 3},
    )
    assert response.status_code == 401
    assert "Missing authentication token" in response.json()["detail"]


# ===================================================================
# T2: 无 token POST /api/chat/stream → 401
# ===================================================================


def test_stream_no_token_401(client: TestClient):
    """无 Authorization header → POST /api/chat/stream 返回 401"""
    response = client.post(
        "/api/chat/stream",
        json={"question": "test", "top_k": 3},
    )
    assert response.status_code == 401
    assert "Missing authentication token" in response.json()["detail"]


# ===================================================================
# T3: 无 token POST /api/retrieve → 401
# ===================================================================


def test_retrieve_no_token_401(client: TestClient):
    """无 Authorization header → POST /api/retrieve 返回 401"""
    response = client.post(
        "/api/retrieve",
        json={"query": "test", "top_k": 5},
    )
    assert response.status_code == 401
    assert "Missing authentication token" in response.json()["detail"]


# ===================================================================
# T4: 无 token GET /api/health → 200
# ===================================================================


def test_health_no_token_200(client: TestClient):
    """无 Authorization header → GET /api/health 返回 200"""
    response = client.get("/api/health")
    assert response.status_code == 200


# ===================================================================
# T5: 有效 token POST /api/chat → 200
# ===================================================================


def test_chat_valid_token_200(client: TestClient):
    """有效 JWT → POST /api/chat 返回 200"""
    token = _make_token()
    response = client.post(
        "/api/chat",
        json={"question": "test", "top_k": 3},
        headers=_auth_headers(token),
    )
    assert response.status_code == 200


# ===================================================================
# T6: 有效 token POST /api/chat/stream → SSE 流
# ===================================================================


def test_stream_valid_token_sse(client: TestClient):
    """有效 JWT → POST /api/chat/stream 返回 200 + SSE content-type"""
    token = _make_token()
    response = client.post(
        "/api/chat/stream",
        json={"question": "test", "top_k": 3},
        headers=_auth_headers(token),
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"


# ===================================================================
# T7: 有效 token POST /api/retrieve → 200
# ===================================================================


def test_retrieve_valid_token_200(client: TestClient):
    """有效 JWT → POST /api/retrieve 返回 200"""
    token = _make_token()
    response = client.post(
        "/api/retrieve",
        json={"query": "test", "top_k": 5},
        headers=_auth_headers(token),
    )
    assert response.status_code == 200
