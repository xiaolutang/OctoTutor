from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.rag.embeddings import DashScopeEmbedding
from app.rag.vector_store import ChromaDBStore
from app.api.routes.health import router as health_router
from app.api.routes.retrieve import router as retrieve_router


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
