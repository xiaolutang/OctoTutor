"""LLMGenerator.generate_title() 单元测试

测试场景：
1. 正常返回标题
2. 超时返回 None
3. 异常返回 None
4. 标题去引号（双引号、单引号、混合）
5. 空白标题返回 None
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.infra.llm import LLMGenerator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_openai_response(content: str) -> MagicMock:
    """构造 mock OpenAI response 对象"""
    mock_message = MagicMock()
    mock_message.content = content
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    return mock_response


def _create_generator() -> LLMGenerator:
    """创建 LLMGenerator 实例（mock OpenAI client）"""
    return LLMGenerator(
        api_key="test-key",
        base_url="http://localhost:13000/v1",
        model="test-model",
    )


# ---------------------------------------------------------------------------
# Test: 正常返回标题
# ---------------------------------------------------------------------------


class TestGenerateTitleNormal:
    """generate_title 正常返回标题"""

    def test_returns_title_string(self):
        """正常调用返回标题字符串"""
        gen = _create_generator()
        mock_resp = _mock_openai_response("集合的基本概念")

        with patch.object(
            gen._async_client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            result = asyncio.run(gen.generate_title("什么是集合？"))

        assert result == "集合的基本概念"

    def test_calls_with_correct_params(self):
        """调用时传入正确的 model / messages / timeout 参数"""
        gen = _create_generator()
        mock_resp = _mock_openai_response("标题")
        captured_kwargs = {}

        async def _capture_create(**kwargs):
            captured_kwargs.update(kwargs)
            return mock_resp

        with patch.object(
            gen._async_client.chat.completions,
            "create",
            new_callable=AsyncMock,
            side_effect=_capture_create,
        ):
            asyncio.run(gen.generate_title("问题内容"))

        assert captured_kwargs["model"] == "test-model"
        assert captured_kwargs["max_tokens"] == 50
        assert captured_kwargs["timeout"] == 5.0
        messages = captured_kwargs["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "问题内容"


# ---------------------------------------------------------------------------
# Test: 超时返回 None
# ---------------------------------------------------------------------------


class TestGenerateTitleTimeout:
    """generate_title 超时返回 None"""

    def test_timeout_returns_none(self):
        """asyncio.TimeoutError 时返回 None"""
        gen = _create_generator()

        with patch.object(
            gen._async_client.chat.completions,
            "create",
            new_callable=AsyncMock,
            side_effect=asyncio.TimeoutError(),
        ):
            result = asyncio.run(gen.generate_title("超时问题"))

        assert result is None


# ---------------------------------------------------------------------------
# Test: 异常返回 None
# ---------------------------------------------------------------------------


class TestGenerateTitleException:
    """generate_title 异常返回 None"""

    def test_generic_exception_returns_none(self):
        """普通 Exception 时返回 None"""
        gen = _create_generator()

        with patch.object(
            gen._async_client.chat.completions,
            "create",
            new_callable=AsyncMock,
            side_effect=RuntimeError("API error"),
        ):
            result = asyncio.run(gen.generate_title("异常问题"))

        assert result is None

    def test_connection_error_returns_none(self):
        """连接错误时返回 None"""
        gen = _create_generator()

        with patch.object(
            gen._async_client.chat.completions,
            "create",
            new_callable=AsyncMock,
            side_effect=ConnectionError("connection refused"),
        ):
            result = asyncio.run(gen.generate_title("连接问题"))

        assert result is None


# ---------------------------------------------------------------------------
# Test: 标题去引号
# ---------------------------------------------------------------------------


class TestGenerateTitleStripQuotes:
    """generate_title 去除标题首尾引号"""

    def test_strip_double_quotes(self):
        """去除双引号"""
        gen = _create_generator()
        mock_resp = _mock_openai_response('"函数的定义域"')

        with patch.object(
            gen._async_client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            result = asyncio.run(gen.generate_title("什么是定义域？"))

        assert result == "函数的定义域"

    def test_strip_single_quotes(self):
        """去除单引号"""
        gen = _create_generator()
        mock_resp = _mock_openai_response("'三角函数'")

        with patch.object(
            gen._async_client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            result = asyncio.run(gen.generate_title("三角函数有哪些？"))

        assert result == "三角函数"

    def test_strip_mixed_quotes_and_whitespace(self):
        """去除首尾引号和外层空白（内部空白保留）"""
        gen = _create_generator()
        mock_resp = _mock_openai_response('  "集合的运算"  ')

        with patch.object(
            gen._async_client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            result = asyncio.run(gen.generate_title("集合怎么运算？"))

        assert result == "集合的运算"

    def test_no_quotes_unchanged(self):
        """无引号的标题保持不变"""
        gen = _create_generator()
        mock_resp = _mock_openai_response("二次函数最值问题")

        with patch.object(
            gen._async_client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            result = asyncio.run(gen.generate_title("求二次函数最值"))

        assert result == "二次函数最值问题"


# ---------------------------------------------------------------------------
# Test: 空白标题返回 None
# ---------------------------------------------------------------------------


class TestGenerateTitleEmptyResult:
    """generate_title 空白标题返回 None"""

    def test_empty_string_returns_none(self):
        """空字符串标题返回 None"""
        gen = _create_generator()
        mock_resp = _mock_openai_response("")

        with patch.object(
            gen._async_client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            result = asyncio.run(gen.generate_title("问题"))

        assert result is None

    def test_whitespace_only_returns_none(self):
        """纯空白标题 strip 后返回 None"""
        gen = _create_generator()
        mock_resp = _mock_openai_response("   ")

        with patch.object(
            gen._async_client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            result = asyncio.run(gen.generate_title("问题"))

        assert result is None
