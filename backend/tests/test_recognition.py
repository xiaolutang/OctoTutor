"""VLMRecognitionProvider 单元测试

覆盖：
1. recognize 正常返回
2. recognize 超时
3. recognize 多张图片单次调用
4. _build_image_block 文件不存在 → FileNotFoundError
5. _build_image_block 非法 URL → ValueError
6. VLM 返回空内容
"""

from __future__ import annotations

import base64
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Optional

import pytest

from app.infra.recognition import VLMRecognitionProvider

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FAKE_API_KEY = "test-key"
FAKE_BASE_URL = "http://localhost:13000/v1"
FAKE_MODEL = "qwen3-vl-flash"
FAKE_UPLOAD_DIR = "data/uploads"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_image_manager():
    """Mock ImageManager with disk_path_from_url"""
    mgr = MagicMock()
    mgr._upload_dir = FAKE_UPLOAD_DIR

    def fake_disk_path_from_url(url: str) -> str:
        prefix = "/api/uploads/"
        if not url.startswith(prefix):
            raise ValueError(f"Invalid upload URL: {url}")
        relative = url[len(prefix):]
        parts = relative.split("/", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid upload URL: {url}")
        return str(Path(FAKE_UPLOAD_DIR) / parts[0] / parts[1])

    mgr.disk_path_from_url = fake_disk_path_from_url
    return mgr


def _make_provider() -> VLMRecognitionProvider:
    return VLMRecognitionProvider(
        api_key=FAKE_API_KEY,
        base_url=FAKE_BASE_URL,
        model=FAKE_MODEL,
        image_manager=_make_image_manager(),
    )


def _fake_image_bytes() -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * 100  # minimal fake PNG


def _make_mock_response(content: Optional[str] = "识别结果文本") -> MagicMock:
    mock_choice = MagicMock()
    mock_choice.message.content = content
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    return mock_response


# ---------------------------------------------------------------------------
# Tests — Happy Path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recognize_success():
    """recognize 正常返回识别文本"""
    provider = _make_provider()
    mock_response = _make_mock_response("识别结果：$x^2 + 1 = 0$")

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

    # 验证 messages 参数包含正确的 system prompt
    # （通过下一行的 capture 验证）


@pytest.mark.asyncio
async def test_recognize_success_captures_messages():
    """recognize 成功时验证 messages 结构"""
    provider = _make_provider()
    mock_response = _make_mock_response("OK")
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
        await provider.recognize(["/api/uploads/user1/test.png"], "问题")

    messages = captured_kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert len(messages) == 2
    user_content = messages[1]["content"]
    text_blocks = [b for b in user_content if b.get("type") == "text"]
    assert len(text_blocks) == 1
    assert text_blocks[0]["text"] == "问题"


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
    mock_response = _make_mock_response("两道题目的转录结果")
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

    messages = captured_kwargs["messages"]
    user_content = messages[1]["content"]

    image_blocks = [b for b in user_content if b.get("type") == "image_url"]
    text_blocks = [b for b in user_content if b.get("type") == "text"]
    assert len(image_blocks) == 2
    assert len(text_blocks) == 1
    assert text_blocks[0]["text"] == "请识别这些图片"


@pytest.mark.asyncio
async def test_recognize_empty_response():
    """VLM 返回空字符串"""
    provider = _make_provider()
    mock_response = _make_mock_response("")

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
    assert result == ""


@pytest.mark.asyncio
async def test_recognize_none_response():
    """VLM 返回 None"""
    provider = _make_provider()
    mock_response = _make_mock_response(None)

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
    assert result is None


# ---------------------------------------------------------------------------
# Tests — Error branches
# ---------------------------------------------------------------------------


def test_build_image_block_file_not_found():
    """图片文件不存在 → FileNotFoundError"""
    provider = _make_provider()

    with patch.object(Path, "exists", return_value=False):
        with pytest.raises(FileNotFoundError, match="Image file not found"):
            provider._build_image_block("/api/uploads/user1/missing.png")


def test_build_image_block_invalid_url_no_slash():
    """非法 URL（缺少 user_id/filename）→ ValueError"""
    provider = _make_provider()

    with pytest.raises(ValueError, match="Invalid upload URL"):
        provider._build_image_block("/api/uploads/noslash")


def test_build_image_block_invalid_url_wrong_prefix():
    """非法 URL（错误前缀）→ ValueError"""
    provider = _make_provider()

    with pytest.raises(ValueError, match="Invalid upload URL"):
        provider._build_image_block("/wrong/prefix/user1/file.png")
