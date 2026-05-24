"""前端鉴权配置接口 — 供前端 AuthProvider 加载 SDK 配置"""

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import settings

router = APIRouter()


class ConfigResponse(BaseModel):
    clientId: str
    authCenterBaseURL: str


@router.get("/api/config", tags=["config"])
async def get_config() -> ConfigResponse:
    """返回前端 AuthService 所需的运行时配置"""
    return ConfigResponse(
        clientId=settings.auth_client_id,
        authCenterBaseURL=settings.auth_base_url,
    )
