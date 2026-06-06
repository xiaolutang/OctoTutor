"""R019 图片上传集成测试

覆盖完整链路：
1. POST /api/chat/upload — 上传图片（鉴权、类型校验、大小校验）
2. GET /api/uploads/{user_id}/{filename} — 鉴权图片访问（归属校验、缓存头）
3. DELETE /api/chat/upload/{image_id} — 删除图片（归属校验）
4. POST /api/chat/stream（含 images）— 图片校验、VLM 降级/成功
"""

from __future__ import annotations

import shutil
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from jose import jwt

from app.middleware.auth import ALGORITHM

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TEST_SECRET = "test-jwt-secret-key"
TEST_TOKEN_EXP = 9999999999
FAKE_IMAGE_ID = "0" * 32  # 32-char hex placeholder
MAX_SIZE_MB = 10
MAX_SIZE_BYTES = MAX_SIZE_MB * 1024 * 1024


def _make_token(sub: str = "user-001") -> str:
    return jwt.encode(
        {"sub": sub, "client_id": "testuser", "exp": TEST_TOKEN_EXP, "type": "access"},
        TEST_SECRET,
        algorithm=ALGORITHM,
    )


def _auth_headers(token: str | None = None) -> dict:
    return {"Authorization": f"Bearer {token or _make_token()}"}


def _fake_jpeg() -> bytes:
    return b"\xff\xd8\xff\xe0" + b"\x00" * 100


def _fake_png() -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * 100


def _fake_webp() -> bytes:
    return b"RIFF" + b"\x00" * 100 + b"WEBP"


def _oversized_file() -> bytes:
    return b"\xff\xd8\xff\xe0" + b"\x00" * (MAX_SIZE_BYTES + 1)


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

    tmpdir = tempfile.mkdtemp()
    image_manager = ImageManager(upload_dir=tmpdir, max_storage_mb=100)

    mock_gen = MagicMock()
    mock_gen.generate_title = AsyncMock(return_value=None)
    mock_gen.get_chat_model.return_value = MagicMock()

    checkpointer = MemorySaver()
    graph_mock = MagicMock()

    app.state.image_manager = image_manager
    app.state.generator = mock_gen
    app.state.recognition_provider = MagicMock()
    app.state.vector_store = MagicMock()
    app.state.embedding_service = MagicMock()

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
    shutil.rmtree(tmpdir, ignore_errors=True)


# ===================================================================
# Upload — success (parameterized for jpg/png/webp)
# ===================================================================


