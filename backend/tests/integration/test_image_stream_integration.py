"""R019 SSE + VLM 识别 — Docker 集成测试（4 tests）

需要 LLM 后端可用。T16 (vlm) 额外需要 DashScope VLM API。
"""

from __future__ import annotations

import pytest

from .conftest import FAKE_JPEG, read_sse_stream, cleanup_conversation, TEST_USER_ID

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_stream_with_nonexistent_image_400(async_client, auth_headers):
    """引用不存在的图片 → 400"""
    resp = await async_client.post(
        "/api/chat/stream",
        json={
            "question": "这道题怎么做",
            "images": [
                {"url": f"/api/uploads/{TEST_USER_ID}/nonexistent.jpg", "image_id": "fake"}
            ],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "图片不存在" in resp.json()["detail"]


async def test_stream_without_images_zero_impact(async_client, auth_headers):
    """无图片 → 200 + SSE done（验证不引入回归）"""
    frames = await read_sse_stream(
        async_client,
        "/api/chat/stream",
        {"question": "什么是集合？"},
        auth_headers,
    )

    event_types = [f["type"] for f in frames]
    assert "done" in event_types, f"SSE 流未收到 done 事件，收到: {event_types}"

    # 清理对话
    init_frame = next((f for f in frames if f["type"] == "init"), None)
    if init_frame and init_frame["data"]:
        conv_id = init_frame["data"].get("conversation_id")
        if conv_id:
            await cleanup_conversation(async_client, conv_id, auth_headers)


@pytest.mark.vlm
async def test_stream_with_uploaded_image_vlm_path(async_client, auth_headers):
    """上传图片 → stream 含 images → SSE 包含 recognizing 状态 + done"""
    # 1. 上传图片
    upload_resp = await async_client.post(
        "/api/chat/upload",
        files={"file": ("test.jpg", FAKE_JPEG, "image/jpeg")},
        headers=auth_headers,
    )
    assert upload_resp.status_code == 200
    data = upload_resp.json()

    try:
        # 2. SSE stream
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
        assert "done" in event_types, f"SSE 流未收到 done 事件，收到: {event_types}"

        # 验证 recognizing 状态事件（VLM 降级也会走这个分支）
        status_frames = [f for f in frames if f["type"] == "status"]
        status_stages = [
            f["data"].get("stage", "") for f in status_frames if f["data"]
        ]
        assert (
            "recognizing" in status_stages
        ), f"未收到 recognizing 状态，收到: {status_stages}"

        # 3. 清理对话
        init_frame = next((f for f in frames if f["type"] == "init"), None)
        if init_frame and init_frame["data"]:
            conv_id = init_frame["data"].get("conversation_id")
            if conv_id:
                await cleanup_conversation(async_client, conv_id, auth_headers)
    finally:
        # 清理图片
        try:
            await async_client.delete(
                f"/api/chat/upload/{data['image_id']}", headers=auth_headers
            )
        except Exception:
            pass


async def test_stream_image_reference_integrity(async_client, auth_headers):
    """上传 → 删除图片 → 引用已删除图片 → 400"""
    # 1. 上传
    upload_resp = await async_client.post(
        "/api/chat/upload",
        files={"file": ("test.jpg", FAKE_JPEG, "image/jpeg")},
        headers=auth_headers,
    )
    data = upload_resp.json()

    # 2. 删除
    await async_client.delete(
        f"/api/chat/upload/{data['image_id']}", headers=auth_headers
    )

    # 3. 引用已删除的图片 → 400
    resp = await async_client.post(
        "/api/chat/stream",
        json={
            "question": "请识别",
            "images": [{"url": data["url"], "image_id": data["image_id"]}],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "图片不存在" in resp.json()["detail"]
