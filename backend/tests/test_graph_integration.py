"""R007-BB001 集成测试 — StateGraph 线性拓扑编排

验证：
- 所有问题统一走 summarize → rewrite → retrieve → respond 路径
- graph.stream() 可执行并产出 events
- 无 classify/refuse 节点
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from langchain_core.messages import AIMessage, HumanMessage

from app.agent.graph import create_graph
from app.rag.models import QueryResult, ChunkMetadata

# 共享辅助函数
from tests._helpers import make_mock_chat_service, make_mock_generator
from tests.conftest import make_query_result


# ---------------------------------------------------------------------------
# 1. graph.nodes 验证
# ---------------------------------------------------------------------------


class TestGraphNodeStructure:
    """graph.nodes 包含 summarize, rewrite, retrieve, respond 四个节点"""

    def test_graph_contains_four_nodes(self):
        """无参数调用时包含四个节点"""
        graph = create_graph(
            chat_service=make_mock_chat_service(),
            generator=make_mock_generator(),
        )
        node_names = set(graph.nodes.keys())
        expected = {"summarize", "rewrite", "retrieve", "respond"}
        assert expected.issubset(node_names), f"missing nodes: {expected - node_names}"
        assert "classify" not in node_names
        assert "refuse" not in node_names


# ---------------------------------------------------------------------------
# 2. 端到端路径测试 — 数学问题
# ---------------------------------------------------------------------------


class TestLinearPath:
    """所有问题统一走 summarize → rewrite → retrieve → respond 路径"""

    @pytest.mark.asyncio
    async def test_math_question_visits_all_nodes(self):
        """数学问题经过 summarize → rewrite → retrieve → respond"""
        chunk = make_query_result(text="集合的概念...")
        chat_svc = make_mock_chat_service(chunks=[chunk])
        gen = make_mock_generator(tokens=["这是", "回答"])

        graph = create_graph(chat_service=chat_svc, generator=gen)

        initial_state = {
            "messages": [HumanMessage(content="什么是集合？")],
            "question": "什么是集合？",
        }

        events = []
        async for event in graph.astream(initial_state):
            events.append(event)

        # 验证经过 retrieve 节点 — retrieve 被调用
        chat_svc.retrieve.assert_called_once_with("什么是集合？", 10)

        # 验证经过 respond 节点 — 返回 AIMessage
        last_event = events[-1]
        respond_output = last_event.get("respond", {})
        assert "messages" in respond_output
        assert len(respond_output["messages"]) == 1
        assert isinstance(respond_output["messages"][0], AIMessage)

        # 验证 event_keys 按序包含线性拓扑节点
        event_keys = [list(e.keys())[0] for e in events]
        assert event_keys == ["summarize", "rewrite", "retrieve", "respond"]

        # 验证 context_chunks 在 state 中
        retrieve_event = None
        for e in events:
            if "retrieve" in e:
                retrieve_event = e
                break
        assert retrieve_event is not None
        retrieve_output = retrieve_event["retrieve"]
        assert len(retrieve_output["context_chunks"]) == 1
        assert retrieve_output["context_chunks"][0].text == "集合的概念..."

    @pytest.mark.asyncio
    async def test_linear_path_populates_sources(self):
        """retrieve 节点正确构建 sources"""
        chunk = make_query_result()
        chat_svc = make_mock_chat_service(chunks=[chunk])
        gen = make_mock_generator(tokens=["answer"])

        graph = create_graph(chat_service=chat_svc, generator=gen)

        initial_state = {
            "messages": [],
            "question": "求函数的最大值",
        }

        events = []
        async for event in graph.astream(initial_state):
            events.append(event)

        event_keys = [list(e.keys())[0] for e in events]
        assert event_keys == ["summarize", "rewrite", "retrieve", "respond"]

        retrieve_event = next(e for e in events if "retrieve" in e)
        sources = retrieve_event["retrieve"]["sources"]
        assert len(sources) == 1
        assert sources[0].book == "必修第一册"
        assert sources[0].section == "1.1 集合"

    @pytest.mark.asyncio
    async def test_linear_path_carries_degradation_info(self):
        """retrieve 节点传递降级信息"""
        chat_svc = make_mock_chat_service(
            chunks=[make_query_result()],
            degraded=True,
            degradation_reason="rerank_failed",
        )
        gen = make_mock_generator(tokens=["answer"])

        graph = create_graph(chat_service=chat_svc, generator=gen)

        initial_state = {
            "messages": [],
            "question": "解方程 x^2=4",
        }

        events = []
        async for event in graph.astream(initial_state):
            events.append(event)

        event_keys = [list(e.keys())[0] for e in events]
        assert event_keys == ["summarize", "rewrite", "retrieve", "respond"]

        retrieve_event = next(e for e in events if "retrieve" in e)
        assert retrieve_event["retrieve"]["degraded"] is True
        assert retrieve_event["retrieve"]["degradation_reason"] == "rerank_failed"


# ---------------------------------------------------------------------------
# 3. 端到端路径测试 — 问候/非课程问题（新架构下也走完整路径）
# ---------------------------------------------------------------------------


class TestGreetingPath:
    """问候/非课程问题也走 summarize → rewrite → retrieve → respond（由 LLM 自然拒绝）"""

    @pytest.mark.asyncio
    async def test_greeting_goes_through_full_path(self):
        """问候问题经过完整线性路径，retrieve 可能返回空"""
        chat_svc = make_mock_chat_service(chunks=[])
        gen = make_mock_generator()

        graph = create_graph(chat_service=chat_svc, generator=gen)

        initial_state = {
            "messages": [HumanMessage(content="你好")],
            "question": "你好",
        }

        events = []
        async for event in graph.astream(initial_state):
            events.append(event)

        # 验证 retrieve 被调用（即使返回空结果）
        chat_svc.retrieve.assert_called_once()

        # 验证走完整路径
        event_keys = [list(e.keys())[0] for e in events]
        assert event_keys == ["summarize", "rewrite", "retrieve", "respond"]

    @pytest.mark.asyncio
    async def test_thanks_goes_through_full_path(self):
        """谢谢经过完整线性路径"""
        chat_svc = make_mock_chat_service(chunks=[])
        gen = make_mock_generator()

        graph = create_graph(chat_service=chat_svc, generator=gen)

        initial_state = {
            "messages": [],
            "question": "谢谢",
        }

        events = []
        async for event in graph.astream(initial_state):
            events.append(event)

        chat_svc.retrieve.assert_called_once()
        event_keys = [list(e.keys())[0] for e in events]
        assert event_keys == ["summarize", "rewrite", "retrieve", "respond"]


# ---------------------------------------------------------------------------
# 4. graph.stream() / astream() 可执行并产出 events
# ---------------------------------------------------------------------------


class TestGraphStreaming:
    """graph.stream() 可执行并产出 events"""

    @pytest.mark.asyncio
    async def test_astream_produces_events(self):
        """astream 产出多个 event"""
        chat_svc = make_mock_chat_service(chunks=[make_query_result()])
        gen = make_mock_generator(tokens=["回答"])

        graph = create_graph(chat_service=chat_svc, generator=gen)

        initial_state = {
            "messages": [],
            "question": "什么是函数？",
        }

        events = []
        async for event in graph.astream(initial_state):
            events.append(event)

        # 线性路径产出 summarize + rewrite + retrieve + respond 四个事件
        assert len(events) >= 4
        event_keys = [list(e.keys())[0] for e in events]
        assert event_keys == ["summarize", "rewrite", "retrieve", "respond"]

    @pytest.mark.asyncio
    async def test_astream_greeting_produces_full_path(self):
        """问候问题也产出完整路径事件"""
        chat_svc = make_mock_chat_service(chunks=[])
        gen = make_mock_generator()

        graph = create_graph(chat_service=chat_svc, generator=gen)

        initial_state = {
            "messages": [],
            "question": "hello",
        }

        events = []
        async for event in graph.astream(initial_state):
            events.append(event)

        assert len(events) == 4
        event_keys = [list(e.keys())[0] for e in events]
        assert event_keys == ["summarize", "rewrite", "retrieve", "respond"]


# ---------------------------------------------------------------------------
# 5. 向后兼容 — 无 chat_service/generator 仍可编译
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    """create_graph 编译验证"""

    def test_create_graph_minimal_args(self):
        """只传 generator 时仍可编译"""
        graph = create_graph(generator=make_mock_generator())
        node_names = set(graph.nodes.keys())
        assert "respond" in node_names
        assert "classify" not in node_names
        assert "refuse" not in node_names

    def test_create_graph_with_checkpointer(self):
        from langgraph.checkpoint.memory import MemorySaver

        graph = create_graph(checkpointer=MemorySaver(), generator=make_mock_generator())
        node_names = set(graph.nodes.keys())
        assert "respond" in node_names
        assert "refuse" not in node_names


# ---------------------------------------------------------------------------
# 6. R010 respond 分级注入测试
# ---------------------------------------------------------------------------


def _make_chat_model_capture():
    """创建 mock chat_model，捕获 system_content"""
    captured = {}

    async def _ainvoke(messages, **kwargs):
        captured["system_content"] = messages[0].content
        return AIMessage(content="mock answer")

    model = MagicMock()
    model.ainvoke = _ainvoke
    return model, captured


def _make_generator_with_model(model):
    """创建 mock generator，使用指定 chat_model"""
    gen = MagicMock()
    gen.get_chat_model.return_value = model
    gen.generate_stream = AsyncMock()
    gen.generate_title = AsyncMock()
    return gen


class TestRespondGradedInjection:
    """R010: respond 节点分级 context 注入集成测试"""

    @pytest.mark.asyncio
    async def test_high_score_strict_context(self):
        """高相关性（score=0.9, degraded=False）→ 强约束注入"""
        from app.config import settings

        chunk = make_query_result(text="集合的概念...", score=0.9)
        assert 0.9 >= settings.relevance_threshold

        chat_svc = make_mock_chat_service(chunks=[chunk], degraded=False)
        model, captured = _make_chat_model_capture()
        gen = _make_generator_with_model(model)

        graph = create_graph(chat_service=chat_svc, generator=gen)
        events = []
        async for event in graph.astream({
            "messages": [HumanMessage(content="什么是集合？")],
            "question": "什么是集合？",
        }):
            events.append(event)

        system_content = captured["system_content"]
        assert "严格基于以上教材内容回答" in system_content
        assert "可能相关的参考内容" not in system_content

    @pytest.mark.asyncio
    async def test_low_score_weak_reference(self):
        """低相关性（score=0.2, degraded=False）→ 弱参考注入"""
        from app.config import settings

        chunk = make_query_result(text="不相关内容...", score=0.2)
        assert 0.2 < settings.relevance_threshold

        chat_svc = make_mock_chat_service(chunks=[chunk], degraded=False)
        model, captured = _make_chat_model_capture()
        gen = _make_generator_with_model(model)

        graph = create_graph(chat_service=chat_svc, generator=gen)
        events = []
        async for event in graph.astream({
            "messages": [HumanMessage(content="今天天气怎么样")],
            "question": "今天天气怎么样",
        }):
            events.append(event)

        system_content = captured["system_content"]
        assert "可能相关的参考内容" in system_content
        assert "严格基于以上教材内容回答" not in system_content

    @pytest.mark.asyncio
    async def test_no_chunks_no_injection(self):
        """无 chunks → 不注入 context"""
        chat_svc = make_mock_chat_service(chunks=[])
        model, captured = _make_chat_model_capture()
        gen = _make_generator_with_model(model)

        graph = create_graph(chat_service=chat_svc, generator=gen)
        events = []
        async for event in graph.astream({
            "messages": [HumanMessage(content="你好")],
            "question": "你好",
        }):
            events.append(event)

        system_content = captured["system_content"]
        assert "以下是检索到的教材内容" not in system_content
        assert "可能相关的参考内容" not in system_content

    @pytest.mark.asyncio
    async def test_degraded_weak_reference(self):
        """降级（degraded=True）→ 即使 score 高也走弱参考路径"""
        chunk = make_query_result(text="集合的概念...", score=0.9)
        chat_svc = make_mock_chat_service(
            chunks=[chunk], degraded=True, degradation_reason="rerank_failed"
        )
        model, captured = _make_chat_model_capture()
        gen = _make_generator_with_model(model)

        graph = create_graph(chat_service=chat_svc, generator=gen)
        events = []
        async for event in graph.astream({
            "messages": [HumanMessage(content="什么是集合？")],
            "question": "什么是集合？",
        }):
            events.append(event)

        system_content = captured["system_content"]
        assert "可能相关的参考内容" in system_content
        assert "严格基于以上教材内容回答" not in system_content
