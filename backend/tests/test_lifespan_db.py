"""R009-BB003: lifespan DB 初始化集成测试

验证 lifespan 中 SQLAlchemy engine 的初始化、建表、释放行为。
通过 mock 外部依赖（ChromaDB、DashScope、LLM、PostgresSaver）隔离测试。
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _set_env(monkeypatch):
    """确保测试环境变量"""
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-jwt-secret")


@pytest.fixture
def mock_deps():
    """Mock lifespan 中所有非 DB 外部依赖

    返回一个 dict，方便测试中访问各个 mock。
    """
    mocks = {}

    # ChromaDBStore: 返回一个带 get_all_chunks 的 mock 实例
    mock_store_instance = MagicMock()
    mock_store_instance.get_all_chunks.return_value = []
    mocks["store_instance"] = mock_store_instance
    mocks["ChromaDBStore"] = MagicMock(return_value=mock_store_instance)

    # DashScopeEmbedding
    mock_embedding_instance = MagicMock()
    mocks["embedding_instance"] = mock_embedding_instance
    mocks["DashScopeEmbedding"] = MagicMock(return_value=mock_embedding_instance)

    # BM25Retriever
    mock_bm25_instance = MagicMock()
    mocks["bm25_instance"] = mock_bm25_instance
    mocks["BM25Retriever"] = MagicMock(return_value=mock_bm25_instance)

    # DashScopeReranker
    mock_reranker_instance = MagicMock()
    mocks["reranker_instance"] = mock_reranker_instance
    mocks["DashScopeReranker"] = MagicMock(return_value=mock_reranker_instance)

    # LLMGenerator
    mock_generator_instance = MagicMock()
    mocks["generator_instance"] = mock_generator_instance
    mocks["LLMGenerator"] = MagicMock(return_value=mock_generator_instance)

    # ChatService
    mock_chat_service_instance = MagicMock()
    mocks["chat_service_instance"] = mock_chat_service_instance
    mocks["ChatService"] = MagicMock(return_value=mock_chat_service_instance)

    # create_graph
    mock_graph = MagicMock()
    mocks["graph"] = mock_graph
    mocks["create_graph"] = MagicMock(return_value=mock_graph)

    # R019: ImageManager
    mock_image_manager = MagicMock()
    mock_image_manager.cleanup_lru = AsyncMock(return_value=0)
    mocks["image_manager_instance"] = mock_image_manager
    mocks["ImageManager"] = MagicMock(return_value=mock_image_manager)

    # R019: VLMRecognitionProvider
    mock_vlm = MagicMock()
    mocks["vlm_instance"] = mock_vlm
    mocks["VLMRecognitionProvider"] = MagicMock(return_value=mock_vlm)

    return mocks


@pytest.fixture
def mock_db():
    """Mock database module 中的关键函数和对象"""
    mock_engine = AsyncMock()
    mock_engine.dispose = AsyncMock()

    mock_session_factory = MagicMock()

    mock_create_tables = AsyncMock()

    return {
        "engine": mock_engine,
        "async_session_factory": mock_session_factory,
        "create_tables": mock_create_tables,
    }


# ---------------------------------------------------------------------------
# Helper: 构建带 mock 的 lifespan 测试
# ---------------------------------------------------------------------------

async def _run_lifespan_with_mocks(mock_deps, mock_db, pg_saver_fail=False):
    """构造 FastAPI app 并运行 lifespan，返回 async generator yield app

    pg_saver_fail: 如果 True，让 PostgresSaver 的 try 块失败走 fallback。
    """

    with patch("app.main.ChromaDBStore", mock_deps["ChromaDBStore"]), \
         patch("app.main.DashScopeEmbedding", mock_deps["DashScopeEmbedding"]), \
         patch("app.main.BM25Retriever", mock_deps["BM25Retriever"]), \
         patch("app.main.DashScopeReranker", mock_deps["DashScopeReranker"]), \
         patch("app.main.LLMGenerator", mock_deps["LLMGenerator"]), \
         patch("app.main.ChatService", mock_deps["ChatService"]), \
         patch("app.main.create_graph", mock_deps["create_graph"]), \
         patch("app.main.ImageManager", mock_deps["ImageManager"]), \
         patch("app.main.VLMRecognitionProvider", mock_deps["VLMRecognitionProvider"]), \
         patch("app.main.engine", mock_db["engine"]), \
         patch("app.main.async_session_factory", mock_db["async_session_factory"]), \
         patch("app.main.create_tables", mock_db["create_tables"]), \
         patch("app.main._ensure_database_exists", new_callable=AsyncMock,
               side_effect=Exception("no pg") if pg_saver_fail else None):

        from fastapi import FastAPI
        from app.main import lifespan

        app = FastAPI(lifespan=lifespan)

        async with lifespan(app):
            yield app


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_engine_initialized_on_startup(mock_deps, mock_db):
    """lifespan 启动后 app.state.db_session_factory 存在"""
    async for app in _run_lifespan_with_mocks(mock_deps, mock_db):
        assert hasattr(app.state, "db_session_factory")
        assert app.state.db_session_factory is mock_db["async_session_factory"]


@pytest.mark.asyncio
async def test_create_tables_called(mock_deps, mock_db):
    """lifespan 启动时调用 create_tables() 自动建表"""
    async for _ in _run_lifespan_with_mocks(mock_deps, mock_db):
        pass
    mock_db["create_tables"].assert_awaited_once()


@pytest.mark.asyncio
async def test_engine_disposed_on_shutdown(mock_deps, mock_db):
    """lifespan 退出时调用 engine.dispose() 释放连接池"""
    async for _ in _run_lifespan_with_mocks(mock_deps, mock_db):
        pass  # 退出 async with 块后 shutdown 逻辑执行

    mock_db["engine"].dispose.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_tables_failure_does_not_crash(mock_deps, mock_db):
    """create_tables 抛异常时 lifespan 不崩溃，只是跳过 DB 初始化"""
    mock_db["create_tables"].side_effect = Exception("DB connection refused")

    # lifespan 应正常完成，不会抛异常
    async for app in _run_lifespan_with_mocks(mock_deps, mock_db):
        # db_session_factory 未被赋值（create_tables 失败跳过了赋值行）
        pass

    # 即使失败，shutdown 仍会尝试 dispose
    mock_db["engine"].dispose.assert_awaited_once()
