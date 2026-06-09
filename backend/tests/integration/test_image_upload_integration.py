"""R019 图片上传/访问/删除 — Docker 集成测试（13 tests）

纯 HTTP 层测试，不需要 LLM/VLM。
"""

from __future__ import annotations

import os

import pytest
import pytest_asyncio

from .conftest import FAKE_JPEG, FAKE_PNG, FAKE_WEBP

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


# ===================================================================
# 上传成功（参数化 jpg/png/webp）
# ===================================================================


@pytest.mark.parametrize(
    "name,content,mime,ext",
    [
        ("test.jpg", FAKE_JPEG, "image/jpeg", "jpg"),
        ("test.png", FAKE_PNG, "image/png", "png"),
        ("test.webp", FAKE_WEBP, "image/webp", "webp"),
    ],
)
async def test_upload_success(
    async_client, auth_headers, user_id, name, content, mime, ext
):
    resp = await async_client.post(
        "/api/chat/upload",
        files={"file": (name, content, mime)},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["image_id"], "image_id should be non-empty"
    assert data["url"].startswith(f"/api/uploads/{user_id}/")
    assert data["url"].endswith(f".{ext}")


# ===================================================================
# 上传校验
# ===================================================================


async def test_upload_unsupported_type_400(async_client, auth_headers):
    resp = await async_client.post(
        "/api/chat/upload",
        files={"file": ("doc.pdf", b"fake pdf", "application/pdf")},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "不支持的文件类型" in resp.json()["detail"]


async def test_upload_oversized_400(async_client, auth_headers):
    big = FAKE_JPEG + b"\x00" * (10 * 1024 * 1024 + 1)  # >10MB
    resp = await async_client.post(
        "/api/chat/upload",
        files={"file": ("big.jpg", big, "image/jpeg")},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "文件大小超过限制" in resp.json()["detail"]


async def test_upload_no_auth_401(async_client):
    resp = await async_client.post(
        "/api/chat/upload",
        files={"file": ("test.jpg", FAKE_JPEG, "image/jpeg")},
    )
    assert resp.status_code == 401


# ===================================================================
# 图片访问（鉴权 + Cache-Control）
# ===================================================================


async def test_serve_image_with_auth(
    async_client, auth_headers, user_id, uploaded_image
):
    resp = await async_client.get(uploaded_image["url"], headers=auth_headers)
    assert resp.status_code == 200
    cache = resp.headers.get("cache-control", "")
    assert "private" in cache
    assert "max-age=3600" in cache
    assert resp.headers.get("content-type", "").startswith("image/")


async def test_serve_image_no_auth_401(
    async_client, uploaded_image
):
    resp = await async_client.get(uploaded_image["url"])
    assert resp.status_code == 401


async def test_serve_image_wrong_user_404(
    async_client, other_headers, uploaded_image
):
    resp = await async_client.get(uploaded_image["url"], headers=other_headers)
    assert resp.status_code == 404


# ===================================================================
# 删除图片
# ===================================================================


async def test_delete_image_success(
    async_client, auth_headers, user_id
):
    # 上传
    upload_resp = await async_client.post(
        "/api/chat/upload",
        files={"file": ("test.jpg", FAKE_JPEG, "image/jpeg")},
        headers=auth_headers,
    )
    data = upload_resp.json()

    # 删除
    del_resp = await async_client.delete(
        f"/api/chat/upload/{data['image_id']}", headers=auth_headers
    )
    assert del_resp.status_code == 200

    # 再访问 → 404
    get_resp = await async_client.get(data["url"], headers=auth_headers)
    assert get_resp.status_code == 404


async def test_delete_nonexistent_image_404(async_client, auth_headers):
    fake_id = "0" * 32
    resp = await async_client.delete(
        f"/api/chat/upload/{fake_id}", headers=auth_headers
    )
    assert resp.status_code == 404


async def test_delete_other_users_image_404(
    async_client, auth_headers, other_headers
):
    # user-9527 上传
    upload_resp = await async_client.post(
        "/api/chat/upload",
        files={"file": ("test.jpg", FAKE_JPEG, "image/jpeg")},
        headers=auth_headers,
    )
    image_id = upload_resp.json()["image_id"]

    # other-user 尝试删除 → 404
    resp = await async_client.delete(
        f"/api/chat/upload/{image_id}", headers=other_headers
    )
    assert resp.status_code == 404

    # 清理
    await async_client.delete(
        f"/api/chat/upload/{image_id}", headers=auth_headers
    )


# ===================================================================
# 边界：超过 3 张图片上限 → 422
# ===================================================================


async def test_stream_exceeds_max_images_422(
    async_client, auth_headers, uploaded_image
):
    """发送 4 张图片引用 → Pydantic 校验拒绝 422"""
    img = uploaded_image
    resp = await async_client.post(
        "/api/chat/stream",
        json={
            "question": "请识别",
            "images": [
                {"url": img["url"], "image_id": img["image_id"]},
                {"url": img["url"], "image_id": img["image_id"]},
                {"url": img["url"], "image_id": img["image_id"]},
                {"url": img["url"], "image_id": img["image_id"]},
            ],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 422
