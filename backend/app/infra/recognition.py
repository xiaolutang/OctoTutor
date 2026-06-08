"""图片识别层 — 基于 Vision LLM 的图片内容识别

提供 VLMRecognitionProvider 实现，
将磁盘上的图片文件通过 OpenAI Vision 兼容 API 发送给 VLM 进行内容识别。
RecognitionProvider Protocol 定义在 domain/protocols.py。
"""

from __future__ import annotations

import base64
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

from openai import AsyncOpenAI

from app.agent.prompts import RECOGNITION_SYSTEM_PROMPT

if TYPE_CHECKING:
    from app.infra.image_manager import ImageManager

logger = logging.getLogger(__name__)


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
    发送给 VLM 模型进行内容识别。路径解析委托给 ImageManager。

    Args:
        api_key: OpenAI 兼容 API Key
        base_url: OpenAI 兼容 API 地址
        model: VLM 模型名称
        image_manager: ImageManager 实例，用于路径解析
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        image_manager: ImageManager,
    ) -> None:
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = model
        self._image_manager = image_manager

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

        使用 ImageManager 解析 URL 到磁盘路径。
        URL 格式: /api/uploads/{user_id}/{filename}
        """
        disk_path = Path(self._image_manager.disk_path_from_url(url))

        if not disk_path.exists():
            raise FileNotFoundError(f"Image file not found: {disk_path}")

        ext = disk_path.suffix.lower()
        mime = _MIME_MAP.get(ext, "image/jpeg")

        b64 = base64.b64encode(disk_path.read_bytes()).decode("utf-8")

        return {
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{b64}"},
        }
