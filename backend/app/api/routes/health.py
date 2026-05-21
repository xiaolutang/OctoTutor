"""健康检查端点

GET /api/health — 返回 ChromaDB 连接状态、文档数量、Embedding 可用性
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.rag.embeddings import DashScopeEmbedding
from app.rag.vector_store import ChromaDBStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["health"])


# ---------------------------------------------------------------------------
# Pydantic 模型
# ---------------------------------------------------------------------------


class ChromaDBStatus(BaseModel):
    connected: bool
    document_count: int


class EmbeddingStatus(BaseModel):
    available: bool


class HealthResponse(BaseModel):
    status: str
    chromadb: ChromaDBStatus
    embedding: EmbeddingStatus


# ---------------------------------------------------------------------------
# 依赖注入
# ---------------------------------------------------------------------------


def get_vector_store() -> ChromaDBStore:
    """获取 ChromaDBStore 单例"""
    from app.main import app

    return app.state.vector_store


def get_embedding_service() -> DashScopeEmbedding:
    """获取 DashScopeEmbedding 单例"""
    from app.main import app

    return app.state.embedding_service


# ---------------------------------------------------------------------------
# 端点
# ---------------------------------------------------------------------------


@router.get("/health", response_model=HealthResponse)
async def health_check(
    store: ChromaDBStore = Depends(get_vector_store),
    embedding_service: DashScopeEmbedding = Depends(get_embedding_service),
) -> HealthResponse:
    """健康检查端点

    返回 ChromaDB 连接状态、文档数量和 Embedding 可用性。
    """
    # ChromaDB 状态检测
    chromadb_connected = False
    document_count = 0
    try:
        document_count = store.count()
        chromadb_connected = True
    except Exception:
        logger.warning("ChromaDB 连接检测失败", exc_info=True)

    # Embedding 可用性检测
    embedding_available = False
    try:
        embedding_available = embedding_service is not None
    except Exception:
        logger.warning("Embedding 检测失败", exc_info=True)

    overall_status = "healthy" if chromadb_connected else "unhealthy"

    return HealthResponse(
        status=overall_status,
        chromadb=ChromaDBStatus(
            connected=chromadb_connected,
            document_count=document_count,
        ),
        embedding=EmbeddingStatus(available=embedding_available),
    )
