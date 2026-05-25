"""对话历史路由

GET  /api/conversations/current  — 获取当前用户最近对话的消息列表。
GET  /api/conversations          — 分页列表（游标）。
PATCH /api/conversations/{id}    — 更新对话（重命名 / 置顶）。
DELETE /api/conversations/{id}   — 删除对话。
"""

from __future__ import annotations

import base64
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.dependencies import get_checkpointer, get_db
from app.chat.errors import ConversationErrorCode, make_conversation_error
from app.chat.schemas import (
    ApiMessage,
    ConversationItemResponse,
    ConversationListResponse,
    ConversationUpdateRequest,
    ThinkingPayload,
)
from app.domain.models import SourceReference
from app.infra.conversation_repo import ConversationRepo
from app.middleware.auth import UserContext, get_current_user

router = APIRouter(prefix="/api", tags=["conversations"])

logger = logging.getLogger(__name__)


@router.get("/conversations/current")
async def get_current_conversation(
    conversation_id: str | None = None,
    checkpointer=Depends(get_checkpointer),
    user: UserContext = Depends(get_current_user),
):
    """获取当前用户最近对话

    必须传 conversation_id 参数精确加载指定 thread。
    未传 conversation_id 时尝试返回最新有效对话。
    - 有消息 → 200 + {conversation_id, messages}
    - 无消息 → 204 No Content
    """
    if conversation_id:
        messages = await _load_conversation_by_id(checkpointer, conversation_id, user.user_id)
    else:
        conversation_id, messages = await _load_latest_conversation(
            checkpointer, user.user_id
        )

    if not messages:
        return Response(status_code=204)

    # 转换为 ApiMessage 格式
    api_messages = [_to_api_message(msg, idx) for idx, msg in enumerate(messages)]

    return JSONResponse(
        status_code=200,
        content={
            "conversation_id": conversation_id,
            "messages": [msg.model_dump() for msg in api_messages],
        },
    )


