"""SSE 流式对话路由

POST /api/chat/stream — Server-Sent Events 流式对话端点。
使用 graph.astream(stream_mode=["updates","messages"]) 驱动 Agent StateGraph：
- updates 事件：节点完成时推送 thinking/status/sources
- messages 事件：respond 节点内 LLM 逐 token 流式输出
respond 节点在 graph 内部调用 ChatOpenAI，PostgresSaver 自动保存 AIMessage checkpoint。
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict
from typing import Any

from langchain_core.messages import HumanMessage

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.dependencies import get_graph, get_checkpointer, get_db
from app.chat.errors import ChatErrorCode, ConversationErrorCode, make_error, make_conversation_error
from app.chat.schemas import ChatRequest
from app.domain.models import Conversation
from app.infra.conversation_repo import ConversationRepo
from app.middleware.auth import UserContext, get_current_user

router = APIRouter(prefix="/api", tags=["chat"])

logger = logging.getLogger(__name__)


@router.post("/chat/stream")
async def stream_chat(
    body: ChatRequest,
    http_request: Request,
    graph=Depends(get_graph),
    checkpointer=Depends(get_checkpointer),
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """SSE 流式对话端点

    使用 graph.astream(stream_mode=["updates","messages"]) 驱动 Agent StateGraph。
    - updates：summarize/rewrite/retrieve/respond 节点完成时推送状态事件
    - messages：respond 节点内 LLM 逐 token 流式推送
    - respond 节点完成后 PostgresSaver 自动保存 AIMessage
    """
    conversation_id = body.conversation_id or str(uuid.uuid4())
    is_new_conversation = not body.conversation_id

    # 已有 conversation_id：归属校验
    if not is_new_conversation:
        try:
            conv = await ConversationRepo.get_by_id(db, conversation_id, user.user_id)
            if conv is None:
                # 归属校验失败：对话不存在或无权访问
                return StreamingResponse(
                    _single_error_event(make_conversation_error(ConversationErrorCode.NOT_FOUND)),
                    media_type="text/event-stream",
                )
        except Exception as e:
            logger.error(f"[stream] conversation ownership check failed: {e}", exc_info=True)
            return StreamingResponse(
                _single_error_event(make_error(ChatErrorCode.INTERNAL_ERROR)),
                media_type="text/event-stream",
            )

    # 新对话：init 阶段前创建 conversation 记录
    if is_new_conversation:
        conv = Conversation(id=conversation_id, user_id=user.user_id)
        await ConversationRepo.create(db, conv)
        await db.commit()

    config = {
        "configurable": {
            "thread_id": conversation_id,
            "user_id": user.user_id,
        }
    }

    # 将用户问题作为 HumanMessage 传入 graph state，checkpointer 自动持久化
    input_state = {
        "messages": [HumanMessage(content=body.question)],
        "question": body.question,
    }

    async def event_generator():
        try:
            # 首个事件：回传 conversation_id 给前端
            yield _sse_frame("init", {"conversation_id": conversation_id})

            async for event in graph.astream(
                input_state,
                config=config,
                stream_mode=["updates", "messages"],
            ):
                if await http_request.is_disconnected():
                    break

                async for frame in _map_event_to_sse(event, http_request):
                    yield frame

            if not await http_request.is_disconnected():
                # 更新统计：updated_at + message_count
                try:
                    await ConversationRepo.update_message_stats(db, conversation_id)
                    await db.commit()
                except Exception as e:
                    logger.warning(f"[stream] update_message_stats failed: {e}")

                yield "event: done\ndata: null\n\n"

                # 新对话：尝试生成标题
                if is_new_conversation:
                    try:
                        generator = http_request.app.state.generator
                        title = await generator.generate_title(body.question)
                        if title:
                            await ConversationRepo.update(
                                db, conversation_id, user.user_id, title=title
                            )
                            await db.commit()
                            yield _sse_frame("title", {
                                "conversation_id": conversation_id,
                                "title": title,
                            })
                    except Exception as e:
                        logger.warning(f"[stream] title generation failed: {e}")

        except Exception as e:
            logger.error(f"SSE stream error: {e}", exc_info=True)
            yield (
                f"event: error\ndata: {json.dumps(make_error(ChatErrorCode.INTERNAL_ERROR), ensure_ascii=False)}\n\n"
            )

    return StreamingResponse(event_generator(), media_type="text/event-stream")


async def _map_event_to_sse(event, http_request: Request):
    """将 graph.astream 双流事件映射为 SSE 帧

    双流事件格式：
    - updates: ("updates", {node_name: node_output})
    - messages: ("messages", (AIMessageChunk, metadata))
    """
    if not isinstance(event, tuple) or len(event) != 2:
        return

    stream_type, data = event

    if stream_type == "updates":
        # 节点完成事件 — data 是 {node_name: node_output}
        if not isinstance(data, dict):
            return
        for node_name, node_output in data.items():
            async for frame in _map_node_update_to_sse(node_name, node_output):
                yield frame

    elif stream_type == "messages":
        # LLM token 事件 — data 是 (message_chunk, metadata)
        if not isinstance(data, tuple) or len(data) != 2:
            return
        message_chunk, metadata = data
        # 只推送 respond 节点的 token（其他节点的 messages 事件忽略）
        node_name = metadata.get("langgraph_node", "")
        if node_name == "respond":
            token = getattr(message_chunk, "content", "")
            if token:
                yield _sse_frame("token", token)


async def _map_node_update_to_sse(node_name: str, node_output: dict):
    """将节点完成事件映射为 SSE 帧"""
    if node_name == "summarize":
        summary = node_output.get("conversation_summary") if node_output else None
        if summary:
            yield _sse_frame("thinking", {"text": "上下文已压缩", "index": 0})

    elif node_name == "rewrite":
        rewritten = node_output.get("rewritten_question") if node_output else None
        if rewritten:
            yield _sse_frame("thinking", {"text": f"查询改写: {rewritten}", "index": 1})

    elif node_name == "retrieve":
        yield _sse_frame(
            "status",
            {"stage": "retrieving", "message": "正在检索教材..."},
        )

        sources = node_output.get("sources", []) if node_output else []
        if sources:
            serialized = [_serialize_source(s) for s in sources]
            yield _sse_frame("sources", serialized)

    elif node_name == "respond":
        yield _sse_frame(
            "status",
            {"stage": "generating", "message": "正在生成回答..."},
        )
        # respond 节点完成后，AIMessage 已由 PostgresSaver 自动保存
        # token 级别的事件已通过 messages 流推送，此处无需额外处理


def _sse_frame(event_type: str, data: Any) -> str:
    """构造 SSE 文本帧"""
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _single_error_event(error: dict):
    """仅 yield 一帧 SSE error 事件的异步生成器"""
    yield _sse_frame("error", error)


def _serialize_source(source) -> dict:
    """序列化 SourceReference 为 dict"""
    if hasattr(source, "model_dump"):
        return source.model_dump()
    if hasattr(source, "__dataclass_fields__"):
        return asdict(source)
    return source
