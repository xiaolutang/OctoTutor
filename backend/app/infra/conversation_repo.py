"""Conversation CRUD 数据访问层

纯数据访问，不包含业务逻辑（校验、错误码等在 router 层处理）。
"""

from __future__ import annotations

import base64
from datetime import datetime, timezone

from sqlalchemy import select, func, delete as sa_delete, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import Conversation


class ConversationRepo:

    @staticmethod
    async def create(session: AsyncSession, conversation: Conversation) -> Conversation:
        """插入一条 conversation 记录"""
        session.add(conversation)
        await session.flush()
        return conversation

    @staticmethod
    async def get_by_id(session: AsyncSession, conv_id: str, user_id: str) -> Conversation | None:
        """根据 id + user_id 查询"""
        result = await session.execute(
            select(Conversation).where(
                Conversation.id == conv_id,
                Conversation.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_by_user(
        session: AsyncSession,
        user_id: str,
        cursor: str | None = None,
        limit: int = 20,
    ) -> tuple[list[Conversation], bool]:
        """游标分页查询

        策略：置顶对话最多 5 条，首页一次返回全部；游标分页只用于普通对话。
        返回 (items, has_more)，多查 1 条判断 has_more。

        游标格式：base64('{updated_at_iso}|{conversation_id}')
        """
        if cursor is None:
            # 首页：查全部置顶 + 前 (limit+1) 条普通对话
            pinned_result = await session.execute(
                select(Conversation)
                .where(Conversation.user_id == user_id, Conversation.pinned == True)
                .order_by(Conversation.pinned_at.desc())
            )
            pinned_items = list(pinned_result.scalars().all())

            normal_limit = max(limit + 1 - len(pinned_items), 1)
            normal_result = await session.execute(
                select(Conversation)
                .where(Conversation.user_id == user_id, Conversation.pinned == False)
                .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
                .limit(normal_limit)
            )
            normal_items = list(normal_result.scalars().all())

            has_more = len(pinned_items) + len(normal_items) > limit
            if has_more:
                normal_items = normal_items[:limit - len(pinned_items)]

            return pinned_items + normal_items, has_more
        else:
            # 翻页：解 cursor，查普通对话
            decoded = base64.b64decode(cursor).decode()
            cursor_time_str, cursor_id = decoded.rsplit("|", 1)
            cursor_time = datetime.fromisoformat(cursor_time_str)

            result = await session.execute(
                select(Conversation)
                .where(
                    Conversation.user_id == user_id,
                    Conversation.pinned == False,
                    (Conversation.updated_at < cursor_time)
                    | ((Conversation.updated_at == cursor_time) & (Conversation.id < cursor_id)),
                )
                .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
                .limit(limit + 1)
            )
            items = list(result.scalars().all())
            has_more = len(items) > limit
            if has_more:
                items = items[:limit]

            return items, has_more

    @staticmethod
    async def update(session: AsyncSession, conv_id: str, user_id: str, **fields) -> Conversation | None:
        """更新指定字段（title/pinned/pinned_at 等）"""
        result = await session.execute(
            sa_update(Conversation)
            .where(Conversation.id == conv_id, Conversation.user_id == user_id)
            .values(**fields)
            .returning(Conversation)
        )
        row = result.scalar_one_or_none()
        return row

    @staticmethod
    async def delete_by_id(session: AsyncSession, conv_id: str, user_id: str) -> bool:
        """删除指定记录，返回是否实际删除"""
        result = await session.execute(
            sa_delete(Conversation).where(
                Conversation.id == conv_id,
                Conversation.user_id == user_id,
            )
        )
        return result.rowcount > 0

    @staticmethod
    async def count_pinned(session: AsyncSession, user_id: str) -> int:
        """返回用户当前置顶数"""
        result = await session.execute(
            select(func.count()).select_from(Conversation).where(
                Conversation.user_id == user_id,
                Conversation.pinned == True,
            )
        )
        return result.scalar() or 0

    @staticmethod
    async def update_message_stats(session: AsyncSession, conv_id: str, message_count_delta: int = 2) -> None:
        """更新 updated_at 和 message_count"""
        await session.execute(
            sa_update(Conversation)
            .where(Conversation.id == conv_id)
            .values(
                updated_at=datetime.now(timezone.utc),
                message_count=Conversation.message_count + message_count_delta,
            )
        )
