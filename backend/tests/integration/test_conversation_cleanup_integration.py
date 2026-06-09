"""R019 对话删除 + 图片清理 — Docker 集成测试（3 tests）

需要 LLM 后端可用（会创建真实对话）。
"""

from __future__ import annotations

import pytest

from .conftest import FAKE_JPEG, read_sse_stream, cleanup_conversation

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_delete_conversation_cleans_up_images(
    async_client, auth_headers, user_id
):
    """上传图片 → stream 含 images → 删除对话 → GET 图片 404"""
    # 1. 上传图片
    upload_resp = await async_client.post(
        "/api/chat/upload",
        files={"file": ("test.jpg", FAKE_JPEG, "image/jpeg")},
        headers=auth_headers,
    )
    data = upload_resp.json()

    try:
        # 2. SSE stream（含图片）
        frames = await read_sse_stream(
            async_client,
            "/api/chat/stream",
            {
                "question": "请识别这张图片",
                "images": [{"url": data["url"], "image_id": data["image_id"]}],
            },
            auth_headers,
            timeout=120.0,
        )
        event_types = [f["type"] for f in frames]
        assert "done" in event_types

        # 3. 获取 conversation_id
        init_frame = next((f for f in frames if f["type"] == "init"), None)
        assert init_frame and init_frame["data"]
        conv_id = init_frame["data"]["conversation_id"]

        # 4. 删除对话
        del_resp = await async_client.delete(
            f"/api/conversations/{conv_id}", headers=auth_headers
        )
        assert del_resp.status_code == 204

        # 5. 验证图片文件已被删除 → GET 返回 404
        get_resp = await async_client.get(data["url"], headers=auth_headers)
        assert get_resp.status_code == 404
    except Exception:
        # 异常时也尝试清理
        try:
            await async_client.delete(
                f"/api/chat/upload/{data['image_id']}", headers=auth_headers
            )
        except Exception:
            pass
        raise


async def test_delete_conversation_no_images(async_client, auth_headers):
    """无图片对话删除 → 204"""
    frames = await read_sse_stream(
        async_client,
        "/api/chat/stream",
        {"question": "什么是函数？"},
        auth_headers,
    )

    event_types = [f["type"] for f in frames]
    assert "done" in event_types

    init_frame = next((f for f in frames if f["type"] == "init"), None)
    assert init_frame and init_frame["data"]
    conv_id = init_frame["data"]["conversation_id"]

    try:
        del_resp = await async_client.delete(
            f"/api/conversations/{conv_id}", headers=auth_headers
        )
        assert del_resp.status_code == 204
    finally:
        await cleanup_conversation(async_client, conv_id, auth_headers)


async def test_delete_other_users_conversation_404(
    async_client, auth_headers, other_headers
):
    """user-9527 创建对话 → other-user 删除 → 404"""
    frames = await read_sse_stream(
        async_client,
        "/api/chat/stream",
        {"question": "什么是导数？"},
        auth_headers,
    )

    init_frame = next((f for f in frames if f["type"] == "init"), None)
    assert init_frame and init_frame["data"]
    conv_id = init_frame["data"]["conversation_id"]

    try:
        # other-user 尝试删除 → 404
        del_resp = await async_client.delete(
            f"/api/conversations/{conv_id}", headers=other_headers
        )
        assert del_resp.status_code == 404
    finally:
        await cleanup_conversation(async_client, conv_id, auth_headers)
