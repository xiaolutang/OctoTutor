"""R009-BF002: ConversationRepo CRUD 数据访问层单元测试

使用 SQLite 内存数据库 + aiosqlite 提供真实 AsyncSession，
验证 ConversationRepo 的所有 CRUD 操作。
"""

from datetime import datetime, timezone, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.domain.models import Base, Conversation
from app.infra.conversation_repo import ConversationRepo


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# SQLite 内存异步引擎
_engine = create_async_engine("sqlite+aiosqlite://", echo=False)
_session_factory = async_sessionmaker(
    _engine, class_=AsyncSession, expire_on_commit=False,
)


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """每个测试前建表、测试后清表"""
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def session():
    """提供测试用 AsyncSession，测试结束自动回滚"""
    async with _session_factory() as s:
        # 用 read-committed 风格：每个操作后 commit 以便跨查询可见
        yield s
        await s.commit()


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _make_conversation(
    conv_id: str = "conv-001",
    user_id: str = "user-123",
    title: str = "新对话",
    pinned: bool = False,
    pinned_at: datetime | None = None,
    message_count: int = 0,
    updated_at: datetime | None = None,
) -> Conversation:
    now = datetime.now(timezone.utc)
    return Conversation(
        id=conv_id,
        user_id=user_id,
        title=title,
        pinned=pinned,
        pinned_at=pinned_at,
        message_count=message_count,
        created_at=now,
        updated_at=updated_at or now,
    )


# ===========================================================================
# 测试
# ===========================================================================


class TestCreate:
    """创建对话"""

    @pytest.mark.asyncio
    async def test_create_returns_conversation(self, session: AsyncSession):
        conv = _make_conversation(conv_id="c1", user_id="u1", title="测试对话")
        result = await ConversationRepo.create(session, conv)
        await session.commit()

        assert result.id == "c1"
        assert result.user_id == "u1"
        assert result.title == "测试对话"

    @pytest.mark.asyncio
    async def test_create_flushes_to_db(self, session: AsyncSession):
        conv = _make_conversation(conv_id="c2", user_id="u1")
        await ConversationRepo.create(session, conv)
        await session.commit()

        # 新 session 查询验证持久化
        async with _session_factory() as s2:
            found = await ConversationRepo.get_by_id(s2, "c2", "u1")
            assert found is not None
            assert found.id == "c2"


class TestGetById:
    """按 ID 查询"""

    @pytest.mark.asyncio
    async def test_get_existing(self, session: AsyncSession):
        conv = _make_conversation(conv_id="c1", user_id="u1")
        await ConversationRepo.create(session, conv)
        await session.commit()

        async with _session_factory() as s2:
            result = await ConversationRepo.get_by_id(s2, "c1", "u1")
        assert result is not None
        assert result.id == "c1"

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_none(self, session: AsyncSession):
        async with _session_factory() as s2:
            result = await ConversationRepo.get_by_id(s2, "no-such-id", "u1")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_wrong_user_returns_none(self, session: AsyncSession):
        conv = _make_conversation(conv_id="c1", user_id="u1")
        await ConversationRepo.create(session, conv)
        await session.commit()

        # 用不同 user_id 查询应返回 None
        async with _session_factory() as s2:
            result = await ConversationRepo.get_by_id(s2, "c1", "wrong-user")
        assert result is None


