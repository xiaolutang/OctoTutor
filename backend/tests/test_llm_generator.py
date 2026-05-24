"""LLMGenerator 单元测试

测试场景：
1. 正常 generate — 返回 (answer, sources) tuple
2. answer 非空
3. sources 包含所有 context_chunks 的引用信息
4. build_numbered_context 格式正确
5. OpenAI 调用参数正确（model, messages）
6. 空上下文处理
"""

from unittest.mock import MagicMock, patch

import pytest

from app.domain.models import SourceReference
from app.infra.llm import LLMGenerator, SYSTEM_PROMPT
from app.rag.models import ChunkMetadata, QueryResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_chunk(
    chunk_id: str = "必修第一册::1.1::p1_s0::child",
    text: str = "一般地，把一些能够确定的不同对象看成一个整体，就说这个整体是由这些对象的全体组成的集合。",
    book: str = "必修第一册",
    section: str = "1.1 集合",
    page_start: int = 1,
    page_end: int = 2,
    score: float = 0.95,
) -> QueryResult:
    """构造测试用 QueryResult"""
    return QueryResult(
        chunk_id=chunk_id,
        text=text,
        score=score,
        metadata=ChunkMetadata(
            book=book,
            chapter="第一章 集合与函数概念",
            section=section,
            section_id=f"{book}::1.1",
            page=page_start,
            page_start=page_start,
            page_end=page_end,
            source_pages=list(range(page_start, page_end + 1)),
            chunk_type="child",
            block_type="definition",
            has_formula=False,
            parent_id="必修第一册::1.1::p1_s0::parent",
            child_index=0,
        ),
    )


def _mock_openai_response(content: str) -> MagicMock:
    """构造 mock OpenAI response 对象"""
    mock_message = MagicMock()
    mock_message.content = content
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    return mock_response


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def generator():
    """创建 LLMGenerator 实例（mock OpenAI client）"""
    with patch("app.infra.llm.OpenAI"):
        return LLMGenerator(
            api_key="test-key",
            base_url="http://localhost:13000/v1",
            model="glm-5.1",
        )


# ---------------------------------------------------------------------------
# 测试：正常 generate
# ---------------------------------------------------------------------------


class TestGenerate:
    """generate 方法测试"""

    def test_returns_answer_and_sources_tuple(self, generator):
        """generate 返回 (answer, sources) 二元组"""
        chunks = [make_chunk()]
        generator._client.chat.completions.create.return_value = _mock_openai_response(
            "集合是由一些确定的不同对象组成的整体。"
        )

        result = generator.generate("什么是集合？", chunks)

        assert isinstance(result, tuple)
        assert len(result) == 2
        answer, sources = result
        assert isinstance(answer, str)
        assert isinstance(sources, list)

    def test_answer_is_not_empty(self, generator):
        """answer 不为空"""
        expected_answer = "集合是由一些确定的不同对象组成的整体。"
        chunks = [make_chunk()]
        generator._client.chat.completions.create.return_value = _mock_openai_response(
            expected_answer
        )

        answer, _ = generator.generate("什么是集合？", chunks)

        assert answer == expected_answer
        assert len(answer) > 0

    def test_sources_contain_all_chunks_metadata(self, generator):
        """sources 包含所有 context_chunks 的引用信息"""
        chunks = [
            make_chunk(
                chunk_id="id-1",
                book="必修第一册",
                section="1.1 集合",
                page_start=1,
                page_end=2,
            ),
            make_chunk(
                chunk_id="id-2",
                book="必修第一册",
                section="1.2 集合的表示",
                page_start=5,
                page_end=7,
            ),
        ]
        generator._client.chat.completions.create.return_value = _mock_openai_response(
            "回答内容"
        )

        _, sources = generator.generate("问题", chunks)

        assert len(sources) == 2
        # 验证第一个 source
        assert sources[0] == SourceReference(
            chunk_id="id-1",
            book="必修第一册",
            section="1.1 集合",
            page_start=1,
            page_end=2,
        )
        # 验证第二个 source
        assert sources[1] == SourceReference(
            chunk_id="id-2",
            book="必修第一册",
            section="1.2 集合的表示",
            page_start=5,
            page_end=7,
        )

    def test_sources_fields_from_metadata(self, generator):
        """sources 的 chunk_id/book/section/page_start/page_end 来自 metadata"""
        chunks = [make_chunk()]
        generator._client.chat.completions.create.return_value = _mock_openai_response(
            "回答"
        )

        _, sources = generator.generate("问题", chunks)

        src = sources[0]
        assert src.chunk_id == chunks[0].chunk_id
        assert src.book == chunks[0].metadata.book
        assert src.section == chunks[0].metadata.section
        assert src.page_start == chunks[0].metadata.page_start
        assert src.page_end == chunks[0].metadata.page_end


