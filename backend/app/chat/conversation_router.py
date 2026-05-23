"""对话历史路由

GET /api/conversations/current — 获取当前用户最近对话的消息列表。
通过 LangGraph checkpointer 加载 checkpoint，提取 messages 转换为 ApiMessage 格式。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.chat.dependencies import get_checkpointer
from app.chat.schemas import ApiMessage, ThinkingPayload
from app.middleware.auth import UserContext, get_current_user

router = APIRouter(prefix="/api", tags=["conversations"])


@router.get("/conversations/current")
async def get_current_conversation(
    request: Request,
    checkpointer=Depends(get_checkpointer),
    user: UserContext = Depends(get_current_user),
):
    """获取当前用户最近对话

    从 checkpointer 加载最新 checkpoint，提取 messages。
    - 有消息 → 200 + {conversation_id, messages}
    - 无消息 → 204 No Content
    """
    # 尝试从 checkpointer 获取该用户的最近 thread
    conversation_id, messages = await _load_latest_conversation(
        checkpointer, user.user_id
    )

    if not messages:
        return JSONResponse(status_code=204, content=None)

    # 转换为 ApiMessage 格式
    api_messages = [_to_api_message(msg, idx) for idx, msg in enumerate(messages)]

    return JSONResponse(
        status_code=200,
        content={
            "conversation_id": conversation_id,
            "messages": [msg.model_dump() for msg in api_messages],
        },
    )


async def _load_latest_conversation(checkpointer, user_id: str):
    """从 checkpointer 加载用户最近的对话

    LangGraph checkpointer 的 list 掏不出来直接按 user_id 过滤，
    这里使用 thread_id = user_id 作为约定（与 stream_router 一致），
    直接通过 get_tuple 加载最新 checkpoint。
    """
    try:
        # 用 user_id 作为 thread_id 查找最近对话
        config = {"configurable": {"thread_id": user_id}}
        checkpoint_tuple = await checkpointer.aget_tuple(config)

        if checkpoint_tuple is None:
            return None, []

        # 提取 checkpoint 中的 messages
        checkpoint = checkpoint_tuple.checkpoint
        if not checkpoint:
            return None, []

        channel_values = checkpoint.get("channel_values", {})
        messages = channel_values.get("messages", [])

        return user_id, messages

    except Exception:
        return None, []


def _to_api_message(msg, index: int) -> ApiMessage:
    """将 LangGraph message 转换为 ApiMessage 格式

    ApiMessage 包含 7 个字段：id/role/content/status/sources/thinking_steps/created_at
    """
    # 提取基本属性
    msg_id = getattr(msg, "id", None) or str(index)
    content = getattr(msg, "content", "") or ""
    msg_type = getattr(msg, "type", "unknown")

    # 映射 role
    role_map = {
        "human": "user",
        "ai": "assistant",
        "system": "system",
    }
    role = role_map.get(msg_type, msg_type)

    # 提取 additional_kwargs 中的 sources 和 thinking_steps
    additional_kwargs = getattr(msg, "additional_kwargs", {}) or {}

    sources = []
    raw_sources = additional_kwargs.get("sources", [])
    if raw_sources:
        from app.domain.models import SourceReference
        for s in raw_sources:
            if isinstance(s, SourceReference):
                sources.append(s)
            elif isinstance(s, dict):
                try:
                    sources.append(SourceReference(**s))
                except Exception:
                    pass

    thinking_steps = []
    raw_thinking = additional_kwargs.get("thinking_steps", [])
    if raw_thinking:
        for t in raw_thinking:
            if isinstance(t, ThinkingPayload):
                thinking_steps.append(t)
            elif isinstance(t, dict):
                try:
                    thinking_steps.append(ThinkingPayload(**t))
                except Exception:
                    pass

    # 提取 created_at
    created_at = ""
    response_metadata = getattr(msg, "response_metadata", {}) or {}
    if "created_at" in response_metadata:
        created_at = response_metadata["created_at"]

    return ApiMessage(
        id=str(msg_id),
        role=role,
        content=content,
        status="completed",
        sources=sources,
        thinking_steps=thinking_steps,
        created_at=created_at,
    )
