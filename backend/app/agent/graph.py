"""AgentState TypedDict + StateGraph 条件路由编排

graph.compile(checkpointer=...) 返回 CompiledStateGraph.
节点函数来自 nodes.py (classify, refuse) 和闭包 (retrieve, respond).
respond 节点内调用 ChatOpenAI，LangGraph 自动拦截 token 流推给 stream_mode="messages"。
"""

import asyncio
from typing import Literal

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages, RemoveMessage
from typing import Annotated

from app.rag.models import QueryResult
from app.domain.models import SourceReference
from app.infra.context_builder import chunks_to_sources
from app.infra.context_builder import build_numbered_context
from app.agent.prompts import TEACHING_SYSTEM_PROMPT
from app.agent.token_budget import TokenBudget, estimate_tokens


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
    conversation_summary: str
    rewritten_question: str


def _route_by_intent(state: AgentState) -> str:
    if state.get("intent") == "textbook":
        return "rewrite"
    return "refuse"


def _make_summarize(chat_model):
    """创建 summarize 节点闭包（可独立测试）

    超阈值 → LLM 摘要 + RemoveMessage 清理旧消息
    未超阈值 → no-op（return {}）
    """

    async def _summarize(state):
        """summarize 节点 — 超阈值时压缩历史消息"""
        messages = state.get("messages", [])
        existing_summary = state.get("conversation_summary", "")

        # 1. 估算总 token
        total_tokens = estimate_tokens(existing_summary)
        for msg in messages:
            total_tokens += estimate_tokens(msg.content or "")
        total_tokens += TokenBudget.RESERVED_FOR_RAG + TokenBudget.RESERVED_FOR_OUTPUT

        # 2. 未超阈值 → no-op
        threshold = int(TokenBudget.CONTEXT_WINDOW * TokenBudget.SUMMARIZE_THRESHOLD)
        if total_tokens < threshold:
            return {}

        # 3. 超阈值 → 分割消息
        keep_count = TokenBudget.RECENT_MESSAGES_KEEP
        if len(messages) <= keep_count:
            return {}  # 消息太少，不摘要

        to_summarize = messages[:-keep_count]
        to_keep = messages[-keep_count:]

        # 4. 构建 LLM 输入
        from app.agent.prompts import SUMMARIZE_PROMPT

        messages_text = "\n".join(
            f"{'用户' if isinstance(m, HumanMessage) else '助手'}：{m.content}"
            for m in to_summarize
        )
        existing_part = f"已有摘要：{existing_summary}" if existing_summary else ""

        prompt = SUMMARIZE_PROMPT.format(
            existing_summary=existing_part,
            messages_text=messages_text,
        )

        # 5. 调用 LLM
        try:
            response = await chat_model.ainvoke([HumanMessage(content=prompt)])
            new_summary = response.content
        except Exception:
            return {}  # LLM 失败 → no-op，下轮重试

        # 6. 成功 → 返回新摘要 + RemoveMessage 清理旧消息
        remove_messages = [RemoveMessage(id=m.id) for m in to_summarize if m.id]

        return {
            "conversation_summary": new_summary,
            "messages": remove_messages,
        }

    return _summarize


def _make_rewrite(chat_model):
    """创建 rewrite 节点闭包（可独立测试）

    首轮（len(messages)<=1）→ no-op（return {}）
    多轮 → LLM 改写追问为独立问题
    """

    async def _rewrite(state):
        """rewrite 节点 — 多轮时改写追问为独立问题"""
        messages = state.get("messages", [])
        question = state.get("question", "")

        # 1. 首轮（messages 只有当前 HumanMessage 或为空）→ 透传
        if len(messages) <= 1:
            return {}

        # 2. 多轮 → 取最近几轮构建 history
        # 只取最近 6 条消息（3 轮对话）作为 history
        recent = messages[-6:] if len(messages) > 6 else messages[:-1]
        history_lines = []
        for msg in recent:
            role = "用户" if isinstance(msg, HumanMessage) else "助手"
            history_lines.append(f"{role}：{msg.content}")
        history = "\n".join(history_lines)

        # 3. 调用 LLM 改写
        from app.agent.prompts import REWRITE_PROMPT
        prompt = REWRITE_PROMPT.format(history=history, question=question)

        try:
            response = await chat_model.ainvoke([HumanMessage(content=prompt)])
            rewritten = response.content.strip()
            if rewritten:
                return {"rewritten_question": rewritten}
        except Exception:
            pass  # LLM 失败 → fallback 原始 question

        return {}  # fallback：不设 rewritten_question，_retrieve 会用 question

    return _rewrite


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

    _summarize = _make_summarize(chat_model)
    _rewrite = _make_rewrite(chat_model)

    async def _retrieve(state):
        """retrieve 节点 — 调用 ChatService._retrieve 检索管线"""
        # 优先使用 rewritten_question，无则 fallback 到 question
        question = state.get("rewritten_question") or state.get("question", "")
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
        """respond 节点 — 构建完整消息列表并调用 LLM

        消息结构：
        1. SystemMessage：教学策略 + RAG context（动态注入）
        2. SystemMessage（可选）：对话摘要（如存在）
        3. 历史消息（summarize 已清理旧消息，只剩近期）
        4. LLM 调用
        """
        chunks = state.get("context_chunks", [])
        summary = state.get("conversation_summary")
        history = state.get("messages", [])

        # 1. 构建 SystemMessage
        system_content = TEACHING_SYSTEM_PROMPT
        if chunks:
            context_text = build_numbered_context(chunks)
            system_content += f"\n\n以下是检索到的教材内容：\n{context_text}\n请基于以上教材内容回答学生的问题。"

        messages = [SystemMessage(content=system_content)]

        # 2. 摘要 SystemMessage（如存在）
        if summary:
            messages.append(SystemMessage(content=f"以下是之前对话的要点总结：\n{summary}"))

        # 3. 历史消息原样透传（summarize 已清理旧消息，只剩近期）
        messages.extend(history)

        # 4. 调用 LLM
        response = await chat_model.ainvoke(messages)
        return {"messages": [response]}

    # 新拓扑：START → summarize → classify → [rewrite → retrieve → respond | refuse] → END
    graph = StateGraph(AgentState)
    graph.add_node("summarize", _summarize)
    graph.add_node("classify", classify_node)
    graph.add_node("rewrite", _rewrite)
    graph.add_node("retrieve", _retrieve)
    graph.add_node("respond", _respond)
    graph.add_node("refuse", refuse_node)

    graph.add_edge(START, "summarize")
    graph.add_edge("summarize", "classify")
    graph.add_conditional_edges("classify", _route_by_intent)
    graph.add_edge("rewrite", "retrieve")
    graph.add_edge("retrieve", "respond")
    graph.add_edge("respond", END)
    graph.add_edge("refuse", END)
    return graph.compile(checkpointer=checkpointer)