# ---------------------------------------------------------------------------
# 测试：build_numbered_context 格式
# ---------------------------------------------------------------------------


class TestBuildNumberedContext:
    """build_numbered_context 格式测试"""

    def test_single_chunk_format(self, generator):
        """单个 chunk 的格式正确"""
        from app.rag.context_builder import build_numbered_context
        chunks = [make_chunk(text="集合的定义内容")]

        result = build_numbered_context(chunks)

        assert "[1]" in result
        assert "必修第一册" in result
        assert "1.1 集合" in result
        assert "第1-2页" in result
        assert "集合的定义内容" in result

    def test_multiple_chunks_numbered(self, generator):
        """多个 chunk 按顺序编号"""
        from app.rag.context_builder import build_numbered_context
        chunks = [
            make_chunk(chunk_id="id-1", text="内容A", page_start=1, page_end=1),
            make_chunk(chunk_id="id-2", text="内容B", page_start=3, page_end=5),
        ]

        result = build_numbered_context(chunks)

        assert "[1]" in result
        assert "[2]" in result
        assert "内容A" in result
        assert "内容B" in result
        assert "第1-1页" in result
        assert "第3-5页" in result

    def test_chunks_separated_by_double_newline(self, generator):
        """多个 chunk 之间用双换行分隔"""
        from app.rag.context_builder import build_numbered_context
        chunks = [
            make_chunk(text="内容A"),
            make_chunk(text="内容B"),
        ]

        result = build_numbered_context(chunks)

        # 确认 chunk 之间有双换行
        parts = result.split("\n\n")
        assert len(parts) == 2


# ---------------------------------------------------------------------------
# 测试：OpenAI 调用参数
# ---------------------------------------------------------------------------


class TestOpenAICall:
    """OpenAI 调用参数测试"""

    def test_correct_model_passed(self, generator):
        """调用时传入正确的 model"""
        chunks = [make_chunk()]
        generator._client.chat.completions.create.return_value = _mock_openai_response(
            "回答"
        )

        generator.generate("问题", chunks)

        call_kwargs = generator._client.chat.completions.create.call_args
        assert call_kwargs.kwargs.get("model") == "glm-5.1" or call_kwargs[1].get("model") == "glm-5.1"

    def test_correct_messages_structure(self, generator):
        """调用时 messages 包含 system prompt 和 user message"""
        chunks = [make_chunk(text="教材内容")]
        generator._client.chat.completions.create.return_value = _mock_openai_response(
            "回答"
        )

        generator.generate("什么是集合？", chunks)

        call_args = generator._client.chat.completions.create.call_args
        messages = call_args.kwargs.get("messages") or call_args[1].get("messages")

        # 验证 messages 结构
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == SYSTEM_PROMPT
        assert messages[1]["role"] == "user"
        # user message 包含 context 和 query
        user_content = messages[1]["content"]
        assert "教材内容" in user_content
        assert "什么是集合？" in user_content


# ---------------------------------------------------------------------------
# 测试：空上下文处理
# ---------------------------------------------------------------------------


class TestEmptyContext:
    """空上下文处理测试"""

    def test_empty_chunks_returns_empty_sources(self, generator):
        """空 context_chunks 返回空 sources 列表"""
        generator._client.chat.completions.create.return_value = _mock_openai_response(
            "抱歉，没有找到相关的教材内容来回答你的问题。"
        )

        answer, sources = generator.generate("问题", [])

        assert isinstance(answer, str)
        assert len(answer) > 0
        assert sources == []

    def test_empty_context_text_is_empty_string(self, generator):
        """空 chunks 时 build_numbered_context 返回空字符串"""
        from app.rag.context_builder import build_numbered_context
        result = build_numbered_context([])

        assert result == ""
