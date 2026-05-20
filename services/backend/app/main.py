from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.api.routes.health import router as health_router


@asynccontextmanager
async def lifespan(application: FastAPI):
    """应用生命周期管理"""
    print(f"[startup] {settings.app_name} v{settings.app_version} started")
    yield
    print(f"[shutdown] {settings.app_name} stopped")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

app.include_router(health_router)
