"""SSE 流式对话路由

POST /api/chat/stream — Server-Sent Events 流式对话端点。
使用 graph.astream(stream_mode="updates") 驱动 Agent StateGraph，
respond 节点只构建 prompt，LLM 逐 token 调用在 router 层执行。
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.chat.dependencies import get_graph, get_checkpointer
from app.chat.errors import ChatErrorCode, make_error
from app.chat.schemas import ChatRequest
from app.middleware.auth import UserContext, get_current_user

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat/stream")
async def stream_chat(
    body: ChatRequest,
    http_request: Request,
    graph=Depends(get_graph),
    checkpointer=Depends(get_checkpointer),
    user: UserContext = Depends(get_current_user),
):
    """SSE 流式对话端点

    使用 graph.astream(stream_mode="updates") 驱动 Agent StateGraph。
    - classify/retrieve 节点由 graph 执行
    - respond 节点只构建 prompt，不调用 LLM
    - LLM 逐 token 流式在 router 层通过 generator.generate_stream() 执行
    """
    from app.chat.dependencies import get_generator

    generator = http_request.app.state.generator
    conversation_id = body.conversation_id or str(uuid.uuid4())

    config = {
        "configurable": {
            "thread_id": conversation_id,
            "user_id": user.user_id,
        }
    }

    input_state = {
        "messages": [],
        "question": body.question,
    }

    async def event_generator():
        try:
            async for node_name, node_output in _iter_graph_updates(
                graph, input_state, config
            ):
                if await http_request.is_disconnected():
                    break

                async for frame in _map_node_to_sse(
                    node_name, node_output, generator, http_request
                ):
                    yield frame

            if not await http_request.is_disconnected():
                yield "event: done\ndata: null\n\n"

        except Exception:
            yield (
                f"event: error\ndata: {json.dumps(make_error(ChatErrorCode.INTERNAL_ERROR), ensure_ascii=False)}\n\n"
            )

    return StreamingResponse(event_generator(), media_type="text/event-stream")


async def _iter_graph_updates(graph, input_state, config):
    """遍历 graph.astream updates，产出 (node_name, node_output) 对"""
    async for event in graph.astream(
        input_state,
        config=config,
        stream_mode="updates",
    ):
        if isinstance(event, dict):
            for node_name, node_output in event.items():
                yield node_name, node_output


async def _map_node_to_sse(node_name: str, node_output: dict, generator, http_request: Request):
    """将 graph 节点输出映射为 SSE 事件帧

    classify → thinking 事件
    retrieve → status(retrieving) + sources 事件
    respond → status(generating) + 逐 token 流式（调用 generator）
    refuse → token 事件（拒绝消息）
    """
    if node_name == "classify":
        intent = node_output.get("intent", "")
        yield _sse_frame(
            "thinking",
            {"text": f"意图分类: {intent}", "index": 0},
        )

    elif node_name == "retrieve":
        yield _sse_frame(
            "status",
            {"stage": "retrieving", "message": "正在检索教材..."},
        )

        sources = node_output.get("sources", [])
        if sources:
            serialized = [_serialize_source(s) for s in sources]
            yield _sse_frame("sources", serialized)

    elif node_name == "respond":
        yield _sse_frame(
            "status",
            {"stage": "generating", "message": "正在生成回答..."},
        )

        # 逐 token 流式：从 respond 节点获取 question + chunks，调用 generator
        question = node_output.get("_question", "")
        chunks = node_output.get("_chunks", [])

        async for token in generator.generate_stream(question, chunks):
            if await http_request.is_disconnected():
                break
            yield _sse_frame("token", token)

    elif node_name == "refuse":
        messages = node_output.get("messages", [])
        if messages:
            content = messages[0].content if hasattr(messages[0], "content") else str(messages[0])
            yield _sse_frame("token", content)


def _sse_frame(event_type: str, data: Any) -> str:
    """构造 SSE 文本帧"""
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _serialize_source(source) -> dict:
    """序列化 SourceReference 为 dict"""
    if hasattr(source, "model_dump"):
        return source.model_dump()
    if hasattr(source, "__dataclass_fields__"):
        return asdict(source)
    return source
