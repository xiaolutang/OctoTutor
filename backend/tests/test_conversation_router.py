"""对话 CRUD API 端到端测试 — R009-BB001

10 个测试场景：
- 列表首页：GET /api/conversations，验证 items + cursor + has_more
- 列表翻页：使用 cursor 查询下一页
- 重命名成功：PATCH /api/conversations/{id}，验证 200
- 重命名空标题拒绝：body={title: ""}，验证 400
- 置顶成功：body={pinned: true}，验证 200 + pinned_at 有值
- 置顶超限拒绝：已有 5 个置顶后再置顶，验证 400 + 错误码 03902
- 取消置顶：body={pinned: false}，验证 200
- 删除成功：DELETE /api/conversations/{id}，验证 204
- 删除不存在：DELETE 不存在的 id，验证 404
- 非本人对话拒绝：使用不同 user_id 创建的对话，验证 404

使用 dependency_overrides + mock ConversationRepo 静态方法。
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# 确保测试环境有必要的配置
os.environ.setdefault("DASHSCOPE_API_KEY", "test-api-key-for-testing")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key")

from app.middleware.auth import UserContext, get_current_user
from app.domain.models import Conversation

# ---------------------------------------------------------------------------
# 测试辅助工具
# ---------------------------------------------------------------------------

_TEST_USER = UserContext(user_id="user-001", username="testuser")
_OTHER_USER = UserContext(user_id="user-002", username="otheruser")


def _make_conversation(
    conv_id: str = "conv-001",
    user_id: str = "user-001",
    title: str = "测试对话",
    pinned: bool = False,
    pinned_at: datetime | None = None,
    message_count: int = 5,
) -> Conversation:
    """构造一个 Conversation ORM 对象"""
    now = datetime.now(timezone.utc)
    conv = Conversation()
    conv.id = conv_id
    conv.user_id = user_id
    conv.title = title
    conv.pinned = pinned
    conv.pinned_at = pinned_at
    conv.message_count = message_count
    conv.created_at = now
    conv.updated_at = now
    return conv


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client():
    """测试用 AsyncClient — mock 所有依赖"""
    from app.main import app
    from app.chat.dependencies import get_db, get_checkpointer

    # --- Mock DB session ---
    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()

    async def _override_get_db():
        yield mock_db

    # --- Mock checkpointer ---
    mock_checkpointer = MagicMock()
    mock_checkpointer.adelete_thread = AsyncMock()

    # --- 覆盖鉴权依赖 ---
    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_checkpointer] = lambda: mock_checkpointer

    # --- Mock app.state（避免 lifespan 缺失报错）---
    app.state.vector_store = MagicMock()
    app.state.embedding_service = MagicMock()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 将 mock_db 挂到 ac 上供测试用例访问
        ac._mock_db = mock_db
        ac._mock_checkpointer = mock_checkpointer
        yield ac

    app.dependency_overrides.clear()


# ===================================================================
# T1: 列表首页 — GET /api/conversations
# ===================================================================


@pytest.mark.asyncio
async def test_list_conversations_first_page(client: AsyncClient):
    """首页返回 items + cursor + has_more"""
    convs = [_make_conversation(conv_id=f"conv-{i}") for i in range(3)]
    with patch("app.chat.conversation_router.ConversationRepo") as MockRepo:
        MockRepo.list_by_user = AsyncMock(return_value=(convs, True))
        response = await client.get("/api/conversations")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "cursor" in data
    assert "has_more" in data
    assert data["has_more"] is True
    assert len(data["items"]) == 3
    assert data["cursor"] is not None


# ===================================================================
# T2: 列表翻页 — 使用 cursor 查询下一页
# ===================================================================


@pytest.mark.asyncio
async def test_list_conversations_with_cursor(client: AsyncClient):
    """翻页请求带 cursor 参数"""
    convs = [_make_conversation(conv_id="conv-page2")]
    with patch("app.chat.conversation_router.ConversationRepo") as MockRepo:
        MockRepo.list_by_user = AsyncMock(return_value=(convs, False))
        response = await client.get(
            "/api/conversations", params={"cursor": "dGVzdA=="}
        )
    assert response.status_code == 200
    data = response.json()
    assert data["has_more"] is False
    assert len(data["items"]) == 1
    assert data["items"][0]["id"] == "conv-page2"


# ===================================================================
# T3: 重命名成功 — PATCH /api/conversations/{id}
# ===================================================================


@pytest.mark.asyncio
async def test_rename_conversation_success(client: AsyncClient):
    """重命名对话 — 返回 200 + 新标题"""
    original = _make_conversation(conv_id="conv-rename", title="旧标题")
    updated = _make_conversation(conv_id="conv-rename", title="新标题")
    with patch("app.chat.conversation_router.ConversationRepo") as MockRepo:
        MockRepo.get_by_id = AsyncMock(return_value=original)
        MockRepo.update = AsyncMock(return_value=updated)
        response = await client.patch(
            "/api/conversations/conv-rename",
            json={"title": "新标题"},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "新标题"
    assert data["id"] == "conv-rename"


# ===================================================================
# T4: 重命名空标题拒绝 — body={title: ""}
# ===================================================================


@pytest.mark.asyncio
async def test_rename_empty_title_rejected(client: AsyncClient):
    """空标题被拒绝 — 返回 400"""
    original = _make_conversation(conv_id="conv-empty-title")
    with patch("app.chat.conversation_router.ConversationRepo") as MockRepo:
        MockRepo.get_by_id = AsyncMock(return_value=original)
        response = await client.patch(
            "/api/conversations/conv-empty-title",
            json={"title": ""},
        )
    assert response.status_code == 400
    data = response.json()
    assert data["code"] == "03903"


# ===================================================================
# T5: 置顶成功 — body={pinned: true}
# ===================================================================


@pytest.mark.asyncio
async def test_pin_conversation_success(client: AsyncClient):
    """置顶成功 — 返回 200 + pinned_at 有值"""
    original = _make_conversation(conv_id="conv-pin", pinned=False)
    now = datetime.now(timezone.utc)
    updated = _make_conversation(conv_id="conv-pin", pinned=True, pinned_at=now)
    with patch("app.chat.conversation_router.ConversationRepo") as MockRepo:
        MockRepo.get_by_id = AsyncMock(return_value=original)
        MockRepo.count_pinned = AsyncMock(return_value=2)
        MockRepo.update = AsyncMock(return_value=updated)
        response = await client.patch(
            "/api/conversations/conv-pin",
            json={"pinned": True},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["pinned"] is True
    assert data["pinned_at"] is not None


# ===================================================================
# T6: 置顶超限拒绝 — 已有 5 个置顶
# ===================================================================


@pytest.mark.asyncio
async def test_pin_conversation_limit_exceeded(client: AsyncClient):
    """已有 5 个置顶后再置顶 — 返回 400 + 错误码 03902"""
    original = _make_conversation(conv_id="conv-pin-limit", pinned=False)
    with patch("app.chat.conversation_router.ConversationRepo") as MockRepo:
        MockRepo.get_by_id = AsyncMock(return_value=original)
        MockRepo.count_pinned = AsyncMock(return_value=5)
        response = await client.patch(
            "/api/conversations/conv-pin-limit",
            json={"pinned": True},
        )
    assert response.status_code == 400
    data = response.json()
    assert data["code"] == "03902"


# ===================================================================
# T7: 取消置顶 — body={pinned: false}
# ===================================================================


@pytest.mark.asyncio
async def test_unpin_conversation_success(client: AsyncClient):
    """取消置顶 — 返回 200 + pinned 为 false"""
    original = _make_conversation(
        conv_id="conv-unpin",
        pinned=True,
        pinned_at=datetime.now(timezone.utc),
    )
    updated = _make_conversation(conv_id="conv-unpin", pinned=False, pinned_at=None)
    with patch("app.chat.conversation_router.ConversationRepo") as MockRepo:
        MockRepo.get_by_id = AsyncMock(return_value=original)
        MockRepo.update = AsyncMock(return_value=updated)
        response = await client.patch(
            "/api/conversations/conv-unpin",
            json={"pinned": False},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["pinned"] is False


# ===================================================================
# T8: 删除成功 — DELETE /api/conversations/{id}
# ===================================================================


@pytest.mark.asyncio
async def test_delete_conversation_success(client: AsyncClient):
    """删除对话 — 返回 204"""
    with patch("app.chat.conversation_router.ConversationRepo") as MockRepo:
        MockRepo.delete_by_id = AsyncMock(return_value=True)
        response = await client.delete("/api/conversations/conv-delete")
    assert response.status_code == 204


# ===================================================================
# T9: 删除不存在 — DELETE 不存在的 id
# ===================================================================


@pytest.mark.asyncio
async def test_delete_conversation_not_found(client: AsyncClient):
    """删除不存在的对话 — 返回 404"""
    with patch("app.chat.conversation_router.ConversationRepo") as MockRepo:
        MockRepo.delete_by_id = AsyncMock(return_value=False)
        response = await client.delete("/api/conversations/nonexistent-id")
    assert response.status_code == 404
    data = response.json()
    assert data["code"] == "03901"


# ===================================================================
# T10: 非本人对话拒绝 — 不同 user_id 的对话
# ===================================================================


@pytest.mark.asyncio
async def test_update_other_users_conversation_rejected(client: AsyncClient):
    """非本人对话 — 返回 404（get_by_id 按 user_id 过滤，找不到即 404）"""
    with patch("app.chat.conversation_router.ConversationRepo") as MockRepo:
        # get_by_id 查不到（因为 user_id 不匹配）
        MockRepo.get_by_id = AsyncMock(return_value=None)
        response = await client.patch(
            "/api/conversations/other-conv",
            json={"title": "黑客尝试"},
        )
    assert response.status_code == 404
    data = response.json()
    assert data["code"] == "03901"
