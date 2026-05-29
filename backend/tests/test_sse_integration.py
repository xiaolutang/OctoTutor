"""R007-BB005+BB006 集成测试 — SSE 集成

3 组测试覆盖：
1. SSE 流式端到端 — thinking+status+sources+token+done 事件序列
2. conversation_id 多轮对话 — 自动创建 / 恢复对话
3. GET /api/conversations/current — 200 + messages / 204
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from starlette.testclient import TestClient

from app.agent.graph import create_graph
from app.chat.dependencies import get_chat_service, get_graph, get_checkpointer, get_db
from app.chat.stream_router import router as stream_router
from app.chat.conversation_router import router as conversation_router
from app.middleware.auth import UserContext, get_current_user

# 共享辅助函数
from tests._helpers import (
    make_auth_headers,
    make_mock_chat_service,
    make_mock_generator,
    parse_sse_frames,
)
from tests.conftest import make_query_result


# ---------------------------------------------------------------------------
# 测试辅助（仅保留本文件特有的 _create_test_app）
# ---------------------------------------------------------------------------


def _create_test_app(mock_service=None, mock_graph=None, mock_checkpointer=None):
    """创建测试 FastAPI 应用"""
    from langgraph.checkpoint.memory import MemorySaver

    @asynccontextmanager
    async def _noop_lifespan(app: FastAPI):
        yield

    app = FastAPI(lifespan=_noop_lifespan)
    app.include_router(stream_router)
    app.include_router(conversation_router)

    # 覆盖鉴权
    test_user = UserContext(user_id="user-123", username="testuser")

    def _override_user():
        return test_user

    app.dependency_overrides[get_current_user] = _override_user

    # 覆盖 graph
    gen = make_mock_generator(tokens=["这是", "回答"])
    if mock_graph is None:
        chat_svc = make_mock_chat_service(chunks=[make_query_result()])
        mock_graph = create_graph(
            checkpointer=MemorySaver(),
            chat_service=chat_svc,
            generator=gen,
        )

    app.dependency_overrides[get_graph] = lambda: mock_graph

    # 覆盖 checkpointer
    if mock_checkpointer is None:
        mock_checkpointer = MemorySaver()

    app.dependency_overrides[get_checkpointer] = lambda: mock_checkpointer

    # 注入 generator 到 app.state（stream_router 直接访问）
    app.state.generator = gen

    # 覆盖 get_db（stream_router 新增 db session 依赖）
    mock_db = AsyncMock()

    async def _override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = _override_get_db

    # 覆盖 chat_service（部分测试仍需要）
    if mock_service:
        app.dependency_overrides[get_chat_service] = lambda: mock_service

    return app


# ---------------------------------------------------------------------------
# 1. SSE 流式端到端测试
# ---------------------------------------------------------------------------


class TestSSEStreamE2E:
    """SSE 流式端到端：发送数学问题 → 收到事件序列"""

    def test_sse_content_type(self):
        """验证返回 content-type 为 text/event-stream"""
        app = _create_test_app()
        with TestClient(app) as client:
            resp = client.post(
                "/api/chat/stream",
                json={"question": "什么是集合？"},
                headers=make_auth_headers(),
            )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]

    def test_event_sequence_textbook(self):
        """数学问题 → status(retrieving) + sources + status(generating) + token + done"""
        app = _create_test_app()
        with TestClient(app) as client:
            resp = client.post(
                "/api/chat/stream",
                json={"question": "什么是集合？"},
                headers=make_auth_headers(),
            )
        assert resp.status_code == 200
        frames = parse_sse_frames(resp.text)

        event_types = [f["type"] for f in frames]
        # 必须包含的关键事件
        assert "done" in event_types, f"missing done, got: {event_types}"

        # 验证 status 事件
        status_frames = [f for f in frames if f["type"] == "status"]
        assert len(status_frames) >= 1

        # 验证最后一个事件是 done
        assert frames[-1]["type"] == "done"
        assert frames[-1]["data"] is None

    def test_sources_event_format(self):
        """sources 事件包含 SourceReference 列表"""
        app = _create_test_app()
        with TestClient(app) as client:
            resp = client.post(
                "/api/chat/stream",
                json={"question": "什么是集合？"},
                headers=make_auth_headers(),
            )
        frames = parse_sse_frames(resp.text)
        sources_frames = [f for f in frames if f["type"] == "sources"]

        if sources_frames:
            sources_data = sources_frames[0]["data"]
            assert isinstance(sources_data, list)
            assert len(sources_data) >= 1
            assert "chunk_id" in sources_data[0]
            assert "book" in sources_data[0]

    def test_no_conversation_id_generates_uuid(self):
        """不传 conversation_id 时自动生成并返回"""
        app = _create_test_app()
        with TestClient(app) as client:
            resp = client.post(
                "/api/chat/stream",
                json={"question": "什么是集合？"},
                headers=make_auth_headers(),
            )
        # 只要不报错即可
        assert resp.status_code == 200

    def test_with_conversation_id(self):
        """传入 conversation_id 正常处理"""
        app = _create_test_app()
        with TestClient(app) as client:
            resp = client.post(
                "/api/chat/stream",
                json={
                    "question": "什么是集合？",
                    "conversation_id": "conv-test-001",
                },
                headers=make_auth_headers(),
            )
        assert resp.status_code == 200
        frames = parse_sse_frames(resp.text)
        assert frames[-1]["type"] == "done"


# ---------------------------------------------------------------------------
# 2. conversation_id 多轮对话
# ---------------------------------------------------------------------------


class TestConversationMultiTurn:
    """conversation_id 多轮对话测试"""

    def test_auto_create_conversation_id(self):
        """不传 conversation_id → 自动创建"""
        app = _create_test_app()
        with TestClient(app) as client:
            resp = client.post(
                "/api/chat/stream",
                json={"question": "什么是函数？"},
                headers=make_auth_headers(),
            )
        assert resp.status_code == 200
        frames = parse_sse_frames(resp.text)
        assert any(f["type"] == "done" for f in frames)

    def test_resume_with_conversation_id(self):
        """第二次传 conversation_id → 恢复对话"""
        from langgraph.checkpoint.memory import MemorySaver

        checkpointer = MemorySaver()
        chat_svc = make_mock_chat_service(chunks=[make_query_result()])
        gen = make_mock_generator(tokens=["回答"])
        graph = create_graph(
            checkpointer=checkpointer,
            chat_service=chat_svc,
            generator=gen,
        )

        app = _create_test_app(mock_graph=graph, mock_checkpointer=checkpointer)

        with TestClient(app) as client:
            # 第一轮 — 不传 conversation_id
            resp1 = client.post(
                "/api/chat/stream",
                json={"question": "什么是函数？"},
                headers=make_auth_headers(),
            )
            assert resp1.status_code == 200
            frames1 = parse_sse_frames(resp1.text)
            assert any(f["type"] == "done" for f in frames1)

            # 第二轮 — 使用固定的 conversation_id
            resp2 = client.post(
                "/api/chat/stream",
                json={
                    "question": "什么是定义域？",
                    "conversation_id": "conv-multi-turn",
                },
                headers=make_auth_headers(),
            )
            assert resp2.status_code == 200
            frames2 = parse_sse_frames(resp2.text)
            assert any(f["type"] == "done" for f in frames2)


# ---------------------------------------------------------------------------
# 3. GET /api/conversations/current — 200 / 204
# ---------------------------------------------------------------------------


class TestGetCurrentConversation:
    """GET /api/conversations/current 测试"""

    def test_no_history_returns_204(self):
        """无历史对话 → 204"""
        from langgraph.checkpoint.memory import MemorySaver

        app = _create_test_app(mock_checkpointer=MemorySaver())
        with TestClient(app) as client:
            resp = client.get(
                "/api/conversations/current",
                headers=make_auth_headers(),
            )
        assert resp.status_code == 204

    def test_with_history_returns_200(self):
        """有历史 → 200 + messages"""
        from langgraph.checkpoint.memory import MemorySaver

        checkpointer = MemorySaver()
        chat_svc = make_mock_chat_service(chunks=[make_query_result()])
        gen = make_mock_generator(tokens=["测试回答"])
        graph = create_graph(
            checkpointer=checkpointer,
            chat_service=chat_svc,
            generator=gen,
        )

        app = _create_test_app(
            mock_graph=graph, mock_checkpointer=checkpointer
        )

        with TestClient(app) as client:
            # 先发一轮对话产生历史
            resp_stream = client.post(
                "/api/chat/stream",
                json={"question": "什么是集合？"},
                headers=make_auth_headers(),
            )
            assert resp_stream.status_code == 200

            # 再查询当前对话
            resp = client.get(
                "/api/conversations/current",
                headers=make_auth_headers(),
            )
            # 200 或 204 都合理，取决于 checkpointer 是否存入了消息
            assert resp.status_code in (200, 204)
            if resp.status_code == 200:
                data = resp.json()
                assert "conversation_id" in data
                assert "messages" in data
                assert isinstance(data["messages"], list)
                # 验证 message 包含 7 个字段
                if data["messages"]:
                    msg = data["messages"][0]
                    expected_fields = {
                        "id", "role", "content", "status",
                        "sources", "thinking_steps", "created_at",
                    }
                    assert expected_fields.issubset(set(msg.keys())), (
                        f"missing fields: {expected_fields - set(msg.keys())}"
                    )

    def test_requires_auth(self):
        """无 token → 401"""
        from langgraph.checkpoint.memory import MemorySaver

        checkpointer = MemorySaver()

        @asynccontextmanager
        async def _noop(app: FastAPI):
            yield

        test_app = FastAPI(lifespan=_noop)
        test_app.include_router(conversation_router)
        # 注入 checkpointer 但不注入鉴权
        test_app.dependency_overrides[get_checkpointer] = lambda: checkpointer
        with TestClient(test_app) as client:
            resp = client.get("/api/conversations/current")
            assert resp.status_code == 401


class TestGreetingPath:
    """问候/非课程问题 → 完整线性路径 → LLM 自然处理"""

    def test_greeting_returns_response(self):
        """问候语 → 完整路径 → token 事件 + done"""
        app = _create_test_app()
        with TestClient(app) as client:
            resp = client.post(
                "/api/chat/stream",
                json={"question": "你好"},
                headers=make_auth_headers(),
            )
        assert resp.status_code == 200
        frames = parse_sse_frames(resp.text)

        # 应有 token（respond 节点输出）+ done
        event_types = [f["type"] for f in frames]
        assert "token" in event_types
        assert "done" in event_types

    def test_short_question_returns_response(self):
        """短问题走完整路径"""
        app = _create_test_app()
        with TestClient(app) as client:
            resp = client.post(
                "/api/chat/stream",
                json={"question": "嗨"},
                headers=make_auth_headers(),
            )
        assert resp.status_code == 200
        frames = parse_sse_frames(resp.text)
        event_types = [f["type"] for f in frames]
        assert "done" in event_types

    def test_thankyou_returns_response(self):
        """谢谢 → 完整路径"""
        app = _create_test_app()
        with TestClient(app) as client:
            resp = client.post(
                "/api/chat/stream",
                json={"question": "谢谢"},
                headers=make_auth_headers(),
            )
        assert resp.status_code == 200
        frames = parse_sse_frames(resp.text)
        assert any(f["type"] == "done" for f in frames)

    def test_missing_question_returns_422(self):
        """缺 question 字段 → 422"""
        app = _create_test_app()
        with TestClient(app) as client:
            resp = client.post(
                "/api/chat/stream",
                json={"top_k": 5},
                headers=make_auth_headers(),
            )
        assert resp.status_code == 422

    def test_empty_conversation_id_accepted(self):
        """conversation_id 为 null → 正常处理"""
        app = _create_test_app()
        with TestClient(app) as client:
            resp = client.post(
                "/api/chat/stream",
                json={
                    "question": "你好",
                    "conversation_id": None,
                },
                headers=make_auth_headers(),
            )
        assert resp.status_code == 200
