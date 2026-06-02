"""R009-BB002 集成测试 — 流式对话自动创建 + 标题推送

测试场景：
1. 新对话自动创建 conversation 记录
2. 多轮对话不重复创建
3. 标题生成成功推送 title SSE 事件
4. 标题生成失败静默跳过
5. message_count 正确更新
6. SSE 事件顺序正确 (init → ... → done → title → end)
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.agent.graph import create_graph
from app.chat.dependencies import get_chat_service, get_graph, get_checkpointer, get_db
from app.chat.stream_router import router as stream_router
from app.middleware.auth import UserContext, get_current_user

# 共享辅助函数
from tests._helpers import (
    make_mock_chat_service,
    make_mock_generator,
    parse_sse_frames,
)
from tests.conftest import make_query_result


# ---------------------------------------------------------------------------
# 测试辅助（仅保留本文件特有的 _create_test_app）
# ---------------------------------------------------------------------------


def _create_test_app(title=None, mock_graph=None):
    """创建测试 FastAPI 应用，支持配置 title mock

    Args:
        title: generate_title 返回值。None 表示不生成标题（默认返回 None）。
        mock_graph: 可选的预构建 graph。
    """
    from langgraph.checkpoint.memory import MemorySaver

    @asynccontextmanager
    async def _noop_lifespan(app: FastAPI):
        yield

    app = FastAPI(lifespan=_noop_lifespan)
    app.include_router(stream_router)

    # 覆盖鉴权
    test_user = UserContext(user_id="user-123", username="testuser")
    app.dependency_overrides[get_current_user] = lambda: test_user

    # 构建 generator
    gen = make_mock_generator(tokens=["这是", "回答"], title=title)

    # 覆盖 graph
    if mock_graph is None:
        chat_svc = make_mock_chat_service(chunks=[make_query_result()])
        mock_graph = create_graph(
            checkpointer=MemorySaver(),
            chat_service=chat_svc,
            generator=gen,
        )

    app.dependency_overrides[get_graph] = lambda: mock_graph
    app.dependency_overrides[get_checkpointer] = lambda: MemorySaver()

    # 注入 generator 到 app.state（stream_router 直接访问 app.state.generator）
    app.state.generator = gen

    # 覆盖 get_db — 使用 mock AsyncSession
    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.flush = AsyncMock()

    async def _override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = _override_get_db

    return app, mock_db


# ---------------------------------------------------------------------------
# 测试类
# ---------------------------------------------------------------------------


class TestAutoCreateConversation:
    """新对话自动创建 conversation 记录"""

    def test_new_conversation_creates_record(self):
        """不传 conversation_id → 自动创建 conversation 记录，init 帧包含 conversation_id"""
        app, mock_db = _create_test_app(title="自动标题")

        with patch("app.chat.stream_router.ConversationRepo") as MockRepo:
            MockRepo.create = AsyncMock()
            MockRepo.update_message_stats = AsyncMock()
            MockRepo.update = AsyncMock()

            with TestClient(app) as client:
                resp = client.post(
                    "/api/chat/stream",
                    json={"question": "什么是集合？"},
                    headers={"Authorization": "Bearer fake"},
                )

            assert resp.status_code == 200
            frames = parse_sse_frames(resp.text)

            # 1. init 帧包含 conversation_id
            init_frame = frames[0]
            assert init_frame["type"] == "init"
            assert "conversation_id" in init_frame["data"]
            conv_id = init_frame["data"]["conversation_id"]

            # 2. ConversationRepo.create 被调用（新对话）
            MockRepo.create.assert_awaited_once()
            call_args = MockRepo.create.call_args
            created_conv = call_args[0][1]  # 第二个位置参数: Conversation 对象
            assert created_conv.id == conv_id
            assert created_conv.user_id == "user-123"

    def test_init_frame_contains_valid_uuid(self):
        """init 帧中的 conversation_id 是有效的 UUID"""
        app, mock_db = _create_test_app()

        with patch("app.chat.stream_router.ConversationRepo") as MockRepo:
            MockRepo.create = AsyncMock()
            MockRepo.update_message_stats = AsyncMock()

            with TestClient(app) as client:
                resp = client.post(
                    "/api/chat/stream",
                    json={"question": "什么是函数？"},
                    headers={"Authorization": "Bearer fake"},
                )

            frames = parse_sse_frames(resp.text)
            init_frame = frames[0]
            conv_id = init_frame["data"]["conversation_id"]

            # 验证是有效 UUID
            parsed = uuid.UUID(conv_id)
            assert str(parsed) == conv_id


class TestExistingConversation:
    """多轮对话不重复创建"""

    def test_existing_conversation_no_create(self):
        """传入 conversation_id → 不调用 ConversationRepo.create"""
        app, mock_db = _create_test_app(title="测试标题")

        # mock 已有对话记录
        from app.domain.models import Conversation
        mock_conv = Conversation(id="conv-existing-001", user_id="user-123")

        with patch("app.chat.stream_router.ConversationRepo") as MockRepo:
            MockRepo.get_by_id = AsyncMock(return_value=mock_conv)
            MockRepo.update_message_stats = AsyncMock()
            MockRepo.update = AsyncMock()

            with TestClient(app) as client:
                resp = client.post(
                    "/api/chat/stream",
                    json={
                        "question": "什么是函数？",
                        "conversation_id": "conv-existing-001",
                    },
                    headers={"Authorization": "Bearer fake"},
                )

            assert resp.status_code == 200
            frames = parse_sse_frames(resp.text)

            # init 帧使用传入的 conversation_id
            init_frame = frames[0]
            assert init_frame["data"]["conversation_id"] == "conv-existing-001"

            # ConversationRepo.create 不应被调用
            MockRepo.create.assert_not_called()

    def test_existing_conversation_no_title_generation(self):
        """传入 conversation_id → 不尝试生成标题（非新对话）"""
        app, mock_db = _create_test_app(title="不应出现的标题")

        # mock 已有对话记录
        from app.domain.models import Conversation
        mock_conv = Conversation(id="conv-existing-002", user_id="user-123")

        with patch("app.chat.stream_router.ConversationRepo") as MockRepo:
            MockRepo.get_by_id = AsyncMock(return_value=mock_conv)
            MockRepo.update_message_stats = AsyncMock()
            MockRepo.update = AsyncMock()

            with TestClient(app) as client:
                resp = client.post(
                    "/api/chat/stream",
                    json={
                        "question": "什么是函数？",
                        "conversation_id": "conv-existing-002",
                    },
                    headers={"Authorization": "Bearer fake"},
                )

            frames = parse_sse_frames(resp.text)

            # 没有 title 事件（因为不是新对话）
            title_frames = [f for f in frames if f["type"] == "title"]
            assert len(title_frames) == 0


class TestTitleGeneration:
    """标题生成与推送"""

    def test_title_generation_success_pushes_title_event(self):
        """generate_title 返回标题 → SSE 流包含 title 事件"""
        app, mock_db = _create_test_app(title="集合的概念")

        with patch("app.chat.stream_router.ConversationRepo") as MockRepo:
            MockRepo.create = AsyncMock()
            MockRepo.update_message_stats = AsyncMock()
            MockRepo.update = AsyncMock()

            with TestClient(app) as client:
                resp = client.post(
                    "/api/chat/stream",
                    json={"question": "什么是集合？"},
                    headers={"Authorization": "Bearer fake"},
                )

            assert resp.status_code == 200
            frames = parse_sse_frames(resp.text)

            # 验证存在 title 事件
            title_frames = [f for f in frames if f["type"] == "title"]
            assert len(title_frames) == 1

            title_data = title_frames[0]["data"]
            assert "conversation_id" in title_data
            assert title_data["title"] == "集合的概念"

            # 验证 ConversationRepo.update 被调用更新标题
            MockRepo.update.assert_awaited_once()
            update_kwargs = MockRepo.update.call_args
            assert update_kwargs[1]["title"] == "集合的概念"

    def test_title_generation_failure_silent_skip(self):
        """generate_title 返回 None → SSE 流中无 title 事件"""
        app, mock_db = _create_test_app(title=None)

        with patch("app.chat.stream_router.ConversationRepo") as MockRepo:
            MockRepo.create = AsyncMock()
            MockRepo.update_message_stats = AsyncMock()
            MockRepo.update = AsyncMock()

            with TestClient(app) as client:
                resp = client.post(
                    "/api/chat/stream",
                    json={"question": "什么是集合？"},
                    headers={"Authorization": "Bearer fake"},
                )

            assert resp.status_code == 200
            frames = parse_sse_frames(resp.text)

            # 没有 title 事件
            title_frames = [f for f in frames if f["type"] == "title"]
            assert len(title_frames) == 0

            # ConversationRepo.update 不应被调用
            MockRepo.update.assert_not_called()

    def test_title_exception_silent_skip(self):
        """generate_title 抛异常 → SSE 流中无 title 事件，不崩溃"""
        app, mock_db = _create_test_app(title="会被覆盖")
        # 让 generate_title 抛异常
        app.state.generator.generate_title = AsyncMock(side_effect=RuntimeError("LLM 超时"))

        with patch("app.chat.stream_router.ConversationRepo") as MockRepo:
            MockRepo.create = AsyncMock()
            MockRepo.update_message_stats = AsyncMock()

            with TestClient(app) as client:
                resp = client.post(
                    "/api/chat/stream",
                    json={"question": "什么是集合？"},
                    headers={"Authorization": "Bearer fake"},
                )

            assert resp.status_code == 200
            frames = parse_sse_frames(resp.text)

            # 没有 title 事件，也没有 error 事件（异常被静默处理）
            title_frames = [f for f in frames if f["type"] == "title"]
            assert len(title_frames) == 0

            # done 事件仍然存在
            done_frames = [f for f in frames if f["type"] == "done"]
            assert len(done_frames) == 1


class TestMessageCountUpdate:
    """message_count 正确更新"""

    def test_update_message_stats_called(self):
        """对话完成后调用 update_message_stats"""
        app, mock_db = _create_test_app(title="标题")

        with patch("app.chat.stream_router.ConversationRepo") as MockRepo:
            MockRepo.create = AsyncMock()
            MockRepo.update_message_stats = AsyncMock()
            MockRepo.update = AsyncMock()

            with TestClient(app) as client:
                resp = client.post(
                    "/api/chat/stream",
                    json={"question": "什么是集合？"},
                    headers={"Authorization": "Bearer fake"},
                )

            assert resp.status_code == 200

            # update_message_stats 被调用
            MockRepo.update_message_stats.assert_awaited_once()
            call_args = MockRepo.update_message_stats.call_args
            # 第一个位置参数是 session，第二个是 conversation_id
            assert call_args[0][0] == mock_db

    def test_update_message_stats_default_delta(self):
        """默认 message_count += 2（一问一答）"""
        app, mock_db = _create_test_app()

        with patch("app.chat.stream_router.ConversationRepo") as MockRepo:
            MockRepo.create = AsyncMock()
            MockRepo.update_message_stats = AsyncMock()

            with TestClient(app) as client:
                resp = client.post(
                    "/api/chat/stream",
                    json={"question": "什么是集合？"},
                    headers={"Authorization": "Bearer fake"},
                )

            MockRepo.update_message_stats.assert_awaited_once()
            # ConversationRepo.update_message_stats 默认 delta=2
            # 验证调用参数正确
            call_args = MockRepo.update_message_stats.call_args
            # 位置参数: (session, conv_id)，无关键字参数（使用默认 delta=2）
            assert len(call_args[0]) >= 2  # session + conv_id

    def test_existing_conversation_also_updates_stats(self):
        """多轮对话也更新 message_count"""
        app, mock_db = _create_test_app()

        # mock 已有对话记录
        from app.domain.models import Conversation
        mock_conv = Conversation(id="conv-stats-001", user_id="user-123")

        with patch("app.chat.stream_router.ConversationRepo") as MockRepo:
            MockRepo.get_by_id = AsyncMock(return_value=mock_conv)
            MockRepo.update_message_stats = AsyncMock()

            with TestClient(app) as client:
                resp = client.post(
                    "/api/chat/stream",
                    json={
                        "question": "什么是函数？",
                        "conversation_id": "conv-stats-001",
                    },
                    headers={"Authorization": "Bearer fake"},
                )

            assert resp.status_code == 200
            MockRepo.update_message_stats.assert_awaited_once()


class TestSSEEventOrder:
    """SSE 事件顺序正确"""

    def test_event_order_init_done_title(self):
        """新对话 + 标题生成成功：init → ... → done → title"""
        app, mock_db = _create_test_app(title="集合基础")

        with patch("app.chat.stream_router.ConversationRepo") as MockRepo:
            MockRepo.create = AsyncMock()
            MockRepo.update_message_stats = AsyncMock()
            MockRepo.update = AsyncMock()

            with TestClient(app) as client:
                resp = client.post(
                    "/api/chat/stream",
                    json={"question": "什么是集合？"},
                    headers={"Authorization": "Bearer fake"},
                )

            frames = parse_sse_frames(resp.text)
            event_types = [f["type"] for f in frames]

            # 1. 第一个事件是 init
            assert event_types[0] == "init"

            # 2. done 出现在 title 之前
            assert "done" in event_types
            assert "title" in event_types
            done_idx = event_types.index("done")
            title_idx = event_types.index("title")
            assert done_idx < title_idx, f"done({done_idx}) should be before title({title_idx})"

            # 3. title 是最后一个事件
            assert event_types[-1] == "title"

    def test_event_order_no_title(self):
        """新对话 + 标题生成失败：init → ... → done（无 title）"""
        app, mock_db = _create_test_app(title=None)

        with patch("app.chat.stream_router.ConversationRepo") as MockRepo:
            MockRepo.create = AsyncMock()
            MockRepo.update_message_stats = AsyncMock()

            with TestClient(app) as client:
                resp = client.post(
                    "/api/chat/stream",
                    json={"question": "什么是集合？"},
                    headers={"Authorization": "Bearer fake"},
                )

            frames = parse_sse_frames(resp.text)
            event_types = [f["type"] for f in frames]

            # 1. 第一个事件是 init
            assert event_types[0] == "init"

            # 2. 最后一个事件是 done（无 title）
            assert event_types[-1] == "done"
            assert "title" not in event_types

    def test_event_order_existing_conversation(self):
        """多轮对话：init → ... → done（无 title）"""
        app, mock_db = _create_test_app(title="不应出现")

        # mock 已有对话记录
        from app.domain.models import Conversation
        mock_conv = Conversation(id="conv-order-001", user_id="user-123")

        with patch("app.chat.stream_router.ConversationRepo") as MockRepo:
            MockRepo.get_by_id = AsyncMock(return_value=mock_conv)
            MockRepo.update_message_stats = AsyncMock()

            with TestClient(app) as client:
                resp = client.post(
                    "/api/chat/stream",
                    json={
                        "question": "什么是函数？",
                        "conversation_id": "conv-order-001",
                    },
                    headers={"Authorization": "Bearer fake"},
                )

            frames = parse_sse_frames(resp.text)
            event_types = [f["type"] for f in frames]

            # 1. 第一个事件是 init，使用传入的 conversation_id
            assert event_types[0] == "init"
            assert frames[0]["data"]["conversation_id"] == "conv-order-001"

            # 2. 最后一个事件是 done
            assert event_types[-1] == "done"

            # 3. 没有 title（非新对话）
            assert "title" not in event_types

    def test_init_always_first(self):
        """init 事件始终是第一个"""
        app, mock_db = _create_test_app()

        with patch("app.chat.stream_router.ConversationRepo") as MockRepo:
            MockRepo.create = AsyncMock()
            MockRepo.update_message_stats = AsyncMock()

            with TestClient(app) as client:
                resp = client.post(
                    "/api/chat/stream",
                    json={"question": "什么是集合？"},
                    headers={"Authorization": "Bearer fake"},
                )

            frames = parse_sse_frames(resp.text)
            assert frames[0]["type"] == "init"
            assert "conversation_id" in frames[0]["data"]


class TestOwnershipCheck:
    """已有 conversation_id 归属校验 — R009-PATCH01-BB001"""

    def test_ownership_not_found_returns_error_03901(self):
        """get_by_id 返回 None → SSE error 03901，不发送 init，不调用 graph"""
        from app.domain.models import Conversation

        app, mock_db = _create_test_app(title="不应出现")

        with patch("app.chat.stream_router.ConversationRepo") as MockRepo:
            MockRepo.get_by_id = AsyncMock(return_value=None)
            MockRepo.update_message_stats = AsyncMock()
            MockRepo.update = AsyncMock()
            MockRepo.create = AsyncMock()

            with TestClient(app) as client:
                resp = client.post(
                    "/api/chat/stream",
                    json={
                        "question": "越权问题",
                        "conversation_id": "conv-other-user-001",
                    },
                    headers={"Authorization": "Bearer fake"},
                )

            assert resp.status_code == 200
            frames = parse_sse_frames(resp.text)

            # 第一帧是 error，code=03901
            assert len(frames) == 1
            assert frames[0]["type"] == "error"
            assert frames[0]["data"]["code"] == "03901"

            # 不发送 init
            # （frames 中只有 error 这一帧，无 init）

            # 不调用 graph → update_message_stats 不应被调用
            MockRepo.update_message_stats.assert_not_called()

            # 不调用 create
            MockRepo.create.assert_not_called()

    def test_ownership_db_exception_returns_error_02901(self):
        """get_by_id 抛异常 → SSE error 02901，不发送 init，不调用 graph"""
        app, mock_db = _create_test_app(title="不应出现")

        with patch("app.chat.stream_router.ConversationRepo") as MockRepo:
            MockRepo.get_by_id = AsyncMock(side_effect=RuntimeError("DB 连接断开"))
            MockRepo.update_message_stats = AsyncMock()
            MockRepo.update = AsyncMock()
            MockRepo.create = AsyncMock()

            with TestClient(app) as client:
                resp = client.post(
                    "/api/chat/stream",
                    json={
                        "question": "测试异常",
                        "conversation_id": "conv-db-error-001",
                    },
                    headers={"Authorization": "Bearer fake"},
                )

            assert resp.status_code == 200
            frames = parse_sse_frames(resp.text)

            # 第一帧是 error，code=02901
            assert len(frames) == 1
            assert frames[0]["type"] == "error"
            assert frames[0]["data"]["code"] == "02901"

            # 不发送 init

            # 不调用 graph → update_message_stats 不应被调用
            MockRepo.update_message_stats.assert_not_called()

            # 不调用 create
            MockRepo.create.assert_not_called()

    def test_ownership_pass_allows_stream(self):
        """get_by_id 返回记录 → 正常进入 graph.astream，发送 init"""
        from app.domain.models import Conversation

        app, mock_db = _create_test_app()

        mock_conv = Conversation(id="conv-own-001", user_id="user-123")

        with patch("app.chat.stream_router.ConversationRepo") as MockRepo:
            MockRepo.get_by_id = AsyncMock(return_value=mock_conv)
            MockRepo.update_message_stats = AsyncMock()

            with TestClient(app) as client:
                resp = client.post(
                    "/api/chat/stream",
                    json={
                        "question": "正常问题",
                        "conversation_id": "conv-own-001",
                    },
                    headers={"Authorization": "Bearer fake"},
                )

            assert resp.status_code == 200
            frames = parse_sse_frames(resp.text)

            # init 正常发送
            assert frames[0]["type"] == "init"
            assert frames[0]["data"]["conversation_id"] == "conv-own-001"

            # 不调用 create
            MockRepo.create.assert_not_called()

            # update_message_stats 被调用
            MockRepo.update_message_stats.assert_awaited_once()

    def test_new_conversation_skips_ownership_check(self):
        """新对话不触发 get_by_id 归属校验"""
        app, mock_db = _create_test_app()

        with patch("app.chat.stream_router.ConversationRepo") as MockRepo:
            MockRepo.create = AsyncMock()
            MockRepo.update_message_stats = AsyncMock()
            MockRepo.get_by_id = AsyncMock(return_value=None)

            with TestClient(app) as client:
                resp = client.post(
                    "/api/chat/stream",
                    json={"question": "新对话问题"},
                    headers={"Authorization": "Bearer fake"},
                )

            assert resp.status_code == 200
            frames = parse_sse_frames(resp.text)

            # init 正常
            assert frames[0]["type"] == "init"

            # 不调用 get_by_id（新对话不走归属校验）
            MockRepo.get_by_id.assert_not_called()

            # create 被调用
            MockRepo.create.assert_awaited_once()
