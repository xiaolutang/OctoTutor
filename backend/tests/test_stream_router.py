"""SSE 流式路由集成测试

5 组测试覆盖：响应格式、事件序列、断线检测、异常兜底、非流式兼容
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import MagicMock

import pytest
from starlette.testclient import TestClient

from app.chat.schemas import StreamEvent, StatusPayload
from app.chat.errors import ChatErrorCode, make_error
from app.domain.models import SourceReference


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

def _make_source(chunk_id: str = "book::sec::p1_s0::child") -> SourceReference:
    return SourceReference(
        chunk_id=chunk_id,
        book="必修第一册",
        section="1.1 集合",
        page_start=1,
        page_end=2,
    )


async def _normal_stream(question: str, top_k: int) -> AsyncIterator[StreamEvent]:
    """模拟正常事件序列：status -> sources -> status -> token -> done"""
    yield StreamEvent(type="status", data=StatusPayload(stage="retrieving", message="正在检索教材..."))
    yield StreamEvent(type="sources", data=[_make_source()])
    yield StreamEvent(type="status", data=StatusPayload(stage="generating", message="正在生成回答..."))
    yield StreamEvent(type="token", data="你好")
    yield StreamEvent(type="done", data=None)


@pytest.fixture()
def mock_service():
    """创建 mock ChatService，默认返回正常事件序列"""
    svc = MagicMock()
    svc.stream_chat = MagicMock(return_value=_normal_stream("", 10))
    return svc


@pytest.fixture()
def client(mock_service):
    """TestClient，使用空 lifespan 绕过 ChromaDB 初始化"""
    from fastapi import FastAPI
    from app.chat.router import router as chat_router
    from app.chat.stream_router import router as stream_router
    from app.chat.dependencies import get_chat_service

    @asynccontextmanager
    async def _noop_lifespan(app: FastAPI):
        yield

    test_app = FastAPI(lifespan=_noop_lifespan)
    test_app.include_router(chat_router)
    test_app.include_router(stream_router)
    test_app.dependency_overrides[get_chat_service] = lambda: mock_service

    with TestClient(test_app) as c:
        yield c

    test_app.dependency_overrides.clear()


# ------------------------------------------------------------------
# 1. SSE 响应格式
# ------------------------------------------------------------------

def test_sse_response_format(client: TestClient):
    """验证返回 content-type 为 text/event-stream"""
    resp = client.post(
        "/api/chat/stream",
        json={"question": "什么是集合？", "top_k": 5},
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]


# ------------------------------------------------------------------
# 2. 事件序列
# ------------------------------------------------------------------

def test_event_sequence(client: TestClient):
    """验证 SSE 文本格式正确，包含完整事件序列"""
    resp = client.post(
        "/api/chat/stream",
        json={"question": "什么是集合？", "top_k": 5},
    )
    text = resp.text

    # 解析 SSE 帧
    frames = [f.strip() for f in text.split("\n\n") if f.strip()]

    # 应有 5 帧：status, sources, status, token, done
    assert len(frames) == 5

    # 验证第一帧是 status
    lines = frames[0].split("\n")
    assert lines[0] == "event: status"
    payload = json.loads(lines[1].replace("data: ", ""))
    assert payload["stage"] == "retrieving"

    # 验证第二帧是 sources（list[SourceReference]）
    lines = frames[1].split("\n")
    assert lines[0] == "event: sources"
    payload = json.loads(lines[1].replace("data: ", ""))
    assert isinstance(payload, list)
    assert payload[0]["chunk_id"] == "book::sec::p1_s0::child"

    # 验证 token 帧
    lines = frames[3].split("\n")
    assert lines[0] == "event: token"
    payload = json.loads(lines[1].replace("data: ", ""))
    assert payload == "你好"

    # 验证 done 帧
    lines = frames[4].split("\n")
    assert lines[0] == "event: done"
    payload = json.loads(lines[1].replace("data: ", ""))
    assert payload is None


# ------------------------------------------------------------------
# 3. 断线检测 — 不输出 error event
# ------------------------------------------------------------------

def test_disconnect_no_error(client: TestClient, mock_service):
    """断线时 break，不输出 error event"""

    async def _stream_disconnect(question, top_k):
        yield StreamEvent(type="status", data=StatusPayload(stage="retrieving", message="检索中..."))
        yield StreamEvent(type="status", data=StatusPayload(stage="retrieving", message="继续..."))

    mock_service.stream_chat = MagicMock(return_value=_stream_disconnect("", 10))

    # monkeypatch Request.is_disconnected 使其始终返回 True
    from starlette.requests import Request as StarletteRequest

    async def _always_disconnected(self):
        return True

    original = StarletteRequest.is_disconnected
    StarletteRequest.is_disconnected = _always_disconnected

    try:
        resp = client.post(
            "/api/chat/stream",
            json={"question": "测试断线", "top_k": 5},
        )
        text = resp.text.strip()

        # 断线后不应有 error 事件
        assert "event: error" not in text
    finally:
        StarletteRequest.is_disconnected = original


# ------------------------------------------------------------------
# 4. 异常兜底 — INTERNAL_ERROR
# ------------------------------------------------------------------

def test_internal_error_fallback(client: TestClient, mock_service):
    """stream_chat 抛异常时 yield INTERNAL_ERROR error event"""

    async def _stream_error(question, top_k):
        raise RuntimeError("unexpected boom")
        yield  # noqa: unreachable — 让函数变成 async generator

    mock_service.stream_chat = MagicMock(return_value=_stream_error("", 10))

    resp = client.post(
        "/api/chat/stream",
        json={"question": "测试异常", "top_k": 5},
    )
    assert resp.status_code == 200
    text = resp.text.strip()

    assert "event: error" in text

    # 解析 error 帧
    lines = text.split("\n")
    event_line = [l for l in lines if l.startswith("event: error")]
    data_line = [l for l in lines if l.startswith("data: ")]
    assert len(event_line) == 1
    assert len(data_line) == 1

    payload = json.loads(data_line[0].replace("data: ", ""))
    expected = make_error(ChatErrorCode.INTERNAL_ERROR)
    assert payload["code"] == expected["code"]
    assert payload["message"] == expected["message"]
    assert payload["action"] == expected["action"]


# ------------------------------------------------------------------
# 5. 非流式接口仍然正常
# ------------------------------------------------------------------

def test_non_stream_chat_still_works(client: TestClient, mock_service):
    """POST /api/chat 非流式接口不受影响"""
    mock_service.handle_chat = MagicMock(return_value=None)

    resp = client.post(
        "/api/chat",
        json={"question": "什么是集合？", "top_k": 5},
    )
    # handle_chat 返回 None -> 404
    assert resp.status_code == 404
