"""AgentState TypedDict + StateGraph 线性拓扑编排

graph.compile(checkpointer=...) 返回 CompiledStateGraph.
拓扑：START → summarize → rewrite → retrieve → respond → END（纯线性，无分支）
respond 节点内调用 ChatOpenAI，LangGraph 自动拦截 token 流推给 stream_mode="messages"。
"""

import asyncio

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages, RemoveMessage
from typing import Annotated

from app.rag.models import QueryResult
from app.domain.models import SourceReference
from app.infra.context_builder import chunks_to_sources
from app.infra.context_builder import build_numbered_context
from app.agent.prompts import TEACHING_SYSTEM_PROMPT, SUMMARIZE_PROMPT, REWRITE_PROMPT
from app.agent.token_budget import TokenBudget, estimate_tokens
from app.config import settings


class AgentState(dict):
    """LangGraph 图状态

    Attributes:
        messages: 对话消息列表（add_messages reducer）
        question: 当前用户问题
        intent: deprecated — 保留字段用于向后兼容旧 checkpoint，新流程不再设置
        context_chunks: RAG 检索到的 chunk 列表
        sources: 引用来源列表
        degraded: 是否处于降级模式
        degradation_reason: 降级原因
        conversation_summary: 对话摘要
        rewritten_question: 改写后的问题
    """

    messages: Annotated[list[BaseMessage], add_messages]
    question: str
    intent: str  # deprecated: 保留向后兼容旧 checkpoint
    context_chunks: list[QueryResult]
    sources: list[SourceReference]
    degraded: bool
    degradation_reason: str | None
    conversation_summary: str
    rewritten_question: str


def _format_msg_line(msg: BaseMessage) -> str:
    """将消息格式化为 '角色：内容' 行"""
    role = "用户" if isinstance(msg, HumanMessage) else "助手"
    return f"{role}：{msg.content}"


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

        # 4. 构建 LLM 输入
        messages_text = "\n".join(_format_msg_line(m) for m in to_summarize)
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
        history = "\n".join(_format_msg_line(msg) for msg in recent)

        # 3. 调用 LLM 改写
        prompt = REWRITE_PROMPT.format(history=history, question=question)

        try:
            response = await chat_model.ainvoke([HumanMessage(content=prompt)])
            rewritten = response.content.strip()
            if rewritten:
                return {"rewritten_question": rewritten}
        except Exception:
            pass  # LLM 失败 → fallback 原始 question

        return {}  # fallback：不设 rewritten_question，retrieve 节点会用 question

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
    # 从 generator 获取 ChatOpenAI 实例（支持原生 streaming）
    chat_model = generator.get_chat_model()

    _summarize = _make_summarize(chat_model)
    _rewrite = _make_rewrite(chat_model)

    async def _retrieve(state):
        """retrieve 节点 — 调用 ChatService.retrieve 检索管线"""
        # 优先使用 rewritten_question，无则 fallback 到 question
        question = state.get("rewritten_question") or state.get("question", "")
        top_k = 10

        result = await asyncio.to_thread(chat_service.retrieve, question, top_k)

        chunks = result.chunks
        sources = chunks_to_sources(chunks)

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

        # 1. 构建 SystemMessage（分级 context 注入）
        system_content = TEACHING_SYSTEM_PROMPT
        if chunks:
            context_text = build_numbered_context(chunks)
            degraded = state.get("degraded", False)

            if not degraded:
                best_score = max(c.score for c in chunks)
                if best_score >= settings.relevance_threshold:
                    # 高相关性 — 强约束
                    system_content += (
                        f"\n\n以下是检索到的教材内容：\n{context_text}\n"
                        "请严格基于以上教材内容回答。只使用教材中明确出现的信息，不要编造教材中没有的内容。"
                    )
                else:
                    # 低相关性 — 弱参考
                    system_content += (
                        f"\n\n以下是一些可能相关的参考内容：\n{context_text}\n"
                        "如果这些内容与学生的问题相关，可以参考使用；如果不相关，基于你的知识回答并标注'教材中未直接涉及'。"
                    )
            else:
                # 降级 — 弱参考（reranker 分数不可信）
                system_content += (
                    f"\n\n以下是一些可能相关的参考内容：\n{context_text}\n"
                    "如果这些内容与学生的问题相关，可以参考使用；如果不相关，基于你的知识回答并标注'教材中未直接涉及'。"
                )

        messages = [SystemMessage(content=system_content)]

        # 2. 摘要 SystemMessage（如存在）
        if summary:
            messages.append(SystemMessage(content=f"以下是之前对话的要点总结：\n{summary}"))

        # 3. 历史消息原样透传（summarize 已清理旧消息，只剩近期）
        messages.extend(history)

        # 4. 调用 LLM
        response = await chat_model.ainvoke(messages)
        return {"messages": [response]}

    # 线性拓扑：START → summarize → rewrite → retrieve → respond → END
    graph = StateGraph(AgentState)
    graph.add_node("summarize", _summarize)
    graph.add_node("rewrite", _rewrite)
    graph.add_node("retrieve", _retrieve)
    graph.add_node("respond", _respond)

    graph.add_edge(START, "summarize")
    graph.add_edge("summarize", "rewrite")
    graph.add_edge("rewrite", "retrieve")
    graph.add_edge("retrieve", "respond")
    graph.add_edge("respond", END)
    return graph.compile(checkpointer=checkpointer)