async def _load_conversation_by_id(checkpointer, conversation_id: str, user_id: str):
    """通过 conversation_id 直接加载指定对话，验证 user_id 归属"""
    try:
        # MemorySaver：直接从 storage 读取
        if hasattr(checkpointer, "storage"):
            if conversation_id not in checkpointer.storage:
                return []
            namespaces = checkpointer.storage[conversation_id]
            messages, _ = _extract_latest_messages(
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


def _extract_latest_messages(namespaces: dict, user_id: str | None = None) -> tuple[list, str]:
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


async def _load_latest_conversation(checkpointer, user_id: str):
    """从 checkpointer 加载用户最近的对话（fallback：无 conversation_id 时使用）"""
    try:
        if hasattr(checkpointer, "storage"):
            return await _load_from_memory_saver(checkpointer, user_id)
        return await _load_from_postgres_saver(checkpointer, user_id)
    except Exception as e:
        logger.warning(f"[conversation] load failed: {e}")
        return None, []


async def _load_from_memory_saver(checkpointer, user_id: str):
    """从 MemorySaver 加载最新有效 thread"""
    best_thread_id = None
    best_messages = []
    best_ts = ""

    for thread_id, namespaces in checkpointer.storage.items():
        if not thread_id or thread_id in ("undefined", "null", ""):
            continue
        messages, ts = _extract_latest_messages({thread_id: namespaces}, user_id)
        if messages and ts >= best_ts:
            best_ts = ts
            best_thread_id = thread_id
            best_messages = messages

    if best_messages:
        return best_thread_id, best_messages
    return None, []


async def _load_from_postgres_saver(checkpointer, user_id: str):
    """从 PostgresSaver 加载最新有效 thread（按时间戳倒序，跳过无效 thread_id）"""
    best_thread_id = None
    best_messages = []
    best_ts = ""

    async for tuple_item in checkpointer.alist(None, limit=100):
        tid = tuple_item.config.get("configurable", {}).get("thread_id")
        if not tid or tid in ("undefined", "null", ""):
            continue
        # user_id 过滤
        tid_user_id = tuple_item.config.get("configurable", {}).get("user_id")
        if tid_user_id and tid_user_id != user_id:
            continue
        checkpoint = tuple_item.checkpoint
        if not checkpoint:
            continue
        ts = checkpoint.get("ts", "")
        channel_values = checkpoint.get("channel_values", {})
        messages = channel_values.get("messages", [])
        if messages and ts > best_ts:
            best_ts = ts
            best_thread_id = tid
            best_messages = messages

    if best_messages:
        logger.info(f"[conversation] fallback thread={best_thread_id}, msgs={len(best_messages)}")
        return best_thread_id, best_messages
    return None, []


def _to_api_message(msg, index: int) -> ApiMessage:
    """将 LangGraph message 转换为 ApiMessage 格式"""
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


# ---------------------------------------------------------------------------
# Conversation CRUD 端点 (R009)
# ---------------------------------------------------------------------------


def _conv_to_response(conv: Conversation) -> ConversationItemResponse:
    """ORM Conversation → ConversationItemResponse"""
    return ConversationItemResponse(
        id=conv.id,
        title=conv.title,
        pinned=conv.pinned,
        pinned_at=conv.pinned_at,
        message_count=conv.message_count,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
    )


@router.get("/conversations")
async def list_conversations(
    cursor: str | None = Query(None),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """分页列表（游标）— 首页返回置顶 + 普通，翻页只返回普通"""
    items, has_more = await ConversationRepo.list_by_user(db, user.user_id, cursor, limit)

    response_items = [_conv_to_response(item) for item in items]

    next_cursor = None
    if has_more and items:
        last = items[-1]
        raw = f"{last.updated_at.isoformat()}|{last.id}"
        next_cursor = base64.b64encode(raw.encode()).decode()

    return ConversationListResponse(items=response_items, cursor=next_cursor, has_more=has_more)


@router.patch("/conversations/{conversation_id}")
async def update_conversation(
    conversation_id: str,
    body: ConversationUpdateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """更新对话 — 重命名 / 置顶 / 取消置顶"""
    conv = await ConversationRepo.get_by_id(db, conversation_id, user.user_id)
    if not conv:
        return JSONResponse(status_code=404, content=make_conversation_error(ConversationErrorCode.NOT_FOUND))

    updates = {}

    if body.title is not None:
        if not body.title.strip() or len(body.title) > 200:
            return JSONResponse(status_code=400, content=make_conversation_error(ConversationErrorCode.TITLE_INVALID))
        updates["title"] = body.title.strip()

    if body.pinned is not None:
        if body.pinned and not conv.pinned:
            count = await ConversationRepo.count_pinned(db, user.user_id)
            if count >= 5:
                return JSONResponse(status_code=400, content=make_conversation_error(ConversationErrorCode.PIN_LIMIT))
            updates["pinned"] = True
            updates["pinned_at"] = datetime.now(timezone.utc)
        elif not body.pinned and conv.pinned:
            updates["pinned"] = False
            updates["pinned_at"] = None

    if updates:
        conv = await ConversationRepo.update(db, conversation_id, user.user_id, **updates)
        await db.commit()

    return _conv_to_response(conv)


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    checkpointer=Depends(get_checkpointer),
    user: UserContext = Depends(get_current_user),
):
    """删除对话 + 清理 checkpoint"""
    deleted = await ConversationRepo.delete_by_id(db, conversation_id, user.user_id)
    if not deleted:
        return JSONResponse(status_code=404, content=make_conversation_error(ConversationErrorCode.NOT_FOUND))

    await db.commit()

    # 清理 checkpoint（失败不阻断）
    try:
        if hasattr(checkpointer, "adelete_thread"):
            await checkpointer.adelete_thread(conversation_id)
    except Exception as e:
        logger.warning(f"[conversation] checkpoint cleanup failed for {conversation_id}: {e}")

    return Response(status_code=204)
