"""Tests for LLMGenerator.generate_stream() — 异步流式生成"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.infra.llm import MATH_JUDGE_PROMPT, SYSTEM_PROMPT, LLMGenerator
from app.rag.models import ChunkMetadata, QueryResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_chunk(content: str | None):
    """构造单个 mock stream chunk"""
    mock_delta = MagicMock()
    mock_delta.content = content
    mock_choice = MagicMock()
    mock_choice.delta = mock_delta
    mock_chunk = MagicMock()
    mock_chunk.choices = [mock_choice]
    return mock_chunk


class MockAsyncStream:
    """支持 async with + async for 的 mock stream"""

    def __init__(self, chunks):
        self._chunks = list(chunks)
        self._aenter_called = False
        self._aexit_called = False

    async def __aenter__(self):
        self._aenter_called = True
        return self

    async def __aexit__(self, *args):
        self._aexit_called = True

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._chunks:
            return self._chunks.pop(0)
        raise StopAsyncIteration


def _make_chunk_metadata() -> ChunkMetadata:
    return ChunkMetadata(
        book="高中数学必修一",
        chapter="第一章 集合与函数概念",
        section="1.1 集合的概念",
        section_id="高中数学必修一::1.1",
        page=10,
        page_start=10,
        page_end=12,
    )


def _make_query_result(text: str = "集合是由一些确定的、互不相同的对象组成的整体。") -> QueryResult:
    return QueryResult(
        chunk_id="chunk_001",
        text=text,
        score=0.95,
        metadata=_make_chunk_metadata(),
    )


def _create_generator() -> LLMGenerator:
    return LLMGenerator(api_key="test-key", base_url="https://api.test.com", model="test-model")


# ---------------------------------------------------------------------------
# Test: 基本流式输出
# ---------------------------------------------------------------------------

class TestGenerateStreamBasic:
    """generate_stream 逐 token yield"""

    def test_yields_tokens(self):
        chunks = [
            _make_mock_chunk("你"),
            _make_mock_chunk("好"),
            _make_mock_chunk("！"),
        ]
        mock_stream = MockAsyncStream(chunks)

        async def _run():
            gen = _create_generator()
            with patch.object(
                gen._async_client.chat.completions,
                "create",
                new_callable=AsyncMock,
                return_value=mock_stream,
            ):
                tokens = []
                async for token in gen.generate_stream(
                    "什么是集合？", [_make_query_result()]
                ):
                    tokens.append(token)
            return tokens

        tokens = asyncio.run(_run())
        assert tokens == ["你", "好", "！"]


# ---------------------------------------------------------------------------
# Test: 空 chunks 使用 MATH_JUDGE_PROMPT
# ---------------------------------------------------------------------------

class TestGenerateStreamEmptyChunks:
    """空 context_chunks 时 messages 使用 MATH_JUDGE_PROMPT"""

    def test_uses_math_judge_prompt(self):
        chunks = [_make_mock_chunk("好的")]
        mock_stream = MockAsyncStream(chunks)

        async def _run():
            gen = _create_generator()
            captured_messages = None

            async def _mock_create(**kwargs):
                nonlocal captured_messages
                captured_messages = kwargs["messages"]
                return mock_stream

            with patch.object(
                gen._async_client.chat.completions,
                "create",
                new_callable=AsyncMock,
                side_effect=_mock_create,
            ):
                tokens = []
                async for token in gen.generate_stream("怎么解方程？", []):
                    tokens.append(token)

            return captured_messages

        messages = asyncio.run(_run())
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == MATH_JUDGE_PROMPT
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "怎么解方程？"


# ---------------------------------------------------------------------------
# Test: 资源释放
# ---------------------------------------------------------------------------

class TestGenerateStreamResourceCleanup:
    """async with stream 异常时 __aexit__ 仍被调用"""

    def test_aexit_called_on_success(self):
        chunks = [_make_mock_chunk("ok")]
        mock_stream = MockAsyncStream(chunks)

        async def _run():
            gen = _create_generator()
            with patch.object(
                gen._async_client.chat.completions,
                "create",
                new_callable=AsyncMock,
                return_value=mock_stream,
            ):
                tokens = []
                async for token in gen.generate_stream(
                    "什么是集合？", [_make_query_result()]
                ):
                    tokens.append(token)
            return mock_stream

        stream = asyncio.run(_run())
        assert stream._aenter_called is True
        assert stream._aexit_called is True

    def test_aexit_called_on_exception(self):
        mock_stream = MockAsyncStream([])

        async def _run():
            gen = _create_generator()

            # 在 __anext__ 中抛异常来模拟流中错误
            class FailingStream(MockAsyncStream):
                async def __anext__(self):
                    raise RuntimeError("stream error")

            failing_stream = FailingStream([])

            with patch.object(
                gen._async_client.chat.completions,
                "create",
                new_callable=AsyncMock,
                return_value=failing_stream,
            ):
                tokens = []
                try:
                    async for token in gen.generate_stream(
                        "什么是集合？", [_make_query_result()]
                    ):
                        tokens.append(token)
                except RuntimeError:
                    pass
            return failing_stream

        stream = asyncio.run(_run())
        assert stream._aenter_called is True
        assert stream._aexit_called is True


# ---------------------------------------------------------------------------
# Test: 空 token 不 yield
# ---------------------------------------------------------------------------

class TestGenerateStreamNoTokens:
    """delta.content 为 None 或空字符串时不 yield"""

    def test_skips_none_and_empty_content(self):
        chunks = [
            _make_mock_chunk(None),
            _make_mock_chunk("hello"),
            _make_mock_chunk(""),
            _make_mock_chunk("world"),
            _make_mock_chunk(None),
        ]
        mock_stream = MockAsyncStream(chunks)

        async def _run():
            gen = _create_generator()
            with patch.object(
                gen._async_client.chat.completions,
                "create",
                new_callable=AsyncMock,
                return_value=mock_stream,
            ):
                tokens = []
                async for token in gen.generate_stream(
                    "什么是集合？", [_make_query_result()]
                ):
                    tokens.append(token)
            return tokens

        tokens = asyncio.run(_run())
        assert tokens == ["hello", "world"]

    def test_all_empty_yields_nothing(self):
        chunks = [
            _make_mock_chunk(None),
            _make_mock_chunk(""),
            _make_mock_chunk(None),
        ]
        mock_stream = MockAsyncStream(chunks)

        async def _run():
            gen = _create_generator()
            with patch.object(
                gen._async_client.chat.completions,
                "create",
                new_callable=AsyncMock,
                return_value=mock_stream,
            ):
                tokens = []
                async for token in gen.generate_stream(
                    "什么是集合？", [_make_query_result()]
                ):
                    tokens.append(token)
            return tokens

        tokens = asyncio.run(_run())
        assert tokens == []