class TestListByUser:
    """列表分页"""

    @pytest.mark.asyncio
    async def test_first_page(self, session: AsyncSession):
        """首页返回全部普通对话"""
        now = datetime.now(timezone.utc)
        for i in range(5):
            conv = _make_conversation(
                conv_id=f"c{i}", user_id="u1",
                updated_at=now - timedelta(seconds=i),
            )
            session.add(conv)
        await session.commit()

        async with _session_factory() as s2:
            items, has_more = await ConversationRepo.list_by_user(s2, "u1", limit=20)
        assert len(items) == 5
        assert has_more is False

    @pytest.mark.asyncio
    async def test_first_page_with_pinned(self, session: AsyncSession):
        """首页先返回置顶再返回普通"""
        now = datetime.now(timezone.utc)
        # 1 个置顶
        session.add(_make_conversation(
            conv_id="pinned1", user_id="u1", pinned=True,
            pinned_at=now, updated_at=now,
        ))
        # 2 个普通
        for i in range(2):
            session.add(_make_conversation(
                conv_id=f"n{i}", user_id="u1",
                updated_at=now - timedelta(seconds=i),
            ))
        await session.commit()

        async with _session_factory() as s2:
            items, has_more = await ConversationRepo.list_by_user(s2, "u1", limit=20)
        assert len(items) == 3
        # 置顶在前
        assert items[0].id == "pinned1"
        assert items[0].pinned is True
        assert has_more is False

    @pytest.mark.asyncio
    async def test_pagination_has_more(self, session: AsyncSession):
        """创建超过 limit 条对话，首页 has_more=True"""
        now = datetime.now(timezone.utc)
        for i in range(25):
            session.add(_make_conversation(
                conv_id=f"c{i:03d}", user_id="u1",
                updated_at=now - timedelta(seconds=i),
            ))
        await session.commit()

        async with _session_factory() as s2:
            items, has_more = await ConversationRepo.list_by_user(s2, "u1", limit=20)
        assert len(items) == 20
        assert has_more is True

    @pytest.mark.asyncio
    async def test_cursor_pagination(self, session: AsyncSession):
        """使用游标翻页"""
        import base64

        now = datetime.now(timezone.utc)
        for i in range(25):
            session.add(_make_conversation(
                conv_id=f"c{i:03d}", user_id="u1",
                updated_at=now - timedelta(seconds=i),
            ))
        await session.commit()

        async with _session_factory() as s2:
            page1, has_more1 = await ConversationRepo.list_by_user(s2, "u1", limit=20)

        assert has_more1 is True
        last = page1[-1]
        cursor = base64.b64encode(
            f"{last.updated_at.isoformat()}|{last.id}".encode()
        ).decode()

        async with _session_factory() as s2:
            page2, has_more2 = await ConversationRepo.list_by_user(s2, "u1", cursor=cursor, limit=20)

        assert len(page2) == 5
        assert has_more2 is False
        # page2 不应包含 page1 的项
        page1_ids = {c.id for c in page1}
        page2_ids = {c.id for c in page2}
        assert page1_ids.isdisjoint(page2_ids)

    @pytest.mark.asyncio
    async def test_list_only_returns_own_conversations(self, session: AsyncSession):
        """不同用户的对话互不可见"""
        now = datetime.now(timezone.utc)
        session.add(_make_conversation(conv_id="u1-c1", user_id="user-1", updated_at=now))
        session.add(_make_conversation(conv_id="u2-c1", user_id="user-2", updated_at=now))
        await session.commit()

        async with _session_factory() as s2:
            items, _ = await ConversationRepo.list_by_user(s2, "user-1")
        assert len(items) == 1
        assert items[0].id == "u1-c1"


class TestUpdate:
    """更新操作"""

    @pytest.mark.asyncio
    async def test_update_title(self, session: AsyncSession):
        conv = _make_conversation(conv_id="c1", user_id="u1", title="旧标题")
        await ConversationRepo.create(session, conv)
        await session.commit()

        async with _session_factory() as s2:
            result = await ConversationRepo.update(s2, "c1", "u1", title="新标题")
            await s2.commit()

        assert result is not None
        assert result.title == "新标题"

    @pytest.mark.asyncio
    async def test_update_pinned_sets_pinned_at(self, session: AsyncSession):
        conv = _make_conversation(conv_id="c1", user_id="u1")
        await ConversationRepo.create(session, conv)
        await session.commit()

        now = datetime.now(timezone.utc)
        async with _session_factory() as s2:
            result = await ConversationRepo.update(
                s2, "c1", "u1", pinned=True, pinned_at=now,
            )
            await s2.commit()

        assert result is not None
        assert result.pinned is True
        assert result.pinned_at is not None

    @pytest.mark.asyncio
    async def test_update_nonexistent_returns_none(self, session: AsyncSession):
        async with _session_factory() as s2:
            result = await ConversationRepo.update(s2, "no-id", "u1", title="x")
        assert result is None


