"""DashScope Embedding 封装

封装 DashScope TextEmbedding API，提供批量文本向量化能力。
支持批量调用（batch_size=6）、指数退避重试（max_retries=3）、
返回 768 维向量。
"""

from __future__ import annotations

import logging
import time
from typing import Any

from dashscope import MultiModalEmbedding, TextEmbedding

logger = logging.getLogger(__name__)


class DashScopeEmbedding:
    """DashScope Embedding 封装

    封装 dashscope.TextEmbedding.call，支持：
    - 批量调用（自动按 batch_size 分批）
    - 指数退避重试（max_retries）
    - 768 维向量返回

    Args:
        api_key: DashScope API Key
        model: Embedding 模型名称，默认 "text-embedding-v3"
        dimension: 向量维度，默认 768
        batch_size: 批量大小，默认 6（DashScope 限制）
        max_retries: 最大重试次数，默认 3
    """

    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-v4",
        dimension: int = 768,
        batch_size: int = 6,
        max_retries: int = 3,
    ) -> None:
        if not api_key:
            raise ValueError("dashscope_api_key 不能为空")

        self._api_key = api_key
        self._model = model
        self._dimension = dimension
        self._batch_size = batch_size
        self._max_retries = max_retries

    def embed(self, texts: list[str]) -> list[list[float]]:
        """将文本列表转为向量列表

        自动按 batch_size 分批调用 DashScope API，
        失败时指数退避重试。超长文本自动截断到 8192 字符。

        Args:
            texts: 待向量化的文本列表

        Returns:
            与 texts 等长的向量列表

        Raises:
            ValueError: texts 为空列表
            RuntimeError: 所有重试失败后仍无法获取结果
        """
        if not texts:
            raise ValueError("texts 不能为空列表")

        # 截断超长文本
        max_len = 8000
        truncated = [t[:max_len] if len(t) > max_len else t for t in texts]

        all_embeddings: list[list[float]] = [None] * len(truncated)  # type: ignore[list-item]

        # 按 batch_size 分片
        batches = self._split_batches(truncated)

        for batch_start, batch_texts in batches:
            batch_embeddings = self._call_with_retry(batch_texts)

            # 按 text_index 放回正确位置
            for i, embedding in enumerate(batch_embeddings):
                all_embeddings[batch_start + i] = embedding

        return all_embeddings  # type: ignore[return-value]

    def embed_query(self, text: str) -> list[float]:
        """将单条查询文本转为向量

        使用 text_type=query 参数，优化检索场景。

        Args:
            text: 查询文本

        Returns:
            768 维向量

        Raises:
            ValueError: text 为空字符串
            RuntimeError: API 调用失败
        """
        if not text:
            raise ValueError("查询文本不能为空")

        result = self._call_with_retry([text], text_type="query")
        return result[0]

    def _split_batches(
        self, texts: list[str]
    ) -> list[tuple[int, list[str]]]:
        """将文本列表按 batch_size 分片

        Returns:
            [(起始索引, 文本子列表), ...]
        """
        batches: list[tuple[int, list[str]]] = []
        for i in range(0, len(texts), self._batch_size):
            batch = texts[i : i + self._batch_size]
            batches.append((i, batch))
        return batches

    def _call_with_retry(
        self,
        texts: list[str],
        text_type: str | None = None,
    ) -> list[list[float]]:
        """带指数退避重试的 API 调用

        Args:
            texts: 文本列表（不超过 batch_size）
            text_type: 可选 "query" 或 "document"

        Returns:
            与 texts 等长的向量列表

        Raises:
            RuntimeError: 所有重试失败
        """
        last_error: Exception | None = None

        for attempt in range(self._max_retries + 1):
            try:
                embeddings = self._call_api(texts, text_type=text_type)
                return embeddings
            except ValueError:
                # 不可重试错误（如维度不匹配），直接抛出
                raise
            except Exception as e:
                last_error = e
                if attempt < self._max_retries:
                    wait_time = 2**attempt  # 1s, 2s, 4s
                    logger.warning(
                        "Embedding API 调用失败 (attempt %d/%d), "
                        "%ds 后重试: %s",
                        attempt + 1,
                        self._max_retries + 1,
                        wait_time,
                        str(e),
                    )
                    time.sleep(wait_time)
                else:
                    logger.error(
                        "Embedding API 调用失败, 已重试 %d 次: %s",
                        self._max_retries,
                        str(e),
                    )

        raise RuntimeError(
            f"Embedding API 调用失败, 已重试 {self._max_retries} 次: "
            f"{last_error}"
        ) from last_error

    def _call_api(
        self,
        texts: list[str],
        text_type: str | None = None,
    ) -> list[list[float]]:
        """调用 DashScope Embedding API

        自动根据模型名选择 TextEmbedding 或 MultiModalEmbedding API。

        Args:
            texts: 文本列表
            text_type: 可选 "query" 或 "document"

        Returns:
            向量列表

        Raises:
            RuntimeError: API 返回非 200 状态码
            ValueError: 返回向量维度与预期不符
        """
        use_vision = self._model.startswith("tongyi-embedding-vision")

        if use_vision:
            mm_input = [{"text": t} for t in texts]
            response = MultiModalEmbedding.call(
                model=self._model,
                input=mm_input,
                api_key=self._api_key,
            )
        else:
            kwargs: dict[str, Any] = {
                "model": self._model,
                "input": texts,
                "api_key": self._api_key,
            }
            if self._dimension:
                kwargs["dimension"] = self._dimension
            if text_type is not None:
                kwargs["text_type"] = text_type
            response = TextEmbedding.call(**kwargs)

        if response.status_code != 200:
            raise RuntimeError(
                f"DashScope API 错误: "
                f"status_code={response.status_code}, "
                f"code={response.code}, "
                f"message={response.message}"
            )

        # 提取并排序 embeddings
        raw_embeddings = response.output["embeddings"]
        if raw_embeddings and "text_index" in raw_embeddings[0]:
            sorted_embeddings = sorted(
                raw_embeddings, key=lambda x: x["text_index"]
            )
        else:
            sorted_embeddings = raw_embeddings

        result: list[list[float]] = []
        for item in sorted_embeddings:
            embedding = item["embedding"]
            if len(embedding) != self._dimension:
                raise ValueError(
                    f"向量维度不匹配: 期望 {self._dimension}, "
                    f"实际 {len(embedding)}"
                )
            result.append(embedding)

        return result
