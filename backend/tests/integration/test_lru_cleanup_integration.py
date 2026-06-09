"""R019 LRU 磁盘清理 — Docker 集成测试（2 tests）

需要小配额环境：在 docker-compose.local.yml 中设置
  IMAGE_MAX_STORAGE_MB=1
然后重新部署：bash deploy/deploy.sh local

运行命令：
  JWT_SECRET_KEY=xxx pytest tests/integration/test_lru_cleanup_integration.py -v -m lru
"""

from __future__ import annotations

import pytest

from .conftest import BIG_JPEG

pytestmark = [pytest.mark.integration, pytest.mark.asyncio, pytest.mark.lru]

# 测试需要 IMAGE_MAX_STORAGE_MB=1（约 1MB）
# BIG_JPEG ~200KB，6 张 ~1.2MB 超配额触发 LRU
UPLOAD_COUNT = 6


async def _upload_n(client, headers, n):
    """上传 n 张图片，返回 [{image_id, url}] 列表。"""
    images = []
    for i in range(n):
        resp = await client.post(
            "/api/chat/upload",
            files={"file": (f"test{i}.jpg", BIG_JPEG, "image/jpeg")},
            headers=headers,
        )
        assert resp.status_code == 200, f"upload #{i} failed: {resp.status_code}"
        images.append(resp.json())
    return images


async def _cleanup_images(client, headers, images):
    """清理图片列表，忽略已不存在的。"""
    for img in images:
        try:
            await client.delete(
                f"/api/chat/upload/{img['image_id']}", headers=headers
            )
        except Exception:
            pass


async def test_lru_deletes_oldest_on_quota_exceeded(async_client, auth_headers):
    """上传超配额 → 最旧图片被 LRU 清理 → GET 404"""
    images = await _upload_n(async_client, auth_headers, UPLOAD_COUNT)

    try:
        # 最早上传的图片应被 LRU 清理（GET → 404）
        resp_old = await async_client.get(images[0]["url"], headers=auth_headers)
        assert resp_old.status_code == 404, (
            f"最旧图片未被清理，期望 404，实际 {resp_old.status_code}"
        )

        # 最新上传的图片应仍存在（GET → 200）
        resp_new = await async_client.get(images[-1]["url"], headers=auth_headers)
        assert resp_new.status_code == 200, (
            f"最新图片不存在，期望 200，实际 {resp_new.status_code}"
        )
    finally:
        await _cleanup_images(async_client, auth_headers, images)


async def test_lru_preserves_recently_accessed(async_client, auth_headers):
    """LRU 清理时保留最近被访问过的图片（mtime 更新）"""
    images = []
    for i in range(UPLOAD_COUNT):
        resp = await async_client.post(
            "/api/chat/upload",
            files={"file": (f"test{i}.jpg", BIG_JPEG, "image/jpeg")},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        images.append(resp.json())

        # 上传第 3 张后，GET 第 1 张更新 mtime（模拟用户查看）
        if i == 2:
            get_resp = await async_client.get(
                images[0]["url"], headers=auth_headers
            )
            assert get_resp.status_code == 200

    try:
        # 第 1 张被访问过（mtime 更新），应保留
        resp_img1 = await async_client.get(images[0]["url"], headers=auth_headers)
        assert resp_img1.status_code == 200, "被访问过的图片不应被优先清理"

        # 第 2 张未被访问且最旧，应已被清理（mtime < img1）
        resp_img2 = await async_client.get(images[1]["url"], headers=auth_headers)
        assert resp_img2.status_code == 404, (
            f"未访问的旧图片应被清理，期望 404，实际 {resp_img2.status_code}"
        )
    finally:
        await _cleanup_images(async_client, auth_headers, images)
