import os
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from unittest.mock import MagicMock

# 确保测试环境有必要的配置（避免 Settings 校验失败）
os.environ.setdefault("DASHSCOPE_API_KEY", "test-api-key-for-testing")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key")

from app.rag.models import ChunkMetadata, QueryResult
from app.middleware.auth import UserContext, get_current_user


# 测试用 mock 用户
_test_user = UserContext(user_id="user-123", username="testuser")


@pytest_asyncio.fixture
async def client():
    """测试用 AsyncClient（带 mock 依赖注入 + auth override）"""
    from app.main import app

    # Mock ChromaDBStore
    mock_store = MagicMock()
    mock_store.count.return_value = 42

    # Mock DashScopeEmbedding
    mock_embedding = MagicMock()

    # 通过 app.state 注入（lifespan 不在测试中执行，需手动设置）
    app.state.vector_store = mock_store
    app.state.embedding_service = mock_embedding

    # 覆盖鉴权依赖
    app.dependency_overrides[get_current_user] = lambda: _test_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    # 清理 dependency overrides
    app.dependency_overrides.clear()


def make_query_result(
    chunk_id: str = "test::chunk::id",
    text: str = "test text",
    score: float = 0.95,
) -> QueryResult:
    """辅助函数：构造 QueryResult"""
    return QueryResult(
        chunk_id=chunk_id,
        text=text,
        score=score,
        metadata=ChunkMetadata(
            book="必修第一册",
            chapter="第一章 集合与函数概念",
            section="1.1 集合",
            section_id="必修第一册::1.1",
            page=1,
            page_start=1,
            page_end=1,
            source_pages=[1],
            chunk_type="child",
            block_type="unknown",
            has_formula=False,
            parent_id="test::parent",
            child_index=0,
        ),
    )
