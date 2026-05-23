"""R007-BF001 单元测试 — AgentState 结构 + graph 编译"""

from langchain_core.messages import HumanMessage

from app.agent.graph import AgentState, create_graph
from app.rag.models import QueryResult, ChunkMetadata
from app.domain.models import SourceReference


class TestAgentState:
    """验证 AgentState TypedDict 结构"""

    def test_construct_full_state(self):
        """构造包含所有字段的 AgentState dict 验证类型正确"""
        state: AgentState = {
            "messages": [HumanMessage(content="什么是集合？")],
            "question": "什么是集合？",
            "intent": "textbook",
            "context_chunks": [
                QueryResult(
                    chunk_id="test::chunk",
                    text="集合的概念...",
                    score=0.95,
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
            ],
            "sources": [
                SourceReference(
                    chunk_id="test::chunk",
                    book="必修第一册",
                    section="1.1 集合",
                    page_start=1,
                    page_end=2,
                )
            ],
            "degraded": False,
            "degradation_reason": None,
        }
        assert state["question"] == "什么是集合？"
        assert state["intent"] == "textbook"
        assert len(state["context_chunks"]) == 1
        assert state["context_chunks"][0].score == 0.95
        assert len(state["sources"]) == 1
        assert state["sources"][0].book == "必修第一册"
        assert state["degraded"] is False
        assert state["degradation_reason"] is None
        assert len(state["messages"]) == 1

    def test_intent_literal_values(self):
        """验证 intent 只接受 textbook / unrelated"""
        state_textbook: AgentState = {
            "messages": [],
            "question": "test",
            "intent": "textbook",
            "context_chunks": [],
            "sources": [],
            "degraded": False,
            "degradation_reason": None,
        }
        assert state_textbook["intent"] == "textbook"

        state_unrelated: AgentState = {
            "messages": [],
            "question": "test",
            "intent": "unrelated",
            "context_chunks": [],
            "sources": [],
            "degraded": False,
            "degradation_reason": None,
        }
        assert state_unrelated["intent"] == "unrelated"


class TestGraphCompilation:
    """验证 graph 可编译"""

    def test_compile_without_checkpointer(self):
        """compile 不抛异常，graph.nodes 包含 classify/retrieve/respond/refuse"""
        graph = create_graph()
        node_names = set(graph.nodes.keys())
        for expected in ("classify", "retrieve", "respond", "refuse"):
            assert expected in node_names, f"missing node: {expected}"

    def test_compile_with_memory_saver(self):
        """compile with MemorySaver 不抛异常"""
        from langgraph.checkpoint.memory import MemorySaver

        checkpointer = MemorySaver()
        graph = create_graph(checkpointer=checkpointer)
        node_names = set(graph.nodes.keys())
        assert "classify" in node_names
        assert "respond" in node_names

    def test_route_by_intent_textbook(self):
        """_route_by_intent textbook -> retrieve"""
        from app.agent.graph import _route_by_intent

        assert _route_by_intent({"intent": "textbook"}) == "retrieve"

    def test_route_by_intent_unrelated(self):
        """_route_by_intent unrelated -> refuse"""
        from app.agent.graph import _route_by_intent

        assert _route_by_intent({"intent": "unrelated"}) == "refuse"