@pytest.mark.parametrize("name,content,mime,ext", [
    ("test.jpg", _fake_jpeg(), "image/jpeg", "jpg"),
    ("test.png", _fake_png(), "image/png", "png"),
    ("test.webp", _fake_webp(), "image/webp", "webp"),
])
def test_upload_success(client: TestClient, name, content, mime, ext):
    """上传 {ext} 图片成功，返回 image_id 和 url"""
    resp = client.post(
        "/api/chat/upload",
        files={"file": (name, content, mime)},
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["image_id"], "image_id should be non-empty"
    assert data["url"].startswith("/api/uploads/user-001/")
    assert data["url"].endswith(f".{ext}")


# ===================================================================
# Upload — validation
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


def test_upload_oversized_400(client: TestClient):
    """上传超大文件（>10MB）→ 400"""
    resp = client.post(
        "/api/chat/upload",
        files={"file": ("big.jpg", _oversized_file(), "image/jpeg")},
        headers=_auth_headers(),
    )
    assert resp.status_code == 400
    assert "文件大小超过限制" in resp.json()["detail"]


def test_upload_no_token_401(client: TestClient):
    """无 Authorization header → 上传返回 401"""
    resp = client.post(
        "/api/chat/upload",
        files={"file": ("test.jpg", _fake_jpeg(), "image/jpeg")},
    )
    assert resp.status_code == 401


# ===================================================================
# Serve — authenticated access
# ===================================================================


def test_serve_image_with_auth(client: TestClient):
    """上传后带 token GET 图片 → 200 + Cache-Control"""
    upload_resp = client.post(
        "/api/chat/upload",
        files={"file": ("test.jpg", _fake_jpeg(), "image/jpeg")},
        headers=_auth_headers(),
    )
    url = upload_resp.json()["url"]

    get_resp = client.get(url, headers=_auth_headers())
    assert get_resp.status_code == 200
    assert "private" in get_resp.headers.get("cache-control", "")
    assert "max-age=3600" in get_resp.headers.get("cache-control", "")


def test_serve_image_no_token_401(client: TestClient):
    """无 token GET 图片 → 401"""
    upload_resp = client.post(
        "/api/chat/upload",
        files={"file": ("test.jpg", _fake_jpeg(), "image/jpeg")},
        headers=_auth_headers(),
    )
    url = upload_resp.json()["url"]

    assert client.get(url).status_code == 401


def test_serve_image_wrong_user_404(client: TestClient):
    """用另一个用户的 token GET 图片 → 404"""
    upload_resp = client.post(
        "/api/chat/upload",
        files={"file": ("test.jpg", _fake_jpeg(), "image/jpeg")},
        headers=_auth_headers(_make_token("user-001")),
    )
    url = upload_resp.json()["url"]

    assert client.get(url, headers=_auth_headers(_make_token("user-002"))).status_code == 404


def test_serve_nonexistent_image_404(client: TestClient):
    """访问不存在的图片 → 404"""
    assert client.get(
        "/api/uploads/user-001/nonexistent.jpg", headers=_auth_headers()
    ).status_code == 404


# ===================================================================
# Delete
# ===================================================================


def test_delete_image_success(client: TestClient):
    """删除自己的图片 → ok，之后再 GET → 404"""
    upload_resp = client.post(
        "/api/chat/upload",
        files={"file": ("test.jpg", _fake_jpeg(), "image/jpeg")},
        headers=_auth_headers(),
    )
    image_id = upload_resp.json()["image_id"]
    url = upload_resp.json()["url"]

    assert client.delete(f"/api/chat/upload/{image_id}", headers=_auth_headers()).status_code == 200
    assert client.get(url, headers=_auth_headers()).status_code == 404


def test_delete_nonexistent_404(client: TestClient):
    """删除不存在的图片 → 404"""
    assert client.delete(
        f"/api/chat/upload/{FAKE_IMAGE_ID}", headers=_auth_headers()
    ).status_code == 404


def test_delete_other_users_image_404(client: TestClient):
    """用户 A 删除用户 B 的图片 → 404"""
    # user-001 上传
    upload_resp = client.post(
        "/api/chat/upload",
        files={"file": ("test.jpg", _fake_jpeg(), "image/jpeg")},
        headers=_auth_headers(_make_token("user-001")),
    )
    image_id = upload_resp.json()["image_id"]

    # user-002 尝试删除
    assert client.delete(
        f"/api/chat/upload/{image_id}",
        headers=_auth_headers(_make_token("user-002")),
    ).status_code == 404


# ===================================================================
# Stream with images
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


def test_stream_with_uploaded_image_vlm_failure(client: TestClient):
    """VLM 失败降级纯文字 → 200"""
    token = _make_token()
    headers = _auth_headers(token)

    upload_resp = client.post(
        "/api/chat/upload",
        files={"file": ("test.jpg", _fake_jpeg(), "image/jpeg")},
        headers=headers,
    )
    data = upload_resp.json()

    client.app.state.recognition_provider.recognize = AsyncMock(
        side_effect=Exception("VLM unavailable")
    )

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


def test_stream_with_uploaded_image_vlm_success(client: TestClient):
    """VLM 识别成功 → 200 + recognizing SSE 事件"""
    token = _make_token()
    headers = _auth_headers(token)

    upload_resp = client.post(
        "/api/chat/upload",
        files={"file": ("test.jpg", _fake_jpeg(), "image/jpeg")},
        headers=headers,
    )
    data = upload_resp.json()

    client.app.state.recognition_provider.recognize = AsyncMock(
        return_value="这是一道数学题"
    )

    resp = client.post(
        "/api/chat/stream",
        json={
            "question": "请识别这张图片",
            "images": [{"url": data["url"], "image_id": data["image_id"]}],
        },
        headers=headers,
    )
    assert resp.status_code == 200

    # SSE 流应包含 recognizing status 事件
    body = resp.text
    assert "recognizing" in body
