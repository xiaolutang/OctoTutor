"""图片识别层 — 基于 Vision LLM 的图片内容识别

提供 RecognitionProvider Protocol 和 VLMRecognitionProvider 实现，
将磁盘上的图片文件通过 OpenAI Vision 兼容 API 发送给 VLM 进行内容识别。
"""

from __future__ import annotations

import base64
import logging
import os
from pathlib import Path
from typing import Protocol

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class RecognitionProvider(Protocol):
    """图片识别提供者协议"""

    async def recognize(self, image_urls: list[str], question: str) -> str: ...


# 扩展名 → MIME 类型映射
_MIME_MAP: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


class VLMRecognitionProvider:
    """基于 Vision LLM 的图片识别实现

    从磁盘读取图片文件，转为 base64 编码后通过 OpenAI Vision 兼容 API
    发送给 VLM 模型进行内容识别。

    Args:
        api_key: OpenAI 兼容 API Key
        base_url: OpenAI 兼容 API 地址
        model: VLM 模型名称
        upload_dir: 上传文件根目录（如 "data/uploads"）
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        upload_dir: str,
    ) -> None:
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = model
        self._upload_dir = upload_dir

    async def recognize(self, image_urls: list[str], question: str) -> str:
        """识别图片内容

        Args:
            image_urls: 图片 URL 列表，格式为 /api/uploads/{user_id}/{filename}
            question: 用户问题，用于构造 prompt

        Returns:
            VLM 返回的识别文本

        Raises:
            FileNotFoundError: 图片文件不存在
            TimeoutError: VLM 调用超时
            Exception: VLM 调用失败
        """
        from app.agent.prompts import RECOGNITION_SYSTEM_PROMPT

        # 构造图片内容块
        image_blocks: list[dict] = []
        for url in image_urls:
            image_block = self._build_image_block(url)
            image_blocks.append(image_block)

        # 构造消息
        user_content: list[dict] = [
            *image_blocks,
            {"type": "text", "text": question},
        ]

        messages = [
            {"role": "system", "content": RECOGNITION_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            timeout=30.0,
        )

        return response.choices[0].message.content

    def _build_image_block(self, url: str) -> dict:
        """将 URL 转换为 OpenAI Vision 格式的 image_url block

        URL 格式: /api/uploads/{user_id}/{filename}
        磁盘路径: {upload_dir}/{user_id}/{filename}
        """
        # 去掉 /api 前缀得到相对路径
        # /api/uploads/user1/abc.jpg → uploads/user1/abc.jpg
        relative_path = url.removeprefix("/api/")

        disk_path = Path(self._upload_dir) / relative_path.removeprefix("uploads/")

        if not disk_path.exists():
            raise FileNotFoundError(f"Image file not found: {disk_path}")

        ext = disk_path.suffix.lower()
        mime = _MIME_MAP.get(ext, "image/jpeg")

        b64 = base64.b64encode(disk_path.read_bytes()).decode("utf-8")

        return {
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{b64}"},
        }
