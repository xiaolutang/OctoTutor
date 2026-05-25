"""R009-BF001: Conversation model 字段定义 & 默认值单元测试

不需要真实 DB 连接，纯同步测试 SQLAlchemy model 的字段元数据和默认值。
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped

from app.domain.models import Base, Conversation


# ---------------------------------------------------------------------------
# 1. Model 可实例化
# ---------------------------------------------------------------------------


class TestConversationInstantiation:
    """Conversation model 可实例化并设置字段值"""

    def test_create_with_required_fields(self):
        conv = Conversation(id="abc-123", user_id="user-1")
        assert conv.id == "abc-123"
        assert conv.user_id == "user-1"

    def test_create_with_all_fields(self):
        now = datetime.now(timezone.utc)
        conv = Conversation(
            id="conv-001",
            user_id="user-42",
            title="数学辅导",
            pinned=True,
            pinned_at=now,
            message_count=5,
            created_at=now,
            updated_at=now,
        )
        assert conv.id == "conv-001"
        assert conv.user_id == "user-42"
        assert conv.title == "数学辅导"
        assert conv.pinned is True
        assert conv.pinned_at == now
        assert conv.message_count == 5

    def test_create_with_keyword_defaults(self):
        """传显式默认值时正确赋值

        注意：SQLAlchemy 的 mapped_column(default=...) 是 server-side default，
        在 Python 实例化时不会自动填充。需要在构造时显式传入。
        """
        conv = Conversation(
            id="x", user_id="u", title="新对话", pinned=False, message_count=0
        )
        assert conv.title == "新对话"
        assert conv.pinned is False
        assert conv.message_count == 0


# ---------------------------------------------------------------------------
# 2. 字段默认值正确
# ---------------------------------------------------------------------------


class TestConversationDefaults:
    """字段 server-side default (SQLAlchemy column default) 验证"""

    def test_id_column_type_is_varchar_36(self):
        """id 列类型为 VARCHAR(36)"""
        col = Conversation.__table__.c.id
        assert isinstance(col.type, String)
        assert col.type.length == 36

    def test_title_default_value(self):
        """title 列 default 为 '新对话'"""
        col = Conversation.__table__.c.title
        assert col.default is not None
        assert col.default.arg == "新对话"

    def test_pinned_default_false(self):
        """pinned 列 default 为 False"""
        col = Conversation.__table__.c.pinned
        assert col.default is not None
        assert col.default.arg is False

    def test_message_count_default_zero(self):
        """message_count 列 default 为 0"""
        col = Conversation.__table__.c.message_count
        assert col.default is not None
        assert col.default.arg == 0

    def test_pinned_at_nullable(self):
        """pinned_at 可为 None"""
        col = Conversation.__table__.c.pinned_at
        assert col.nullable is True

    def test_created_at_has_default(self):
        """created_at 列有 default callable"""
        col = Conversation.__table__.c.created_at
        assert col.default is not None
        assert callable(col.default.arg)

    def test_updated_at_has_default_and_onupdate(self):
        """updated_at 列有 default 和 onupdate callable"""
        col = Conversation.__table__.c.updated_at
        assert col.default is not None
        assert callable(col.default.arg)
        assert col.onupdate is not None
        assert callable(col.onupdate.arg)


# ---------------------------------------------------------------------------
# 3. Base metadata 包含 conversations 表
# ---------------------------------------------------------------------------


class TestBaseMetadata:
    """验证 Base.metadata 中注册了 conversations 表"""

    def test_conversations_table_registered(self):
        table_names = Base.metadata.tables.keys()
        assert "conversations" in table_names

    def test_conversations_table_has_expected_columns(self):
        expected = {
            "id",
            "user_id",
            "title",
            "pinned",
            "pinned_at",
            "message_count",
            "created_at",
            "updated_at",
        }
        actual = set(Conversation.__table__.c.keys())
        assert actual == expected

    def test_id_is_primary_key(self):
        col = Conversation.__table__.c.id
        assert col.primary_key is True

    def test_user_id_not_nullable(self):
        col = Conversation.__table__.c.user_id
        assert col.nullable is False
