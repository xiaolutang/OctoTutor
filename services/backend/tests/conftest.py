import os
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from unittest.mock import MagicMock

# 确保测试环境有必要的配置（避免 Settings 校验失败）
os.environ.setdefault("DASHSCOPE_API_KEY", "test-api-key-for-testing")

from app.rag.models import ChunkMetadata, QueryResult


@pytest_asyncio.fixture
async def client():
    """测试用 AsyncClient（带 mock 依赖注入）"""
    from app.main import app

    # Mock ChromaDBStore
    mock_store = MagicMock()
    mock_store.count.return_value = 42

    # Mock DashScopeEmbedding
    mock_embedding = MagicMock()

    # 通过 app.state 注入（lifespan 不在测试中执行，需手动设置）
    app.state.vector_store = mock_store
    app.state.embedding_service = mock_embedding

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


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
            page=1,
            chunk_type="child",
            has_formula=False,
            parent_id="test::parent",
            child_index=0,
        ),
    )
