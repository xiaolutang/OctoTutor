"""R007-BB001 集成测试 — StateGraph 条件路由编排

验证：
- textbook 问题走 classify→retrieve→respond 路径
- unrelated 问题走 classify→refuse 路径
- graph.stream() 可执行并产出 events
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage

from app.agent.graph import AgentState, create_graph, _route_by_intent
from app.rag.models import QueryResult, ChunkMetadata
from app.domain.models import SourceReference


# ---------------------------------------------------------------------------
# 辅助：构造 mock ChatService
# ---------------------------------------------------------------------------


def _make_mock_chat_service(chunks=None, degraded=False, degradation_reason=None):
    """构造 mock ChatService，_retrieve 返回指定 chunks"""
    svc = MagicMock()

    result_chunks = chunks or []
    result = MagicMock()
    result.chunks = result_chunks
    result.degraded = degraded
    result.degradation_reason = degradation_reason

    svc._retrieve.return_value = result
    return svc


def _make_mock_generator(tokens=None):
    """构造 mock LLMGenerator，generate_stream 返回指定 tokens"""
    gen = MagicMock()

    async def _stream(*args, **kwargs):
        for t in (tokens or ["mock", " answer"]):
            yield t

    gen.generate_stream = _stream
    gen._build_numbered_context = MagicMock(return_value="[1] mock context")
    return gen


def _make_query_result(text="test chunk", score=0.95):
    return QueryResult(
        chunk_id="test::chunk::1",
        text=text,
        score=score,
        metadata=ChunkMetadata(
            book="必修第一册",
            chapter="第一章",
            section="1.1 集合",
            section_id="必修第一册::1.1",
            page=1,
            page_start=1,
            page_end=2,
        ),
    )


# ---------------------------------------------------------------------------
# 1. graph.nodes 验证
# ---------------------------------------------------------------------------


class TestGraphNodeStructure:
    """graph.nodes 包含 classify, retrieve, respond, refuse 四个节点"""

    def test_graph_contains_four_nodes(self):
        """无参数调用时包含四个节点"""
        graph = create_graph(
            chat_service=_make_mock_chat_service(),
            generator=_make_mock_generator(),
        )
        node_names = set(graph.nodes.keys())
        expected = {"classify", "retrieve", "respond", "refuse"}
        assert expected.issubset(node_names), f"missing nodes: {expected - node_names}"

    def test_graph_contains_classify_node(self):
        graph = create_graph(
            chat_service=_make_mock_chat_service(),
            generator=_make_mock_generator(),
        )
        assert "classify" in graph.nodes

    def test_graph_contains_retrieve_node(self):
        graph = create_graph(
            chat_service=_make_mock_chat_service(),
            generator=_make_mock_generator(),
        )
        assert "retrieve" in graph.nodes

    def test_graph_contains_respond_node(self):
        graph = create_graph(
            chat_service=_make_mock_chat_service(),
            generator=_make_mock_generator(),
        )
        assert "respond" in graph.nodes

    def test_graph_contains_refuse_node(self):
        graph = create_graph(
            chat_service=_make_mock_chat_service(),
            generator=_make_mock_generator(),
        )
        assert "refuse" in graph.nodes


# ---------------------------------------------------------------------------
# 2. 条件路由验证
# ---------------------------------------------------------------------------


class TestRouteByIntent:
    """_route_by_intent 条件路由"""

    def test_textbook_routes_to_retrieve(self):
        assert _route_by_intent({"intent": "textbook"}) == "retrieve"

    def test_unrelated_routes_to_refuse(self):
        assert _route_by_intent({"intent": "unrelated"}) == "refuse"

    def test_unknown_defaults_to_refuse(self):
        assert _route_by_intent({"intent": "other"}) == "refuse"


# ---------------------------------------------------------------------------
# 3. 端到端路径测试 — textbook 问题
# ---------------------------------------------------------------------------


class TestTextbookPath:
    """textbook 意图走 classify→retrieve→respond 路径"""

    @pytest.mark.asyncio
    async def test_textbook_question_visits_retrieve_and_respond(self):
        """数学问题经过 classify→retrieve→respond"""
        chunk = _make_query_result("集合的概念...")
        chat_svc = _make_mock_chat_service(chunks=[chunk])
        gen = _make_mock_generator(tokens=["这是", "回答"])

        graph = create_graph(chat_service=chat_svc, generator=gen)

        initial_state = {
            "messages": [HumanMessage(content="什么是集合？")],
            "question": "什么是集合？",
        }

        events = []
        async for event in graph.astream(initial_state):
            events.append(event)

        # 验证经过 retrieve 节点 — _retrieve 被调用
        chat_svc._retrieve.assert_called_once_with("什么是集合？", 10)

        # 验证经过 respond 节点 — 最终消息包含 AI 回答
        last_event = events[-1]
        respond_output = last_event.get("respond", {})
        messages = respond_output.get("messages", [])
        assert len(messages) == 1
        assert isinstance(messages[0], AIMessage)
        assert messages[0].content == "这是回答"

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
    async def test_textbook_path_populates_sources(self):
        """retrieve 节点正确构建 sources"""
        chunk = _make_query_result()
        chat_svc = _make_mock_chat_service(chunks=[chunk])
        gen = _make_mock_generator(tokens=["answer"])

        graph = create_graph(chat_service=chat_svc, generator=gen)

        initial_state = {
            "messages": [],
            "question": "求函数的最大值",
        }

        events = []
        async for event in graph.astream(initial_state):
            events.append(event)

        retrieve_event = next(e for e in events if "retrieve" in e)
        sources = retrieve_event["retrieve"]["sources"]
        assert len(sources) == 1
        assert sources[0].book == "必修第一册"
        assert sources[0].section == "1.1 集合"

    @pytest.mark.asyncio
    async def test_textbook_path_carries_degradation_info(self):
        """retrieve 节点传递降级信息"""
        chat_svc = _make_mock_chat_service(
            chunks=[_make_query_result()],
            degraded=True,
            degradation_reason="rerank_failed",
        )
        gen = _make_mock_generator(tokens=["answer"])

        graph = create_graph(chat_service=chat_svc, generator=gen)

        initial_state = {
            "messages": [],
            "question": "解方程 x^2=4",
        }

        events = []
        async for event in graph.astream(initial_state):
            events.append(event)

        retrieve_event = next(e for e in events if "retrieve" in e)
        assert retrieve_event["retrieve"]["degraded"] is True
        assert retrieve_event["retrieve"]["degradation_reason"] == "rerank_failed"


# ---------------------------------------------------------------------------
# 4. 端到端路径测试 — unrelated 问题
# ---------------------------------------------------------------------------


class TestUnrelatedPath:
    """unrelated 意图走 classify→refuse 路径"""

    @pytest.mark.asyncio
    async def test_unrelated_question_goes_to_refuse(self):
        """问候问题经过 classify→refuse"""
        chat_svc = _make_mock_chat_service()
        gen = _make_mock_generator()

        graph = create_graph(chat_service=chat_svc, generator=gen)

        initial_state = {
            "messages": [HumanMessage(content="你好")],
            "question": "你好",
        }

        events = []
        async for event in graph.astream(initial_state):
            events.append(event)

        # 验证 _retrieve 未被调用
        chat_svc._retrieve.assert_not_called()

        # 验证经过 refuse 节点
        refuse_event = next((e for e in events if "refuse" in e), None)
        assert refuse_event is not None

        refuse_output = refuse_event["refuse"]
        messages = refuse_output.get("messages", [])
        assert len(messages) == 1
        assert isinstance(messages[0], AIMessage)
        assert "课程学习助手" in messages[0].content

    @pytest.mark.asyncio
    async def test_short_question_goes_to_refuse(self):
        """短问题（<=3字）走 refuse"""
        chat_svc = _make_mock_chat_service()
        gen = _make_mock_generator()

        graph = create_graph(chat_service=chat_svc, generator=gen)

        initial_state = {
            "messages": [],
            "question": "嗨",
        }

        events = []
        async for event in graph.astream(initial_state):
            events.append(event)

        chat_svc._retrieve.assert_not_called()
        refuse_event = next((e for e in events if "refuse" in e), None)
        assert refuse_event is not None

    @pytest.mark.asyncio
    async def test_greeting_goes_to_refuse(self):
        """常见问候走 refuse"""
        chat_svc = _make_mock_chat_service()
        gen = _make_mock_generator()

        graph = create_graph(chat_service=chat_svc, generator=gen)

        initial_state = {
            "messages": [],
            "question": "谢谢",
        }

        events = []
        async for event in graph.astream(initial_state):
            events.append(event)

        chat_svc._retrieve.assert_not_called()
        refuse_event = next((e for e in events if "refuse" in e), None)
        assert refuse_event is not None


# ---------------------------------------------------------------------------
# 5. graph.stream() / astream() 可执行并产出 events
# ---------------------------------------------------------------------------


class TestGraphStreaming:
    """graph.stream() 可执行并产出 events"""

    @pytest.mark.asyncio
    async def test_astream_produces_events(self):
        """astream 产出多个 event"""
        chat_svc = _make_mock_chat_service(chunks=[_make_query_result()])
        gen = _make_mock_generator(tokens=["回答"])

        graph = create_graph(chat_service=chat_svc, generator=gen)

        initial_state = {
            "messages": [],
            "question": "什么是函数？",
        }

        events = []
        async for event in graph.astream(initial_state):
            events.append(event)

        # textbook 路径至少产出 classify + retrieve + respond 三个事件
        assert len(events) >= 3
        event_keys = [list(e.keys())[0] for e in events]
        assert event_keys == ["classify", "retrieve", "respond"]

    @pytest.mark.asyncio
    async def test_astream_unrelated_produces_classify_refuse(self):
        """unrelated 路径产出 classify + refuse 两个事件"""
        chat_svc = _make_mock_chat_service()
        gen = _make_mock_generator()

        graph = create_graph(chat_service=chat_svc, generator=gen)

        initial_state = {
            "messages": [],
            "question": "hello",
        }

        events = []
        async for event in graph.astream(initial_state):
            events.append(event)

        assert len(events) == 2
        event_keys = [list(e.keys())[0] for e in events]
        assert event_keys == ["classify", "refuse"]


# ---------------------------------------------------------------------------
# 6. 向后兼容 — 无 chat_service/generator 仍可编译
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    """无参数调用 create_graph 仍可编译（向后兼容）"""

    def test_create_graph_no_args(self):
        """不传 chat_service 和 generator 时仍可编译"""
        graph = create_graph()
        assert "classify" in graph.nodes
        assert "refuse" in graph.nodes

    def test_create_graph_only_checkpointer(self):
        from langgraph.checkpoint.memory import MemorySaver

        graph = create_graph(checkpointer=MemorySaver())
        assert "classify" in graph.nodes