class TestDelete:
    """删除操作"""

    @pytest.mark.asyncio
    async def test_delete_existing(self, session: AsyncSession):
        conv = _make_conversation(conv_id="c1", user_id="u1")
        await ConversationRepo.create(session, conv)
        await session.commit()

        async with _session_factory() as s2:
            deleted = await ConversationRepo.delete_by_id(s2, "c1", "u1")
            await s2.commit()

        assert deleted is True

        # 删除后再查询返回 None
        async with _session_factory() as s2:
            found = await ConversationRepo.get_by_id(s2, "c1", "u1")
        assert found is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_false(self, session: AsyncSession):
        async with _session_factory() as s2:
            deleted = await ConversationRepo.delete_by_id(s2, "no-id", "u1")
        assert deleted is False

    @pytest.mark.asyncio
    async def test_delete_wrong_user_returns_false(self, session: AsyncSession):
        conv = _make_conversation(conv_id="c1", user_id="u1")
        await ConversationRepo.create(session, conv)
        await session.commit()

        async with _session_factory() as s2:
            deleted = await ConversationRepo.delete_by_id(s2, "c1", "wrong-user")
        assert deleted is False


class TestCountPinned:
    """置顶计数"""

    @pytest.mark.asyncio
    async def test_count_pinned(self, session: AsyncSession):
        now = datetime.now(timezone.utc)
        for i in range(3):
            session.add(_make_conversation(
                conv_id=f"p{i}", user_id="u1", pinned=True,
                pinned_at=now, updated_at=now,
            ))
        # 非置顶
        session.add(_make_conversation(conv_id="n1", user_id="u1", pinned=False))
        await session.commit()

        async with _session_factory() as s2:
            count = await ConversationRepo.count_pinned(s2, "u1")
        assert count == 3

    @pytest.mark.asyncio
    async def test_count_pinned_no_pinned(self, session: AsyncSession):
        session.add(_make_conversation(conv_id="n1", user_id="u1", pinned=False))
        await session.commit()

        async with _session_factory() as s2:
            count = await ConversationRepo.count_pinned(s2, "u1")
        assert count == 0

    @pytest.mark.asyncio
    async def test_count_pinned_only_counts_own(self, session: AsyncSession):
        now = datetime.now(timezone.utc)
        session.add(_make_conversation(
            conv_id="p1", user_id="user-1", pinned=True, pinned_at=now,
        ))
        session.add(_make_conversation(
            conv_id="p2", user_id="user-2", pinned=True, pinned_at=now,
        ))
        await session.commit()

        async with _session_factory() as s2:
            count = await ConversationRepo.count_pinned(s2, "user-1")
        assert count == 1


class TestUpdateMessageStats:
    """更新消息统计"""

    @pytest.mark.asyncio
    async def test_update_message_stats_increments(self, session: AsyncSession):
        conv = _make_conversation(conv_id="c1", user_id="u1", message_count=0)
        await ConversationRepo.create(session, conv)
        await session.commit()

        async with _session_factory() as s2:
            await ConversationRepo.update_message_stats(s2, "c1", message_count_delta=2)
            await s2.commit()

        async with _session_factory() as s2:
            found = await ConversationRepo.get_by_id(s2, "c1", "u1")
        assert found is not None
        assert found.message_count == 2

    @pytest.mark.asyncio
    async def test_update_message_stats_accumulates(self, session: AsyncSession):
        conv = _make_conversation(conv_id="c1", user_id="u1", message_count=2)
        await ConversationRepo.create(session, conv)
        await session.commit()

        async with _session_factory() as s2:
            await ConversationRepo.update_message_stats(s2, "c1", message_count_delta=3)
            await s2.commit()

        async with _session_factory() as s2:
            found = await ConversationRepo.get_by_id(s2, "c1", "u1")
        assert found is not None
        assert found.message_count == 5
