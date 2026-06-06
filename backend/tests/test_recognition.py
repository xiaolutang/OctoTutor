"""VLMRecognitionProvider 单元测试

覆盖：
1. recognize 正常返回
2. recognize 超时
3. recognize 多张图片单次调用
"""

from __future__ import annotations

import base64
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.infra.recognition import VLMRecognitionProvider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_provider() -> VLMRecognitionProvider:
    return VLMRecognitionProvider(
        api_key="test-key",
        base_url="http://localhost:13000/v1",
        model="qwen3-vl-flash",
        upload_dir="data/uploads",
    )


def _fake_image_bytes() -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * 100  # minimal fake PNG


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recognize_success():
    """recognize 正常返回识别文本"""
    provider = _make_provider()

    fake_b64 = base64.b64encode(_fake_image_bytes()).decode()

    # Mock AsyncOpenAI
    mock_choice = MagicMock()
    mock_choice.message.content = "识别结果：$x^2 + 1 = 0$"
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    with patch.object(
        provider._client.chat.completions,
        "create",
        new_callable=AsyncMock,
        return_value=mock_response,
    ), patch.object(Path, "exists", return_value=True), patch.object(
        Path, "read_bytes", return_value=_fake_image_bytes()
    ):
        result = await provider.recognize(
            ["/api/uploads/user1/test.png"], "请识别图片"
        )

    assert result == "识别结果：$x^2 + 1 = 0$"


@pytest.mark.asyncio
async def test_recognize_timeout():
    """recognize 超时抛出异常"""
    import asyncio

    provider = _make_provider()

    with patch.object(
        provider._client.chat.completions,
        "create",
        new_callable=AsyncMock,
        side_effect=asyncio.TimeoutError(),
    ), patch.object(Path, "exists", return_value=True), patch.object(
        Path, "read_bytes", return_value=_fake_image_bytes()
    ):
        with pytest.raises(asyncio.TimeoutError):
            await provider.recognize(
                ["/api/uploads/user1/test.png"], "请识别图片"
            )


@pytest.mark.asyncio
async def test_recognize_multi_images():
    """多张图片：单次 VLM 调用，验证传入的 content 包含多张图"""
    provider = _make_provider()

    fake_b64 = base64.b64encode(_fake_image_bytes()).decode()

    mock_choice = MagicMock()
    mock_choice.message.content = "两道题目的转录结果"
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    captured_kwargs: dict = {}

    async def capture_create(**kwargs):
        captured_kwargs.update(kwargs)
        return mock_response

    with patch.object(
        provider._client.chat.completions,
        "create",
        new_callable=AsyncMock,
        side_effect=capture_create,
    ), patch.object(Path, "exists", return_value=True), patch.object(
        Path, "read_bytes", return_value=_fake_image_bytes()
    ):
        result = await provider.recognize(
            [
                "/api/uploads/user1/a.jpg",
                "/api/uploads/user1/b.png",
            ],
            "请识别这些图片",
        )

    assert result == "两道题目的转录结果"

    # 验证只调用一次 VLM
    messages = captured_kwargs["messages"]
    user_content = messages[1]["content"]

    # user_content 应包含 2 个 image_url block + 1 个 text block
    image_blocks = [b for b in user_content if b.get("type") == "image_url"]
    text_blocks = [b for b in user_content if b.get("type") == "text"]
    assert len(image_blocks) == 2
    assert len(text_blocks) == 1
    assert text_blocks[0]["text"] == "请识别这些图片"
