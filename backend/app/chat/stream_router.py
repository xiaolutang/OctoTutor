"""SSE 流式对话路由

POST /api/chat/stream — Server-Sent Events 流式对话端点。
使用 graph.stream() 驱动 Agent StateGraph，替代 service.stream_chat()。
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.chat.dependencies import get_graph, get_checkpointer
from app.chat.errors import ChatErrorCode, make_error
from app.chat.schemas import ChatRequest, StreamEvent
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

    使用 graph.astream() 的 stream_mode=["updates"] 驱动 Agent StateGraph。
    遍历节点更新事件，将 updates 映射为 SSE 事件。
    断线检测：每轮迭代检查 is_disconnected()，断线则 break。
    外层兜底：未预期异常 yield INTERNAL_ERROR error event。
    """

    # conversation_id 为 None 时生成 UUID4
    conversation_id = body.conversation_id or str(uuid.uuid4())

    # LangGraph config
    config = {
        "configurable": {
            "thread_id": conversation_id,
            "user_id": user.user_id,
        }
    }

    # 初始输入状态
    input_state = {
        "messages": [],
        "question": body.question,
    }

    async def event_generator():
        try:
            # 使用 stream_mode="updates" 获取节点级更新
            async for node_name, node_output in _iter_graph_updates(
                graph, input_state, config
            ):
                if await http_request.is_disconnected():
                    break

                async for sse_frame in _map_node_to_sse(node_name, node_output):
                    yield sse_frame

            # 流结束
            if not await http_request.is_disconnected():
                yield f"event: done\ndata: null\n\n"

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
        # updates 模式下每个 event 是 dict: {node_name: node_output}
        if isinstance(event, dict):
            for node_name, node_output in event.items():
                yield node_name, node_output


async def _map_node_to_sse(node_name: str, node_output: dict):
    """将 graph 节点输出映射为 SSE 事件帧

    classify → thinking 事件
    retrieve → status(retrieving) + sources 事件
    respond → status(generating) + token 事件（从 AIMessage content 提取）
    refuse → token 事件（拒绝消息）
    """
    if node_name == "classify":
        intent = node_output.get("intent", "")
        yield _sse_frame(
            "thinking",
            {"text": f"意图分类: {intent}", "index": 0},
        )

    elif node_name == "retrieve":
        # status: retrieving
        yield _sse_frame(
            "status",
            {"stage": "retrieving", "message": "正在检索教材..."},
        )

        # sources 事件
        sources = node_output.get("sources", [])
        if sources:
            serialized = [_serialize_source(s) for s in sources]
            yield _sse_frame("sources", serialized)

    elif node_name == "respond":
        # status: generating
        yield _sse_frame(
            "status",
            {"stage": "generating", "message": "正在生成回答..."},
        )

        # 从 AIMessage 提取完整回答作为 token 事件
        messages = node_output.get("messages", [])
        if messages:
            content = messages[0].content if hasattr(messages[0], "content") else str(messages[0])
            yield _sse_frame("token", content)

    elif node_name == "refuse":
        # 拒绝消息直接作为 token 输出
        messages = node_output.get("messages", [])
        if messages:
            content = messages[0].content if hasattr(messages[0], "content") else str(messages[0])
            yield _sse_frame("token", content)


def _sse_frame(event_type: str, data) -> str:
    """构造 SSE 文本帧"""
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _serialize_source(source) -> dict:
    """序列化 SourceReference 为 dict"""
    if hasattr(source, "model_dump"):
        return source.model_dump()
    if hasattr(source, "__dataclass_fields__"):
        return asdict(source)
    return source
