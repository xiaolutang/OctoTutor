"""R019 图片上传集成测试

覆盖完整链路：
1. POST /api/chat/upload — 上传图片（鉴权、类型校验、大小校验）
2. GET /api/uploads/{user_id}/{filename} — 鉴权图片访问（归属校验）
3. DELETE /api/chat/upload/{image_id} — 删除图片（归属校验）
4. POST /api/chat/stream（含 images）— 图片校验、VLM 降级
"""

from __future__ import annotations

import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from jose import jwt

from app.middleware.auth import ALGORITHM

# ---------------------------------------------------------------------------
# 测试辅助
# ---------------------------------------------------------------------------

TEST_SECRET = "test-jwt-secret-key"


def _make_token(sub: str = "user-001") -> str:
    return jwt.encode(
        {"sub": sub, "client_id": "testuser", "exp": 9999999999, "type": "access"},
        TEST_SECRET,
        algorithm=ALGORITHM,
    )


def _auth_headers(token: str | None = None) -> dict:
    return {"Authorization": f"Bearer {token or _make_token()}"}


def _fake_jpeg() -> bytes:
    """最小合法 JPEG 头"""
    return b"\xff\xd8\xff\xe0" + b"\x00" * 100


def _fake_png() -> bytes:
    """最小合法 PNG 头"""
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * 100


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    """TestClient with mocked dependencies + real ImageManager"""
    from langgraph.checkpoint.memory import MemorySaver

    from app.main import app
    from app.infra.image_manager import ImageManager
    from app.chat.dependencies import get_graph, get_checkpointer, get_db

    # 使用临时目录作为 upload_dir，测试结束自动清理
    tmpdir = tempfile.mkdtemp()
    image_manager = ImageManager(upload_dir=tmpdir, max_storage_mb=100)

    # Mock Graph + Generator
    mock_gen = MagicMock()
    mock_gen.generate_title = AsyncMock(return_value=None)
    mock_gen.get_chat_model.return_value = MagicMock()

    checkpointer = MemorySaver()
    graph_mock = MagicMock()

    # app.state 注入
    app.state.image_manager = image_manager
    app.state.generator = mock_gen
    app.state.recognition_provider = MagicMock()
    app.state.vector_store = MagicMock()
    app.state.embedding_service = MagicMock()

    # dependency_overrides
    app.dependency_overrides[get_graph] = lambda: graph_mock
    app.dependency_overrides[get_checkpointer] = lambda: checkpointer

    mock_db = AsyncMock()
    async def _override_get_db():
        yield mock_db
    app.dependency_overrides[get_db] = _override_get_db

    with patch("app.middleware.auth.settings") as mock_settings:
        mock_settings.auth_jwt_secret = TEST_SECRET
        tc = TestClient(app)
        yield tc

    app.dependency_overrides.clear()

    # 清理临时目录
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)


# ===================================================================
# T1: POST /api/chat/upload — 正常上传
# ===================================================================


