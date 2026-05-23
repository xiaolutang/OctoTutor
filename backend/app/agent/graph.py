"""AgentState TypedDict + StateGraph 骨架

graph.compile(checkpointer=...) 返回 CompiledStateGraph,
后续节点实现在 nodes.py 中逐步替换 stub lambda.
"""

from typing import Literal

from langchain_core.messages import BaseMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from typing import Annotated

from app.rag.models import QueryResult
from app.domain.models import SourceReference


class AgentState(dict):
    """LangGraph 图状态

    Attributes:
        messages: 对话消息列表（add_messages reducer）
        question: 当前用户问题
        intent: 分类结果 "textbook" | "unrelated"
        context_chunks: RAG 检索到的 chunk 列表
        sources: 引用来源列表
        degraded: 是否处于降级模式
        degradation_reason: 降级原因
    """

    messages: Annotated[list[BaseMessage], add_messages]
    question: str
    intent: Literal["textbook", "unrelated"]
    context_chunks: list[QueryResult]
    sources: list[SourceReference]
    degraded: bool
    degradation_reason: str | None


def _route_by_intent(state: AgentState) -> str:
    if state.get("intent") == "textbook":
        return "retrieve"
    return "refuse"


def create_graph(checkpointer=None):
    """创建并编译 Agent StateGraph

    Args:
        checkpointer: LangGraph checkpointer 实例
            (AsyncPostgresSaver / MemorySaver)

    Returns:
        CompiledStateGraph: 编译后的可执行图
    """
    graph = StateGraph(AgentState)
    graph.add_node("classify", lambda state: {})
    graph.add_node("retrieve", lambda state: {})
    graph.add_node("respond", lambda state: {})
    graph.add_node("refuse", lambda state: {})
    graph.add_edge(START, "classify")
    graph.add_conditional_edges("classify", _route_by_intent)
    graph.add_edge("retrieve", "respond")
    graph.add_edge("respond", END)
    graph.add_edge("refuse", END)
    return graph.compile(checkpointer=checkpointer)
