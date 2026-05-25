"""SQLAlchemy async engine + session factory

为 Conversation CRUD 提供 async session 管理。
复用 settings.database_url，驱动替换为 postgresql+psycopg://。
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

# 将 postgresql:// 替换为 postgresql+psycopg://（SQLAlchemy async 驱动）
_database_url = settings.database_url
if _database_url.startswith("postgresql://"):
    _database_url = _database_url.replace("postgresql://", "postgresql+psycopg://", 1)

engine = create_async_engine(_database_url, pool_size=5)

async_session_factory = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False,
)


async def create_tables():
    """创建所有 SQLAlchemy 表（lifespan 中调用）"""
    from app.domain.models import Base  # noqa: WPS433 — 延迟导入避免循环依赖

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
