"""LLM Generator — 基于 OpenAI 兼容协议的 RAG 回答生成器

实现 domain.protocols.Generator Protocol，
通过 OpenAI 兼容协议调用 LLM 生成助教式回答。
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from openai import AsyncOpenAI, OpenAI

from app.domain.models import SourceReference
from app.rag.models import QueryResult

SYSTEM_PROMPT = """你是章鱼哥，一个高中数学助教。基于给定的教材内容回答学生的问题。
规则：
1. 只使用提供的教材内容回答，不要编造内容
2. 引用回答依据时要标注出处（书名、章节、页码）
3. 如果提供的内容不足以回答问题，明确说明
4. 不要直接给出完整答案，引导学生理解解题思路"""

MATH_JUDGE_PROMPT = """你是高中数学辅导助手。用户的问题没有找到相关教材内容。
如果是数学问题，用你的知识解答；如果不是数学问题，
礼貌告知你只能解答数学相关问题。"""


class LLMGenerator:
    """基于 LLM 的 RAG 回答生成器

    实现 Generator Protocol，将检索到的 context chunks 与用户问题
    一起提交给 LLM，生成助教式回答并附带引用来源。

    Args:
        api_key: OpenAI 兼容 API Key
        base_url: OpenAI 兼容 API 地址
        model: LLM 模型名称
    """

    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        self._model = model
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._async_client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    def generate(
        self, query: str, context_chunks: list[QueryResult]
    ) -> tuple[str, list[SourceReference]]:
        """基于 context chunks 生成回答

        Args:
            query: 学生问题
            context_chunks: 检索到的相关教材片段

        Returns:
            (answer, sources) tuple：
            - answer: LLM 生成的回答文本
            - sources: 所有 context chunks 的引用来源列表
        """
        # 1. 构建 context（带编号标记）
        context_text = self._build_numbered_context(context_chunks)

        # 2. 调用 LLM
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"参考教材内容：\n{context_text}\n\n学生问题：{query}",
            },
        ]
        response = self._client.chat.completions.create(
            model=self._model, messages=messages
        )
        answer = response.choices[0].message.content

        # 3. 从 context_chunks metadata 构建 sources（非从 LLM 输出解析）
        sources = [
            SourceReference(
                chunk_id=chunk.chunk_id,
                book=chunk.metadata.book,
                section=chunk.metadata.section,
                page_start=chunk.metadata.page_start,
                page_end=chunk.metadata.page_end,
            )
            for chunk in context_chunks
        ]
        return answer, sources

    async def generate_stream(
        self, query: str, context_chunks: list[QueryResult]
    ) -> AsyncIterator[str]:
        """异步流式生成回答，逐 token yield

        Args:
            query: 学生问题
            context_chunks: 检索到的相关教材片段（可为空）

        Yields:
            LLM 生成的 token 字符串
        """
        if context_chunks:
            context_text = self._build_numbered_context(context_chunks)
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"参考教材内容：\n{context_text}\n\n学生问题：{query}",
                },
            ]
        else:
            messages = [
                {"role": "system", "content": MATH_JUDGE_PROMPT},
                {"role": "user", "content": query},
            ]

        stream = await self._async_client.chat.completions.create(
            model=self._model, messages=messages, stream=True
        )
        async with stream:
            async for chunk in stream:
                token = chunk.choices[0].delta.content or ""
                if token:
                    yield token

    def _build_numbered_context(self, chunks: list[QueryResult]) -> str:
        """构建带编号标记的 context 文本

        每个片段按 [编号] (书名 - 章节, 第x-y页) 格式标记，
        便于 LLM 在回答中引用具体出处。

        Args:
            chunks: 检索到的教材片段列表

        Returns:
            格式化后的 context 文本
        """
        parts = []
        for i, chunk in enumerate(chunks, 1):
            parts.append(
                f"[{i}] ({chunk.metadata.book} - {chunk.metadata.section}, "
                f"第{chunk.metadata.page_start}-{chunk.metadata.page_end}页)\n"
                f"{chunk.text}"
            )
        return "\n\n".join(parts)
