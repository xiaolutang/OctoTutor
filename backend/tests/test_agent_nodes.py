"""R007-BB003+BB004 单元测试 — respond / prompts / summarize / rewrite"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph.message import RemoveMessage

from app.agent.prompts import TEACHING_SYSTEM_PROMPT
from app.agent.graph import _make_summarize, _make_rewrite, build_context_injection
from app.agent.token_budget import TokenBudget
from app.chat.errors import ChatErrorCode
from tests.conftest import make_query_result


# ===================================================================
# 1. TEACHING_SYSTEM_PROMPT 内容验证
# ===================================================================

# 模拟未来 respond_node 的完整行为（闭包注入 LLM 后）
# 这里直接测试 TEACHING_SYSTEM_PROMPT 的内容


class TestTeachingSystemPrompt:
    """验证教学策略 prompt 包含要求的关键词和约束"""

    REQUIRED_KEYWORDS = ["类比", "启发", "步骤", "纠正", "关联"]
    REQUIRED_CONSTRAINTS = ["忠实性约束", "最高优先级", "绝不编造"]

    def test_prompt_contains_teaching_strategies(self):
        """prompt 包含所有教学策略关键词"""
        for kw in self.REQUIRED_KEYWORDS:
            assert kw in TEACHING_SYSTEM_PROMPT, f"缺少教学策略关键词：{kw}"

    def test_prompt_is_not_placeholder(self):
        """prompt 已替换，不是占位符"""
        assert len(TEACHING_SYSTEM_PROMPT) > 100

    def test_prompt_contains_faithfulness_constraints(self):
        """prompt 包含忠实性约束完整链条"""
        for constraint in self.REQUIRED_CONSTRAINTS:
            assert constraint in TEACHING_SYSTEM_PROMPT, f"缺少忠实性约束：{constraint}"
        assert "不直接" in TEACHING_SYSTEM_PROMPT or "绝不直接" in TEACHING_SYSTEM_PROMPT


# ===================================================================
# 2. 错误码映射验证
# ===================================================================


class TestErrorCodeMapping:
    """验证 ChatErrorCode 错误码值"""

    @pytest.mark.parametrize("code,expected", [
        (ChatErrorCode.LLM_CONNECT_FAILED, "02201"),
        (ChatErrorCode.LLM_STREAM_ERROR, "02202"),
        (ChatErrorCode.LLM_TIMEOUT, "02204"),
    ])
    def test_error_code_values(self, code, expected):
        assert code.value == expected


# ===================================================================
# 3. _summarize 闭包测试
# ===================================================================


def _make_long_text(char_count: int) -> str:
    """生成指定字符数的文本（用于构造超阈值消息）"""
    return "x" * char_count


class TestSummarizeNode:
    """_make_summarize 闭包单元测试"""

    # 基于 TokenBudget 常量推导的测试参数
    # 阈值 = CONTEXT_WINDOW * SUMMARIZE_THRESHOLD = 130_000 tokens
    # 每条 char_per_msg 字符 → char_per_msg * 1.5 tokens
    # 需要 total_tokens > 阈值 + RESERVED → 消息数 > (130000 + 12000) / (char_per_msg * 1.5)
    # 加上 RECENT_MESSAGES_KEEP 限制，消息数必须 > RECENT_MESSAGES_KEEP
    CHAR_PER_MSG = 10_000   # 每条 10000 字符 → 15000 tokens
    MSG_COUNT_ABOVE = 15    # > RECENT_MESSAGES_KEEP(10) 且总 tokens 超阈值

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

    def _make_over_threshold_messages(self):
        """构造超阈值消息列表（MSG_COUNT_ABOVE 条，每条 CHAR_PER_MSG 字符）"""
        messages = []
        for i in range(self.MSG_COUNT_ABOVE):
            msg_cls = HumanMessage if i % 2 == 0 else AIMessage
            messages.append(msg_cls(content=_make_long_text(self.CHAR_PER_MSG), id=f"msg-{i}"))
        return messages

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
        messages = self._make_over_threshold_messages()
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
        expected_remove = self.MSG_COUNT_ABOVE - TokenBudget.RECENT_MESSAGES_KEEP
        assert len(remove_msgs) == expected_remove

        # 验证调用了 LLM
        mock_chat_model.ainvoke.assert_called_once()

    @pytest.mark.asyncio
    async def test_with_existing_summary(self, summarize, mock_chat_model):
        """有旧摘要 → LLM prompt 包含旧摘要信息"""
        messages = self._make_over_threshold_messages()
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

        messages = self._make_over_threshold_messages()
        state = {
            "messages": messages,
            "conversation_summary": "",
        }
        result = await summarize(state)
        assert result == {}

    @pytest.mark.asyncio
    async def test_few_messages_no_op(self, summarize):
        """消息数 <= RECENT_MESSAGES_KEEP → return {}，即使 token 超阈值"""
        # 构造超长消息（超阈值），但数量 < RECENT_MESSAGES_KEEP
        few_count = TokenBudget.RECENT_MESSAGES_KEEP - 1
        messages = []
        for i in range(few_count):
            msg_cls = HumanMessage if i % 2 == 0 else AIMessage
            messages.append(msg_cls(content=_make_long_text(100000), id=f"msg-{i}"))

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


# ===================================================================
# 5. build_context_injection 纯函数测试
# ===================================================================


class TestBuildContextInjection:
    """build_context_injection 纯函数单元测试（无需跑 graph）"""

    def _make_chunk(self, score: float):
        """构造带指定 score 的 QueryResult"""
        return make_query_result(text="测试内容", score=score)

    def test_no_chunks_returns_empty(self):
        """空 chunks → 不注入"""
        assert build_context_injection([], False, 0.5) == ""

    def test_high_score_strict_context(self):
        """高相关性 → 强约束"""
        result = build_context_injection([self._make_chunk(0.9)], False, 0.5)
        assert "严格基于以上教材内容回答" in result
        assert "可能相关的参考内容" not in result

    def test_low_score_weak_reference(self):
        """低相关性 → 弱参考"""

        result = build_context_injection([self._make_chunk(0.2)], False, 0.5)
        assert "可能相关的参考内容" in result
        assert "严格基于以上教材内容回答" not in result

    def test_degraded_weak_reference_even_with_high_score(self):
        """降级 → 即使 score 高也走弱参考"""

        result = build_context_injection([self._make_chunk(0.9)], True, 0.5)
        assert "可能相关的参考内容" in result
        assert "严格基于以上教材内容回答" not in result

    def test_score_exactly_at_threshold_goes_strict(self):
        """score 恰好等于 threshold → 走强约束（>= 包含边界）"""

        result = build_context_injection([self._make_chunk(0.5)], False, 0.5)
        assert "严格基于以上教材内容回答" in result
        assert "可能相关的参考内容" not in result
