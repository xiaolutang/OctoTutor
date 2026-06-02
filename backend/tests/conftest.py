import os
from unittest.mock import MagicMock

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

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
    book: str = "必修第一册",
    chapter: str = "第一章 集合与函数概念",
    section: str = "1.1 集合",
    section_id: str | None = None,
    page: int = 1,
    page_start: int | None = None,
    page_end: int | None = None,
    source_pages: list[int] | None = None,
    chunk_type: str = "child",
    block_type: str = "unknown",
    has_formula: bool = False,
    parent_id: str = "test::parent",
    child_index: int = 0,
) -> QueryResult:
    """辅助函数：构造 QueryResult

    所有参数都有合理默认值。page_start/page_end 默认跟随 page。
    section_id 默认自动推导为 "{book}::1.1"。
    """
    _page_start = page_start if page_start is not None else page
    _page_end = page_end if page_end is not None else page
    _source_pages = source_pages if source_pages is not None else [page]
    _section_id = section_id if section_id is not None else f"{book}::{section.split()[0] if section else '1'}"

    return QueryResult(
        chunk_id=chunk_id,
        text=text,
        score=score,
        metadata=ChunkMetadata(
            book=book,
            chapter=chapter,
            section=section,
            section_id=_section_id,
            page=page,
            page_start=_page_start,
            page_end=_page_end,
            source_pages=_source_pages,
            chunk_type=chunk_type,
            block_type=block_type,
            has_formula=has_formula,
            parent_id=parent_id,
            child_index=child_index,
        ),
    )


def make_eval_query_result(
    book: str = "必修第一册",
    page: int = 5,
    score: float = 0.9,
    section_id: str | None = None,
) -> QueryResult:
    """构造 eval 场景的 QueryResult（简化签名：book/page/score/section_id）"""
    return make_query_result(
        chunk_id=f"test::{book}::p{page}",
        text=f"测试文本 page={page}",
        score=score,
        book=book,
        section_id=section_id,
        page=page,
    )
