"""R007-BB003+BB004 单元测试 — refuse / respond / prompts"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage

from app.agent.nodes import refuse_node, _REFUSE_MESSAGE
from app.agent.prompts import TEACHING_SYSTEM_PROMPT
from app.chat.errors import ChatErrorCode


# ===================================================================
# 1. refuse_node 测试
# ===================================================================


class TestRefuseNode:
    """refuse_node 返回静态 AIMessage，不调 LLM"""

    def test_returns_static_aimessage(self):
        """输入任意 state → 返回含静态拒绝文本的 dict"""
        state = {
            "messages": [HumanMessage(content="今天天气怎么样？")],
            "question": "今天天气怎么样？",
            "intent": "unrelated",
        }
        result = refuse_node(state)

        assert "messages" in result
        assert len(result["messages"]) == 1
        msg = result["messages"][0]
        assert isinstance(msg, AIMessage)
        assert msg.content == _REFUSE_MESSAGE

    def test_refuse_message_contains_key_phrases(self):
        """拒绝消息包含关键语义"""
        assert "课程学习助手" in _REFUSE_MESSAGE
        assert "教材内容" in _REFUSE_MESSAGE

    def test_refuse_node_ignores_input_state(self):
        """refuse_node 不依赖输入 state 的内容"""
        empty_state = {}
        result = refuse_node(empty_state)

        assert result["messages"][0].content == _REFUSE_MESSAGE

    def test_refuse_node_is_sync(self):
        """refuse_node 是同步函数，不返回 coroutine"""
        import inspect

        assert not inspect.iscoroutinefunction(refuse_node)


# ===================================================================
# 2. TEACHING_SYSTEM_PROMPT 内容验证
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


# ===================================================================
# 3. 错误码映射验证
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
