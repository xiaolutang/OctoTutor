from fastapi import APIRouter

from app.config import settings

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health_check():
    """健康检查端点

    BF-002 阶段返回简化版本（无 ChromaDB 状态）。
    R003-BB-008 会扩展此端点添加 chromadb 状态和 embedding 可用性。
    """
    return {
        "status": "healthy",
        "version": settings.app_version,
    }
