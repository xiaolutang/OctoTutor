"""SSE 流式对话路由

POST /api/chat/stream — Server-Sent Events 流式对话端点。
与 POST /api/chat（非流式）独立并存。
"""

from __future__ import annotations

import json
from dataclasses import asdict

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.chat.dependencies import get_chat_service
from app.chat.errors import ChatErrorCode, make_error
from app.chat.schemas import ChatRequest, StreamEvent
from app.chat.service import ChatService

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat/stream")
async def stream_chat(
    body: ChatRequest,
    http_request: Request,
    service: ChatService = Depends(get_chat_service),
):
    """SSE 流式对话端点

    遍历 service.stream_chat() 产出的事件，序列化为 SSE 文本格式。
    断线检测：每轮迭代检查 is_disconnected()，断线则 break（不 yield error）。
    外层兜底：未预期异常 yield INTERNAL_ERROR error event。
    """

    async def event_generator():
        try:
            async for event in service.stream_chat(body.question, body.top_k):
                if await http_request.is_disconnected():
                    break
                serialized = _serialize_event_data(event)
                yield f"event: {event.type}\ndata: {json.dumps(serialized, ensure_ascii=False)}\n\n"
        except Exception:
            yield (
                f"event: error\ndata: {json.dumps(make_error(ChatErrorCode.INTERNAL_ERROR), ensure_ascii=False)}\n\n"
            )

    return StreamingResponse(event_generator(), media_type="text/event-stream")


def _serialize_event_data(event: StreamEvent):
    """序列化 StreamEvent.data 为 JSON 兼容对象

    处理顺序：Pydantic model_dump() > dataclass asdict() > list 递归 > 原始值
    """
    data = event.data
    if data is None:
        return None
    if hasattr(data, "model_dump"):
        return data.model_dump()
    if hasattr(data, "__dataclass_fields__"):
        return asdict(data)
    if isinstance(data, list):
        return [
            item.model_dump() if hasattr(item, "model_dump")
            else asdict(item) if hasattr(item, "__dataclass_fields__")
            else item
            for item in data
        ]
    return data
