"""R019 图片上传集成测试

覆盖完整链路：
1. POST /api/chat/upload — 上传图片（鉴权、类型校验、大小校验）
2. GET /api/uploads/{user_id}/{filename} — 鉴权图片访问（归属校验、缓存头）
3. DELETE /api/chat/upload/{image_id} — 删除图片（归属校验）
4. POST /api/chat/stream（含 images）— 图片校验、VLM 降级/成功
"""

from __future__ import annotations

import os
import shutil
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.chat.dependencies import get_checkpointer
from tests._helpers import (
    FAKE_JPEG,
    FAKE_PNG,
    FAKE_WEBP,
    TEST_SECRET,
    make_auth_headers,
    make_mock_msg,
    make_token,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FAKE_IMAGE_ID = "0" * 32  # 32-char hex placeholder
MAX_SIZE_MB = 10
MAX_SIZE_BYTES = MAX_SIZE_MB * 1024 * 1024


OVERSIZED_FILE = b"\xff\xd8\xff\xe0" + b"\x00" * (MAX_SIZE_BYTES + 1)


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
    ("test.jpg", FAKE_JPEG, "image/jpeg", "jpg"),
    ("test.png", FAKE_PNG, "image/png", "png"),
    ("test.webp", FAKE_WEBP, "image/webp", "webp"),
])
def test_upload_success(client: TestClient, name, content, mime, ext):
    """上传 {ext} 图片成功，返回 image_id 和 url"""
    resp = client.post(
        "/api/chat/upload",
        files={"file": (name, content, mime)},
        headers=make_auth_headers(),
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
        headers=make_auth_headers(),
    )
    assert resp.status_code == 400
    assert "不支持的文件类型" in resp.json()["detail"]


def test_upload_oversized_400(client: TestClient):
    """上传超大文件（>10MB）→ 400"""
    resp = client.post(
        "/api/chat/upload",
        files={"file": ("big.jpg", OVERSIZED_FILE, "image/jpeg")},
        headers=make_auth_headers(),
    )
    assert resp.status_code == 400
    assert "文件大小超过限制" in resp.json()["detail"]


def test_upload_no_token_401(client: TestClient):
    """无 Authorization header → 上传返回 401"""
    resp = client.post(
        "/api/chat/upload",
        files={"file": ("test.jpg", FAKE_JPEG, "image/jpeg")},
    )
    assert resp.status_code == 401


# ===================================================================
# Serve — authenticated access
# ===================================================================


def test_serve_image_with_auth(client: TestClient):
    """上传后带 token GET 图片 → 200 + Cache-Control"""
    upload_resp = client.post(
        "/api/chat/upload",
        files={"file": ("test.jpg", FAKE_JPEG, "image/jpeg")},
        headers=make_auth_headers(),
    )
    url = upload_resp.json()["url"]

    get_resp = client.get(url, headers=make_auth_headers())
    assert get_resp.status_code == 200
    assert "private" in get_resp.headers.get("cache-control", "")
    assert "max-age=3600" in get_resp.headers.get("cache-control", "")


def test_serve_image_no_token_401(client: TestClient):
    """无 token GET 图片 → 401"""
    upload_resp = client.post(
        "/api/chat/upload",
        files={"file": ("test.jpg", FAKE_JPEG, "image/jpeg")},
        headers=make_auth_headers(),
    )
    url = upload_resp.json()["url"]

    assert client.get(url).status_code == 401


def test_serve_image_wrong_user_404(client: TestClient):
    """用另一个用户的 token GET 图片 → 404"""
    upload_resp = client.post(
        "/api/chat/upload",
        files={"file": ("test.jpg", FAKE_JPEG, "image/jpeg")},
        headers=make_auth_headers(make_token("user-001")),
    )
    url = upload_resp.json()["url"]

    assert client.get(url, headers=make_auth_headers(make_token("user-002"))).status_code == 404


def test_serve_nonexistent_image_404(client: TestClient):
    """访问不存在的图片 → 404"""
    assert client.get(
        "/api/uploads/user-001/nonexistent.jpg", headers=make_auth_headers()
    ).status_code == 404


# ===================================================================
# Delete
# ===================================================================


def test_delete_image_success(client: TestClient):
    """删除自己的图片 → ok，之后再 GET → 404"""
    upload_resp = client.post(
        "/api/chat/upload",
        files={"file": ("test.jpg", FAKE_JPEG, "image/jpeg")},
        headers=make_auth_headers(),
    )
    image_id = upload_resp.json()["image_id"]
    url = upload_resp.json()["url"]

    assert client.delete(f"/api/chat/upload/{image_id}", headers=make_auth_headers()).status_code == 200
    assert client.get(url, headers=make_auth_headers()).status_code == 404


def test_delete_nonexistent_404(client: TestClient):
    """删除不存在的图片 → 404"""
    assert client.delete(
        f"/api/chat/upload/{FAKE_IMAGE_ID}", headers=make_auth_headers()
    ).status_code == 404


def test_delete_other_users_image_404(client: TestClient):
    """用户 A 删除用户 B 的图片 → 404"""
    # user-001 上传
    upload_resp = client.post(
        "/api/chat/upload",
        files={"file": ("test.jpg", FAKE_JPEG, "image/jpeg")},
        headers=make_auth_headers(make_token("user-001")),
    )
    image_id = upload_resp.json()["image_id"]

    # user-002 尝试删除
    assert client.delete(
        f"/api/chat/upload/{image_id}",
        headers=make_auth_headers(make_token("user-002")),
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
        headers=make_auth_headers(),
    )
    assert resp.status_code == 400
    assert "图片不存在" in resp.json()["detail"]


