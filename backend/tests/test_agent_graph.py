"""R007-BF001 单元测试 — AgentState 结构 + graph 编译（线性拓扑）

拓扑：START → summarize → rewrite → retrieve → respond → END
"""

from unittest.mock import MagicMock

from langchain_core.messages import HumanMessage

from app.agent.graph import AgentState, create_graph
from app.rag.models import QueryResult, ChunkMetadata
from app.domain.models import SourceReference


def _mock_generator():
    """构造 mock LLMGenerator，提供 get_chat_model"""
    gen = MagicMock()
    gen.get_chat_model.return_value = MagicMock()
    return gen


class TestAgentState:
    """验证 AgentState TypedDict 结构"""

    def test_construct_full_state(self):
        """构造包含所有字段的 AgentState dict 验证类型正确"""
        state: AgentState = {
            "messages": [HumanMessage(content="什么是集合？")],
            "question": "什么是集合？",
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
        assert len(state["context_chunks"]) == 1
        assert state["context_chunks"][0].score == 0.95
        assert len(state["sources"]) == 1
        assert state["sources"][0].book == "必修第一册"
        assert state["degraded"] is False
        assert state["degradation_reason"] is None
        assert len(state["messages"]) == 1


class TestGraphCompilation:
    """验证 graph 可编译 — 线性拓扑（4 个节点）"""

    def test_compile_without_checkpointer(self):
        """compile 不抛异常，graph.nodes 包含 summarize/rewrite/retrieve/respond"""
        graph = create_graph(generator=_mock_generator())
        node_names = set(graph.nodes.keys())
        for expected in ("summarize", "rewrite", "retrieve", "respond"):
            assert expected in node_names, f"missing node: {expected}"

    def test_compile_with_memory_saver(self):
        """compile with MemorySaver 不抛异常"""
        from langgraph.checkpoint.memory import MemorySaver

        checkpointer = MemorySaver()
        graph = create_graph(checkpointer=checkpointer, generator=_mock_generator())
        node_names = set(graph.nodes.keys())
        assert "respond" in node_names
        assert "retrieve" in node_names
        assert "classify" not in node_names
        assert "refuse" not in node_names

    def test_linear_topology_four_nodes(self):
        """验证线性拓扑恰好 4 个节点"""
        graph = create_graph(generator=_mock_generator())
        node_names = set(graph.nodes.keys())
        # 去掉 __start__ 和 __end__（LangGraph 内部节点）
        real_nodes = node_names - {"__start__", "__end__"}
        assert real_nodes == {"summarize", "rewrite", "retrieve", "respond"}


class TestContentToStr:
    """验证 _content_to_str() 处理 str / list[dict] / 其他类型"""

    def test_string_passthrough(self):
        """string 原样返回"""
        from app.agent.graph import _content_to_str
        assert _content_to_str("hello") == "hello"

    def test_list_of_text_blocks(self):
        """list[dict] 拼接所有 text block"""
        from app.agent.graph import _content_to_str
        content = [
            {"type": "text", "text": "识别结果"},
            {"type": "text", "text": "用户问题"},
        ]
        assert _content_to_str(content) == "识别结果\n用户问题"

    def test_empty_list(self):
        """空 list 返回空串"""
        from app.agent.graph import _content_to_str
        assert _content_to_str([]) == ""

    def test_non_text_blocks_filtered(self):
        """非 text 类型的 block 被过滤"""
        from app.agent.graph import _content_to_str
        content = [
            {"type": "image_url", "image_url": {"url": "data:..."}},
            {"type": "text", "text": "hello"},
        ]
        assert _content_to_str(content) == "hello"

    def test_fallback_to_str(self):
        """其他类型 fallback 为 str()"""
        from app.agent.graph import _content_to_str
        assert _content_to_str(42) == "42"
