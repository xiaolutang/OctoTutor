from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.rag.embeddings import DashScopeEmbedding
from app.rag.vector_store import ChromaDBStore
from app.infra.bm25 import BM25Retriever
from app.infra.reranker import DashScopeReranker
from app.infra.llm import LLMGenerator
from app.chat.service import ChatService
from app.agent.graph import create_graph
from app.api.routes.health import router as health_router
from app.api.routes.retrieve import router as retrieve_router
from app.chat.router import router as chat_router
from app.chat.stream_router import router as stream_router
from app.chat.conversation_router import router as conversation_router


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

    # 初始化 LangGraph PostgresSaver（失败时回退 MemorySaver）
    checkpointer = None
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        checkpointer = AsyncPostgresSaver.from_conn_string(settings.database_url)
        await checkpointer.setup()
        print("[startup] PostgresSaver initialized")
    except Exception as e:
        from langgraph.checkpoint.memory import MemorySaver

        checkpointer = MemorySaver()
        print(
            f"[startup] WARNING: PostgresSaver failed ({e}), "
            "using MemorySaver fallback"
        )
    application.state.checkpointer = checkpointer

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
    print(f"[shutdown] {settings.app_name} stopped")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

app.include_router(health_router)
app.include_router(retrieve_router)
app.include_router(chat_router)
app.include_router(stream_router)
app.include_router(conversation_router)
