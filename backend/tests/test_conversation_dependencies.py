"""R009-BF005: chat/dependencies.py — get_db session 注入 单元测试

验证 get_db 依赖注入函数：
1. 正常 yield AsyncSession
2. session 在 generator 结束后正确关闭
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.dependencies import get_db


class TestGetDb:
    """get_db 依赖注入测试"""

    @pytest.fixture
    def mock_session(self):
        """创建 mock AsyncSession"""
        session = AsyncMock(spec=AsyncSession)
        return session

    @pytest.fixture
    def mock_factory(self, mock_session):
        """创建 mock session factory，模拟 async context manager"""
        # factory() 返回一个 async context manager
        context_manager = AsyncMock()
        context_manager.__aenter__ = AsyncMock(return_value=mock_session)
        context_manager.__aexit__ = AsyncMock(return_value=False)

        factory = MagicMock()
        factory.return_value = context_manager
        return factory

    @pytest.fixture
    def mock_request(self, mock_factory):
        """创建 mock Request，带 app.state.db_session_factory"""
        request = MagicMock()
        request.app.state.db_session_factory = mock_factory
        return request

    @pytest.mark.asyncio
    async def test_yields_session(self, mock_request, mock_session):
        """get_db 正常 yield 一个 AsyncSession"""
        gen = get_db(mock_request)
        session = await gen.__anext__()
        assert session is mock_session
        # 清理 generator
        await gen.aclose()

    @pytest.mark.asyncio
    async def test_session_is_async_session_instance(self, mock_request, mock_session):
        """yield 出来的对象是 AsyncSession 类型（mock spec 验证）"""
        gen = get_db(mock_request)
        session = await gen.__anext__()
        assert isinstance(session, AsyncSession)
        await gen.aclose()

    @pytest.mark.asyncio
    async def test_factory_called_as_context_manager(self, mock_request, mock_factory):
        """factory() 被作为 async context manager 调用"""
        gen = get_db(mock_request)
        await gen.__anext__()

        # 验证 factory 被调用一次
        mock_factory.assert_called_once()

        # 验证 __aenter__ 被调用（进入 async with）
        context_manager = mock_factory.return_value
        context_manager.__aenter__.assert_awaited_once()

        await gen.aclose()

    @pytest.mark.asyncio
    async def test_session_closed_after_generator_exhausted(
        self, mock_request, mock_factory, mock_session
    ):
        """generator 正常结束后 session 被关闭（__aexit__ 被调用）"""
        gen = get_db(mock_request)
        session = await gen.__anext__()
        assert session is mock_session

        # generator 耗尽 — 触发 cleanup（async with __aexit__）
        with pytest.raises(StopAsyncIteration):
            await gen.__anext__()

        # 验证 async with 的 __aexit__ 被调用（session 关闭）
        context_manager = mock_factory.return_value
        context_manager.__aexit__.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_session_closed_on_aclose(self, mock_request, mock_factory):
        """通过 aclose() 关闭 generator 时，session 也被正确关闭"""
        gen = get_db(mock_request)
        await gen.__anext__()

        # aclose 触发 generator cleanup
        await gen.aclose()

        # 验证 async with 的 __aexit__ 被调用
        context_manager = mock_factory.return_value
        context_manager.__aexit__.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_async_generator(self, mock_request):
        """get_db 返回 AsyncGenerator 类型"""
        gen = get_db(mock_request)
        assert hasattr(gen, '__anext__')
        assert hasattr(gen, 'aclose')
        await gen.aclose()
