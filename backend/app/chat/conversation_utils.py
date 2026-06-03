"""对话共享工具函数

从 conversation_router.py 提取的公共函数，供 stream_router.py 和 conversation_router.py 复用。
"""

from __future__ import annotations

import logging

from app.chat.schemas import ApiMessage, ThinkingPayload
from app.domain.models import SourceReference

logger = logging.getLogger(__name__)


def extract_latest_messages(namespaces: dict, user_id: str | None = None) -> tuple[list, str]:
    """从 MemorySaver namespaces 提取最新 messages（可选按 user_id 过滤）

    Returns:
        (messages, ts) tuple — 最新消息列表和时间戳
    """
    best_messages = []
    best_ts = ""
    for _ns, checkpoints in namespaces.items():
        for _cp_id, (checkpoint, meta, _parent) in checkpoints.items():
            # user_id 过滤
            if user_id:
                cp_user_id = meta.get("configurable", {}).get("user_id") if meta else None
                if cp_user_id and cp_user_id != user_id:
                    continue
            channel_values = checkpoint.get("channel_values", {})
            messages = channel_values.get("messages", [])
            ts = checkpoint.get("ts", "")
            if messages and ts >= best_ts:
                best_ts = ts
                best_messages = messages
    return best_messages, best_ts


async def load_conversation_by_id(checkpointer, conversation_id: str, user_id: str):
    """通过 conversation_id 直接加载指定对话，验证 user_id 归属

    公共 API — 被 conversation_router 和 stream_router 共同使用。
    """
    try:
        # MemorySaver：直接从 storage 读取
        if hasattr(checkpointer, "storage"):
            if conversation_id not in checkpointer.storage:
                return []
            namespaces = checkpointer.storage[conversation_id]
            messages, _ = extract_latest_messages(
                {conversation_id: namespaces}, user_id
            )
            return messages

        # PostgresSaver：alist 返回带 config 的 CheckpointTuple，可验证 user_id
        config = {"configurable": {"thread_id": conversation_id}}
        async for tuple_item in checkpointer.alist(config, limit=1):
            cp_user_id = tuple_item.config.get("configurable", {}).get("user_id")
            if cp_user_id and cp_user_id != user_id:
                return []
            checkpoint = tuple_item.checkpoint
            if not checkpoint:
                return []
            channel_values = checkpoint.get("channel_values", {})
            return channel_values.get("messages", [])
        return []
    except Exception as e:
        logger.warning(f"[conversation] load by id failed: {e}")
        return []


def to_api_message(msg, index: int) -> ApiMessage:
    """将 LangGraph message 转换为 ApiMessage 格式

    公共 API — 被 conversation_router 和 stream_router 共同使用。
    """
    msg_id = getattr(msg, "id", None) or str(index)
    content = getattr(msg, "content", "") or ""
    msg_type = getattr(msg, "type", "unknown")

    role = msg_type

    additional_kwargs = getattr(msg, "additional_kwargs", {}) or {}

    sources = []
    raw_sources = additional_kwargs.get("sources", [])
    if raw_sources:
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
