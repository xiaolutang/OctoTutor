"""检索 API 端点

POST /api/retrieve — 查询 → 返回 top-K 相关 chunks（cosine similarity）
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.middleware.auth import UserContext, get_current_user
from app.rag.embeddings import DashScopeEmbedding
from app.rag.vector_store import ChromaDBStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["retrieve"])


# ---------------------------------------------------------------------------
# Pydantic 模型
# ---------------------------------------------------------------------------


class RetrieveRequest(BaseModel):
    """检索请求"""

    query: str = Field(..., min_length=1, description="查询文本")
    top_k: int = Field(default=5, ge=1, le=20, description="返回数量 1-20")


class ChunkResponse(BaseModel):
    """单个 chunk 响应"""

    chunk_id: str
    text: str
    score: float
    metadata: dict[str, Any]


class RetrieveResponse(BaseModel):
    """检索响应"""

    chunks: list[ChunkResponse]
    total: int


# ---------------------------------------------------------------------------
# 依赖注入
# ---------------------------------------------------------------------------


def get_vector_store() -> ChromaDBStore:
    """获取 ChromaDBStore 单例（由 main.py 初始化并挂载到 app.state）"""
    from app.main import app

    return app.state.vector_store


def get_embedding_service() -> DashScopeEmbedding:
    """获取 DashScopeEmbedding 单例"""
    from app.main import app

    return app.state.embedding_service


# ---------------------------------------------------------------------------
# 端点
# ---------------------------------------------------------------------------


@router.post("/retrieve", response_model=RetrieveResponse)
async def retrieve(
    request: RetrieveRequest,
    store: ChromaDBStore = Depends(get_vector_store),
    embedding_service: DashScopeEmbedding = Depends(get_embedding_service),
    user: UserContext = Depends(get_current_user),
) -> RetrieveResponse:
    """向量检索端点

    接收查询文本，调用 Embedding 向量化后检索 ChromaDB，返回 top-K 相关 chunks。
    """
    try:
        query_embedding = embedding_service.embed_query(request.query)
    except Exception as exc:
        logger.error("Embedding 调用失败: %s", exc)
        raise HTTPException(status_code=500, detail="Embedding 服务暂时不可用") from exc

    try:
        results = store.query(
            query_embedding=query_embedding,
            top_k=request.top_k,
        )
    except Exception as exc:
        logger.error("ChromaDB 查询失败: %s", exc)
        raise HTTPException(status_code=500, detail="检索服务暂时不可用") from exc

    chunks = [
        ChunkResponse(
            chunk_id=r.chunk_id,
            text=r.text,
            score=r.score,
            metadata=r.metadata.to_dict(),
        )
        for r in results
    ]

    return RetrieveResponse(chunks=chunks, total=len(chunks))
