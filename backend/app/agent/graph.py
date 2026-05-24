"""AgentState TypedDict + StateGraph 条件路由编排

graph.compile(checkpointer=...) 返回 CompiledStateGraph.
节点函数来自 nodes.py (classify, refuse) 和闭包 (retrieve, respond).
respond 节点内调用 ChatOpenAI，LangGraph 自动拦截 token 流推给 stream_mode="messages"。
"""

import asyncio
from typing import Literal

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from typing import Annotated

from app.rag.models import QueryResult
from app.domain.models import SourceReference
from app.infra.context_builder import chunks_to_sources
from app.infra.context_builder import build_numbered_context
from app.agent.prompts import TEACHING_SYSTEM_PROMPT


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


def create_graph(checkpointer=None, chat_service=None, generator=None):
    """创建并编译 Agent StateGraph

    Args:
        checkpointer: LangGraph checkpointer 实例
            (AsyncPostgresSaver / MemorySaver)
        chat_service: ChatService 实例，用于 retrieve 节点检索
        generator: LLMGenerator 实例，用于提取 api_key/base_url/model 构建 ChatOpenAI

    Returns:
        CompiledStateGraph: 编译后的可执行图
    """
    from app.agent.nodes import classify_node, refuse_node

    # 从 generator 获取 ChatOpenAI 实例（支持原生 streaming）
    chat_model = generator.get_chat_model()

    async def _retrieve(state):
        """retrieve 节点 — 调用 ChatService._retrieve 检索管线"""
        question = state.get("question", "")
        top_k = 10

        result = await asyncio.to_thread(chat_service._retrieve, question, top_k)

        chunks = result.chunks
        sources = chunks_to_sources(chunks) if chunks else []

        return {
            "context_chunks": chunks,
            "sources": sources,
            "degraded": result.degraded,
            "degradation_reason": result.degradation_reason,
        }

    async def _respond(state):
        """respond 节点 — 调用 ChatOpenAI 流式生成回答

        LLM 在 graph 节点内调用，LangGraph 自动拦截 token 流推给 stream_mode="messages"。
        节点完成后 PostgresSaver 自动保存 AIMessage 到 checkpoint。
        """
        question = state.get("question", "")
        chunks = state.get("context_chunks", [])

        # 构建 messages
        if chunks:
            context_text = build_numbered_context(chunks)
            user_content = f"参考教材内容：\n{context_text}\n\n学生问题：{question}"
            messages = [
                SystemMessage(content=TEACHING_SYSTEM_PROMPT),
                HumanMessage(content=user_content),
            ]
        else:
            # 无检索结果时使用简化 prompt
            messages = [
                SystemMessage(content=TEACHING_SYSTEM_PROMPT),
                HumanMessage(content=question),
            ]

        # 调用 ChatOpenAI（streaming=True），LangGraph 拦截 token 流
        response = await chat_model.ainvoke(messages)

        # 返回 AIMessage 写入 state.messages，PostgresSaver 自动 checkpoint
        return {"messages": [response]}

    graph = StateGraph(AgentState)
    graph.add_node("classify", classify_node)
    graph.add_node("retrieve", _retrieve)
    graph.add_node("respond", _respond)
    graph.add_node("refuse", refuse_node)
    graph.add_edge(START, "classify")
    graph.add_conditional_edges("classify", _route_by_intent)
    graph.add_edge("retrieve", "respond")
    graph.add_edge("respond", END)
    graph.add_edge("refuse", END)
    return graph.compile(checkpointer=checkpointer)
