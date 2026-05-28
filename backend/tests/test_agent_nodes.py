"""R007-BB003+BB004 单元测试 — respond / prompts / summarize / rewrite"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph.message import RemoveMessage

from app.agent.prompts import TEACHING_SYSTEM_PROMPT
from app.agent.graph import _make_summarize
from app.chat.errors import ChatErrorCode


# ===================================================================
# 1. TEACHING_SYSTEM_PROMPT 内容验证
# ===================================================================

# 模拟未来 respond_node 的完整行为（闭包注入 LLM 后）
# 这里直接测试 TEACHING_SYSTEM_PROMPT 的内容


class TestTeachingSystemPrompt:
    """验证教学策略 prompt 包含要求的关键词"""

    def test_prompt_contains_analogy(self):
        """类比驱动"""
        assert "类比" in TEACHING_SYSTEM_PROMPT

    def test_prompt_contains_heuristic(self):
        """启发式引导"""
        assert "启发" in TEACHING_SYSTEM_PROMPT

    def test_prompt_contains_stepwise(self):
        """步骤化叙事"""
        assert "步骤" in TEACHING_SYSTEM_PROMPT

    def test_prompt_contains_correction(self):
        """纠正误解"""
        assert "纠正" in TEACHING_SYSTEM_PROMPT

    def test_prompt_contains_connection(self):
        """知识关联"""
        assert "关联" in TEACHING_SYSTEM_PROMPT

    def test_prompt_contains_core_principles(self):
        """核心原则 — 不直接给答案"""
        assert "不直接" in TEACHING_SYSTEM_PROMPT or "绝不直接" in TEACHING_SYSTEM_PROMPT

    def test_prompt_is_not_placeholder(self):
        """prompt 已替换，不是占位符"""
        assert len(TEACHING_SYSTEM_PROMPT) > 100

    def test_prompt_contains_faithfulness_constraint(self):
        """忠实性约束章节存在"""
        assert "忠实性约束" in TEACHING_SYSTEM_PROMPT

    def test_prompt_contains_highest_priority(self):
        """忠实性约束标记为最高优先级"""
        assert "最高优先级" in TEACHING_SYSTEM_PROMPT

    def test_prompt_contains_no_fabrication(self):
        """绝不编造措辞"""
        assert "绝不编造" in TEACHING_SYSTEM_PROMPT


# ===================================================================
# 2. 错误码映射验证
# ===================================================================


class TestErrorCodeMapping:
    """验证 ChatErrorCode 错误码值"""

    def test_connection_error_maps_to_02201(self):
        """ConnectionError → LLM_CONNECT_FAILED (02201)"""
        assert ChatErrorCode.LLM_CONNECT_FAILED.value == "02201"

    def test_runtime_error_maps_to_02202(self):
        """RuntimeError → LLM_STREAM_ERROR (02202)"""
        assert ChatErrorCode.LLM_STREAM_ERROR.value == "02202"

    def test_timeout_error_maps_to_02204(self):
        """TimeoutError → LLM_TIMEOUT (02204)"""
        assert ChatErrorCode.LLM_TIMEOUT.value == "02204"


# ===================================================================
# 3. _summarize 闭包测试
# ===================================================================


def _make_long_text(char_count: int) -> str:
    """生成指定字符数的文本（用于构造超阈值消息）"""
    return "x" * char_count


class TestSummarizeNode:
    """_make_summarize 闭包单元测试"""

    @pytest.fixture
    def mock_chat_model(self):
        """创建 mock chat_model"""
        model = AsyncMock()
        model.ainvoke = AsyncMock()
        response = MagicMock()
        response.content = "这是对话摘要"
        model.ainvoke.return_value = response
        return model

    @pytest.fixture
    def summarize(self, mock_chat_model):
        """创建 _summarize 闭包"""
        return _make_summarize(mock_chat_model)

    @pytest.mark.asyncio
    async def test_under_threshold_no_op(self, summarize):
        """短消息列表未超阈值 → return {}"""
        state = {
            "messages": [
                HumanMessage(content="什么是集合？", id="msg-1"),
                AIMessage(content="集合是数学中的基本概念", id="msg-2"),
            ],
            "conversation_summary": "",
        }
        result = await summarize(state)
        assert result == {}

    @pytest.mark.asyncio
    async def test_over_threshold_generates_summary(self, summarize, mock_chat_model):
        """超阈值 → LLM 生成摘要 + RemoveMessage 清理旧消息"""
        # 阈值 = 200_000 * 0.65 = 130_000 tokens
        # 每条消息 10000 字符 → 15000 tokens，需要 > 130000/15000 ≈ 9 条
        # 加上 reserved (12000)，需要约 10 条
        # 但 RECENT_MESSAGES_KEEP = 10，所以需要 > 10 条才能触发
        # 用 15 条消息，每条足够长来超阈值
        char_per_msg = 10000  # 10000 字符 → 15000 tokens
        messages = []
        for i in range(15):
            msg_cls = HumanMessage if i % 2 == 0 else AIMessage
            messages.append(msg_cls(content=_make_long_text(char_per_msg), id=f"msg-{i}"))

        state = {
            "messages": messages,
            "conversation_summary": "",
        }
        result = await summarize(state)

        # 验证生成了摘要
        assert "conversation_summary" in result
        assert result["conversation_summary"] == "这是对话摘要"

        # 验证生成了 RemoveMessage
        assert "messages" in result
        remove_msgs = result["messages"]
        assert all(isinstance(m, RemoveMessage) for m in remove_msgs)
        # 应该移除前 5 条消息（15 - 10 = 5）
        assert len(remove_msgs) == 5

        # 验证调用了 LLM
        mock_chat_model.ainvoke.assert_called_once()

    @pytest.mark.asyncio
    async def test_with_existing_summary(self, summarize, mock_chat_model):
        """有旧摘要 → LLM prompt 包含旧摘要信息"""
        # 构造超阈值消息
        char_per_msg = 10000
        messages = []
        for i in range(15):
            msg_cls = HumanMessage if i % 2 == 0 else AIMessage
            messages.append(msg_cls(content=_make_long_text(char_per_msg), id=f"msg-{i}"))

        state = {
            "messages": messages,
            "conversation_summary": "之前的对话摘要内容",
        }
        result = await summarize(state)

        assert "conversation_summary" in result

        # 验证 LLM 被调用时 prompt 中包含旧摘要
        call_args = mock_chat_model.ainvoke.call_args
        prompt_content = call_args[0][0][0].content
        assert "之前的对话摘要内容" in prompt_content

    @pytest.mark.asyncio
    async def test_llm_failure_no_op(self, mock_chat_model):
        """LLM 抛异常 → return {}"""
        mock_chat_model.ainvoke.side_effect = Exception("LLM error")
        summarize = _make_summarize(mock_chat_model)

        char_per_msg = 10000
        messages = []
        for i in range(15):
            msg_cls = HumanMessage if i % 2 == 0 else AIMessage
            messages.append(msg_cls(content=_make_long_text(char_per_msg), id=f"msg-{i}"))

        state = {
            "messages": messages,
            "conversation_summary": "",
        }
        result = await summarize(state)
        assert result == {}

    @pytest.mark.asyncio
    async def test_few_messages_no_op(self, summarize):
        """消息数 <= RECENT_MESSAGES_KEEP → return {}，即使 token 超阈值"""
        # 构造超长消息（超阈值），但只有 5 条（<= 10）
        messages = [
            HumanMessage(content=_make_long_text(100000), id="msg-0"),
            AIMessage(content=_make_long_text(100000), id="msg-1"),
            HumanMessage(content=_make_long_text(100000), id="msg-2"),
            AIMessage(content=_make_long_text(100000), id="msg-3"),
            HumanMessage(content=_make_long_text(100000), id="msg-4"),
        ]

        state = {
            "messages": messages,
            "conversation_summary": "",
        }
        result = await summarize(state)
        assert result == {}


# ===================================================================
# 4. _rewrite 闭包测试
# ===================================================================


class TestRewriteNode:
    """_make_rewrite 工厂函数单元测试"""

    @pytest.mark.asyncio
    async def test_first_turn_passthrough(self):
        """首轮（messages <= 1）→ return {}"""
        from app.agent.graph import _make_rewrite
        mock_chat_model = AsyncMock()
        _rewrite = _make_rewrite(mock_chat_model)

        state = {
            "messages": [HumanMessage(content="什么是函数？")],
            "question": "什么是函数？",
        }
        result = await _rewrite(state)
        assert result == {}
        mock_chat_model.ainvoke.assert_not_called()

    @pytest.mark.asyncio
    async def test_multi_turn_rewrite(self):
        """多轮 → LLM 改写 → 返回 rewritten_question"""
        from app.agent.graph import _make_rewrite
        mock_chat_model = AsyncMock()
        mock_chat_model.ainvoke.return_value = MagicMock(content="函数的定义域怎么求？")
        _rewrite = _make_rewrite(mock_chat_model)

        state = {
            "messages": [
                HumanMessage(content="什么是函数？", id="m1"),
                AIMessage(content="函数是一种对应关系...", id="m2"),
                HumanMessage(content="它的定义域怎么求？", id="m3"),
            ],
            "question": "它的定义域怎么求？",
        }
        result = await _rewrite(state)
        assert "rewritten_question" in result
        assert "函数" in result["rewritten_question"]
        assert "定义域" in result["rewritten_question"]
        mock_chat_model.ainvoke.assert_called_once()

    @pytest.mark.asyncio
    async def test_llm_failure_fallback(self):
        """LLM 失败 → return {}"""
        from app.agent.graph import _make_rewrite
        mock_chat_model = AsyncMock()
        mock_chat_model.ainvoke.side_effect = Exception("LLM error")
        _rewrite = _make_rewrite(mock_chat_model)

        state = {
            "messages": [
                HumanMessage(content="什么是函数？", id="m1"),
                AIMessage(content="函数是一种对应关系...", id="m2"),
                HumanMessage(content="它的定义域怎么求？", id="m3"),
            ],
            "question": "它的定义域怎么求？",
        }
        result = await _rewrite(state)
        assert result == {}