def test_upload_jpeg_success(client: TestClient):
    """上传 JPEG 图片成功，返回 image_id 和 url"""
    resp = client.post(
        "/api/chat/upload",
        files={"file": ("test.jpg", _fake_jpeg(), "image/jpeg")},
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "image_id" in data
    assert "url" in data
    assert data["url"].startswith("/api/uploads/user-001/")
    assert data["url"].endswith(".jpg")


def test_upload_png_success(client: TestClient):
    """上传 PNG 图片成功"""
    resp = client.post(
        "/api/chat/upload",
        files={"file": ("photo.png", _fake_png(), "image/png")},
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["url"].endswith(".png")


# ===================================================================
# T2: POST /api/chat/upload — 类型校验
# ===================================================================


def test_upload_unsupported_type_400(client: TestClient):
    """上传不支持的文件类型 → 400"""
    resp = client.post(
        "/api/chat/upload",
        files={"file": ("doc.pdf", b"fake pdf content", "application/pdf")},
        headers=_auth_headers(),
    )
    assert resp.status_code == 400
    assert "不支持的文件类型" in resp.json()["detail"]


# ===================================================================
# T3: POST /api/chat/upload — 无 token → 401
# ===================================================================


def test_upload_no_token_401(client: TestClient):
    """无 Authorization header → 上传返回 401"""
    resp = client.post(
        "/api/chat/upload",
        files={"file": ("test.jpg", _fake_jpeg(), "image/jpeg")},
    )
    assert resp.status_code == 401


# ===================================================================
# T4: GET /api/uploads/{user_id}/{filename} — 鉴权访问
# ===================================================================


def test_serve_image_with_auth(client: TestClient):
    """上传后带 token GET 图片 → 200"""
    # 先上传
    upload_resp = client.post(
        "/api/chat/upload",
        files={"file": ("test.jpg", _fake_jpeg(), "image/jpeg")},
        headers=_auth_headers(),
    )
    assert upload_resp.status_code == 200
    url = upload_resp.json()["url"]

    # GET 图片
    get_resp = client.get(url, headers=_auth_headers())
    assert get_resp.status_code == 200


def test_serve_image_no_token_401(client: TestClient):
    """无 token GET 图片 → 401"""
    # 先上传
    upload_resp = client.post(
        "/api/chat/upload",
        files={"file": ("test.jpg", _fake_jpeg(), "image/jpeg")},
        headers=_auth_headers(),
    )
    url = upload_resp.json()["url"]

    # 无 token 访问
    get_resp = client.get(url)
    assert get_resp.status_code == 401


def test_serve_image_wrong_user_404(client: TestClient):
    """用另一个用户的 token GET 图片 → 404"""
    # user-001 上传
    upload_resp = client.post(
        "/api/chat/upload",
        files={"file": ("test.jpg", _fake_jpeg(), "image/jpeg")},
        headers=_auth_headers(_make_token("user-001")),
    )
    url = upload_resp.json()["url"]

    # user-002 尝试访问
    get_resp = client.get(url, headers=_auth_headers(_make_token("user-002")))
    assert get_resp.status_code == 404


def test_serve_nonexistent_image_404(client: TestClient):
    """访问不存在的图片 → 404"""
    get_resp = client.get(
        "/api/uploads/user-001/nonexistent.jpg",
        headers=_auth_headers(),
    )
    assert get_resp.status_code == 404


# ===================================================================
# T5: DELETE /api/chat/upload/{image_id} — 删除
# ===================================================================


def test_delete_image_success(client: TestClient):
    """删除自己的图片 → ok"""
    upload_resp = client.post(
        "/api/chat/upload",
        files={"file": ("test.jpg", _fake_jpeg(), "image/jpeg")},
        headers=_auth_headers(),
    )
    image_id = upload_resp.json()["image_id"]

    del_resp = client.delete(f"/api/chat/upload/{image_id}", headers=_auth_headers())
    assert del_resp.status_code == 200

    # 删除后再 GET → 404
    url = upload_resp.json()["url"]
    get_resp = client.get(url, headers=_auth_headers())
    assert get_resp.status_code == 404


def test_delete_nonexistent_404(client: TestClient):
    """删除不存在的图片 → 404"""
    del_resp = client.delete(
        "/api/chat/upload/00000000000000000000000000000000",
        headers=_auth_headers(),
    )
    assert del_resp.status_code == 404


# ===================================================================
# T6: 上传 → GET → 删除 完整链路
# ===================================================================


def test_upload_serve_delete_lifecycle(client: TestClient):
    """完整生命周期：上传 → GET 200 → 删除 → GET 404"""
    token = _make_token()
    headers = _auth_headers(token)

    # 1. 上传
    upload_resp = client.post(
        "/api/chat/upload",
        files={"file": ("photo.jpg", _fake_jpeg(), "image/jpeg")},
        headers=headers,
    )
    assert upload_resp.status_code == 200
    data = upload_resp.json()
    image_id, url = data["image_id"], data["url"]

    # 2. GET 可访问
    assert client.get(url, headers=headers).status_code == 200

    # 3. 删除
    assert client.delete(f"/api/chat/upload/{image_id}", headers=headers).status_code == 200

    # 4. GET 404
    assert client.get(url, headers=headers).status_code == 404


# ===================================================================
# T7: 上传 → 发送消息（stream）含不存在的图片 → 400
# ===================================================================


def test_stream_with_nonexistent_image_400(client: TestClient):
    """stream 请求引用不存在的图片 → 400"""
    resp = client.post(
        "/api/chat/stream",
        json={
            "question": "这道题怎么做",
            "images": [{"url": "/api/uploads/user-001/fake.jpg", "image_id": "fake"}],
        },
        headers=_auth_headers(),
    )
    assert resp.status_code == 400
    assert "图片不存在" in resp.json()["detail"]


# ===================================================================
# T8: 上传 → 发送消息（stream）含存在的图片 → 200
# ===================================================================


def test_stream_with_uploaded_image_200(client: TestClient):
    """上传图片后 stream 请求引用该图片 → 200（VLM mock 降级）"""
    token = _make_token()
    headers = _auth_headers(token)

    # 上传
    upload_resp = client.post(
        "/api/chat/upload",
        files={"file": ("test.jpg", _fake_jpeg(), "image/jpeg")},
        headers=headers,
    )
    data = upload_resp.json()

    # VLM mock 抛异常 → 降级纯文字
    client.app.state.recognition_provider.recognize = AsyncMock(
        side_effect=Exception("VLM unavailable")
    )

    # stream
    resp = client.post(
        "/api/chat/stream",
        json={
            "question": "请识别这张图片",
            "images": [{"url": data["url"], "image_id": data["image_id"]}],
        },
        headers=headers,
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