def test_stream_with_uploaded_image_vlm_failure(client: TestClient):
    """VLM 失败降级纯文字 → 200"""
    token = make_token()
    headers = make_auth_headers(token)

    upload_resp = client.post(
        "/api/chat/upload",
        files={"file": ("test.jpg", FAKE_JPEG, "image/jpeg")},
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
    token = make_token()
    headers = make_auth_headers(token)

    upload_resp = client.post(
        "/api/chat/upload",
        files={"file": ("test.jpg", FAKE_JPEG, "image/jpeg")},
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


# ===================================================================
# BB002: Stream without images — regression (零影响)
# ===================================================================


def test_stream_without_images_zero_impact(client: TestClient):
    """无图片时 stream 行为与 R019 前一致"""
    resp = client.post(
        "/api/chat/stream",
        json={"question": "什么是集合？"},
        headers=make_auth_headers(),
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]


# ===================================================================
# BB001: Upload edge cases — ext normalization + save failure
# ===================================================================


def test_upload_jpeg_ext_normalized_to_jpg(client: TestClient):
    """上传 .jpeg 文件扩展名规范化为 .jpg"""
    resp = client.post(
        "/api/chat/upload",
        files={"file": ("photo.jpeg", FAKE_JPEG, "image/jpeg")},
        headers=make_auth_headers(),
    )
    assert resp.status_code == 200
    assert resp.json()["url"].endswith(".jpg")


def test_upload_no_ext_fallback_png(client: TestClient):
    """文件名无扩展名时 fallback 为 .png"""
    resp = client.post(
        "/api/chat/upload",
        files={"file": ("photo", FAKE_PNG, "image/png")},
        headers=make_auth_headers(),
    )
    assert resp.status_code == 200
    assert resp.json()["url"].endswith(".png")


def test_upload_save_failure_500(client: TestClient):
    """image_manager.save 异常时返回 500"""
    with patch.object(
        client.app.state.image_manager, "save",
        new_callable=AsyncMock, side_effect=OSError("disk full"),
    ):
        resp = client.post(
            "/api/chat/upload",
            files={"file": ("test.jpg", FAKE_JPEG, "image/jpeg")},
            headers=make_auth_headers(),
        )
    assert resp.status_code == 500


# ===================================================================
# BB003: delete_conversation 图片清理集成测试
# ===================================================================


def test_delete_conversation_cleans_up_images(client: TestClient):
    """删除含图片对话 → 关联图片文件从磁盘删除"""
    # 1. 上传图片
    upload_resp = client.post(
        "/api/chat/upload",
        files={"file": ("test.jpg", FAKE_JPEG, "image/jpeg")},
        headers=make_auth_headers(),
    )
    data = upload_resp.json()
    image_id = data["image_id"]
    url = data["url"]

    # 2. 验证文件存在
    image_manager = client.app.state.image_manager
    filepath = image_manager.resolve_filepath(url, "user-001")
    assert os.path.isfile(filepath)

    # 3. Mock load_conversation_by_id 返回含图片引用的消息
    conv_id = "test-conv-with-images"
    mock_msg = make_mock_msg(
        id="msg-img-1", content="请识别这张图片",
        additional_kwargs={"images": [{"url": url, "image_id": image_id}]},
    )

    with patch(
        "app.chat.conversation_router.ConversationRepo.delete_by_id",
        new_callable=AsyncMock, return_value=True,
    ), patch(
        "app.chat.conversation_router.load_conversation_by_id",
        new_callable=AsyncMock, return_value=[mock_msg],
    ):
        resp = client.delete(f"/api/conversations/{conv_id}", headers=make_auth_headers())

    assert resp.status_code == 204
    # 4. 验证图片文件已被删除
    assert not os.path.exists(filepath)


def test_delete_conversation_without_images(client: TestClient):
    """删除无图片对话 → 无报错"""
    conv_id = "test-conv-no-images"
    mock_msg = make_mock_msg(id="msg-plain", content="普通消息")

    with patch(
        "app.chat.conversation_router.ConversationRepo.delete_by_id",
        new_callable=AsyncMock, return_value=True,
    ), patch(
        "app.chat.conversation_router.load_conversation_by_id",
        new_callable=AsyncMock, return_value=[mock_msg],
    ):
        resp = client.delete(f"/api/conversations/{conv_id}", headers=make_auth_headers())

    assert resp.status_code == 204


def test_delete_conversation_image_cleanup_failure_does_not_block(client: TestClient):
    """文件删除失败 → 不阻断对话删除"""
    # 1. 上传图片
    upload_resp = client.post(
        "/api/chat/upload",
        files={"file": ("test.jpg", FAKE_JPEG, "image/jpeg")},
        headers=make_auth_headers(),
    )
    data = upload_resp.json()

    # 2. Mock load_conversation_by_id 返回含图片引用的消息
    conv_id = "test-conv-cleanup-fail"
    mock_msg = make_mock_msg(
        id="msg-img-1", content="请识别这张图片",
        additional_kwargs={"images": [{"url": data["url"], "image_id": data["image_id"]}]},
    )

    # 3. 让 image_manager.delete 抛异常
    with patch(
        "app.chat.conversation_router.ConversationRepo.delete_by_id",
        new_callable=AsyncMock, return_value=True,
    ), patch(
        "app.chat.conversation_router.load_conversation_by_id",
        new_callable=AsyncMock, return_value=[mock_msg],
    ), patch.object(
        client.app.state.image_manager, "delete",
        new_callable=AsyncMock, side_effect=OSError("disk error"),
    ):
        resp = client.delete(f"/api/conversations/{conv_id}", headers=make_auth_headers())

    # 对话删除仍成功
    assert resp.status_code == 204
