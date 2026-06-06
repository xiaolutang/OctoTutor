from contextlib import asynccontextmanager
import os

from fastapi import FastAPI
from starlette.responses import FileResponse

from app.config import settings
from app.rag.embeddings import DashScopeEmbedding
from app.rag.vector_store import ChromaDBStore
from app.infra.bm25 import BM25Retriever
from app.infra.reranker import DashScopeReranker
from app.infra.llm import LLMGenerator
from app.infra.image_manager import ImageManager
from app.infra.recognition import VLMRecognitionProvider
from app.chat.service import ChatService
from app.agent.graph import create_graph
from app.infra.database import engine, async_session_factory, create_tables
from app.api.routes.health import router as health_router
from app.api.routes.retrieve import router as retrieve_router
from app.api.routes.config import router as config_router
from app.chat.router import router as chat_router
from app.chat.stream_router import router as stream_router
from app.chat.conversation_router import router as conversation_router
from app.chat.upload_router import router as upload_router, serve_router as upload_serve_router
from app.middleware.upload_mtime import upload_mtime_middleware


async def _ensure_database_exists(database_url: str):
    """连接 postgres 默认库，自动创建目标数据库

    PostgreSQL 的 CREATE DATABASE 不支持 IF NOT EXISTS，
    所以 catch "already exists" 错误视为成功。
    """
    from urllib.parse import urlparse

    parsed = urlparse(database_url)
    db_name = parsed.path.lstrip("/")

    # 构建 postgres 默认库的连接串
    postgres_url = database_url.replace(f"/{db_name}", "/postgres")

    import psycopg
    async with await psycopg.AsyncConnection.connect(
        postgres_url, autocommit=True
    ) as conn:
        try:
            await conn.execute(f'CREATE DATABASE "{db_name}"')
            print(f"[startup] Database '{db_name}' created")
        except psycopg.errors.DuplicateDatabase:
            print(f"[startup] Database '{db_name}' already exists")


@asynccontextmanager
async def lifespan(application: FastAPI):
    """应用生命周期管理：初始化依赖单例"""
    # 初始化 ChromaDBStore
    store = ChromaDBStore(
        persist_directory=settings.chroma_persist_dir,
    )
    application.state.vector_store = store

    # 初始化 DashScopeEmbedding
    embedding_service = DashScopeEmbedding(
        api_key=settings.dashscope_api_key,
        model=settings.dashscope_embedding_model,
        dimension=settings.dashscope_embedding_dimension,
    )
    application.state.embedding_service = embedding_service

    # 初始化 BM25Retriever（从 ChromaDB 加载全量 chunks 构建索引）
    bm25 = BM25Retriever()
    chunks = store.get_all_chunks()
    if chunks:
        bm25.build_index(chunks)
        print(f"[startup] BM25 index built with {len(chunks)} chunks")
    application.state.bm25 = bm25

    # 初始化 DashScope Reranker
    reranker = DashScopeReranker(
        api_key=settings.dashscope_api_key,
        model=settings.rerank_model,
    )
    application.state.reranker = reranker
    print(f"[startup] Reranker initialized (model={settings.rerank_model})")

    # 初始化 LLM Generator
    generator = LLMGenerator(
        api_key=settings.newapi_api_key,
        base_url=settings.newapi_base_url,
        model=settings.llm_model,
    )
    application.state.generator = generator
    print(f"[startup] LLM Generator initialized (model={settings.llm_model})")

    # 初始化 ChatService（Agent graph retrieve 节点使用其检索管线）
    chat_service = ChatService(
        embedding=embedding_service,
        vector_store=store,
        bm25=bm25,
        reranker=reranker,
        generator=generator,
        settings=settings,
    )
    application.state.chat_service = chat_service
    print("[startup] ChatService initialized")

    # R019: 初始化 ImageManager
    image_manager = ImageManager(
        upload_dir=settings.data_uploads_dir,
        max_storage_mb=settings.image_max_storage_mb,
    )
    application.state.image_manager = image_manager
    # 启动时清理过期文件
    await image_manager.cleanup_lru()
    print(f"[startup] ImageManager initialized (dir={settings.data_uploads_dir})")

    # R019: 初始化 VLMRecognitionProvider（DashScope 直连）
    recognition_provider = VLMRecognitionProvider(
        api_key=settings.dashscope_api_key,
        base_url=settings.dashscope_vision_base_url,
        model=settings.vision_model,
        image_manager=image_manager,
    )
    application.state.recognition_provider = recognition_provider
    print(f"[startup] VLMRecognitionProvider initialized (model={settings.vision_model})")

    # 初始化 LangGraph PostgresSaver（失败时回退 MemorySaver）
    checkpointer = None
    checkpointer_ctx = None
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        # 自动建库：连接 postgres 默认库，确保目标数据库存在
        await _ensure_database_exists(settings.database_url)

        checkpointer_ctx = AsyncPostgresSaver.from_conn_string(settings.database_url)
        checkpointer = await checkpointer_ctx.__aenter__()
        await checkpointer.setup()
        print("[startup] PostgresSaver initialized")
    except Exception as e:
        checkpointer_ctx = None
        from langgraph.checkpoint.memory import MemorySaver

        checkpointer = MemorySaver()
        print(
            f"[startup] WARNING: PostgresSaver failed ({e}), "
            "using MemorySaver fallback"
        )
    application.state.checkpointer = checkpointer

    # 初始化 SQLAlchemy async engine + 自动建表（R009）
    try:
        await create_tables()
        application.state.db_session_factory = async_session_factory
        print("[startup] SQLAlchemy engine + conversations table initialized")
    except Exception as e:
        print(f"[startup] WARNING: SQLAlchemy init failed ({e})")

    # 编译 Agent StateGraph
    graph = create_graph(
        checkpointer=checkpointer,
        chat_service=chat_service,
        generator=generator,
    )
    application.state.graph = graph
    print("[startup] Agent graph compiled")

    print(f"[startup] {settings.app_name} v{settings.app_version} started")
    yield
    # shutdown: 释放 PostgresSaver 连接池
    if checkpointer_ctx is not None:
        await checkpointer_ctx.__aexit__(None, None, None)
        print("[shutdown] PostgresSaver connection pool closed")
    # shutdown: 释放 SQLAlchemy engine (R009)
    try:
        await engine.dispose()
        print("[shutdown] SQLAlchemy engine disposed")
    except Exception:
        pass
    print(f"[shutdown] {settings.app_name} stopped")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

app.include_router(health_router)
app.include_router(config_router)
app.include_router(retrieve_router)
app.include_router(chat_router)
app.include_router(stream_router)
app.include_router(conversation_router)
app.include_router(upload_router)
app.include_router(upload_serve_router)

# R019: 图片访问 mtime 中间件
app.middleware("http")(upload_mtime_middleware)
