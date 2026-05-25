"""R009-BF004: Conversation Schema + 错误码 单元测试

覆盖场景:
- ConversationListResponse 空列表序列化
- ConversationUpdateRequest 仅 title，验证 pinned 默认 None
- ConversationErrorCode 03901-03904 存在
- ConversationItemResponse 全字段序列化
- make_conversation_error 生成正确错误字典
"""

from datetime import datetime, timezone

import pytest

from app.chat.errors import (
    CONVERSATION_ERROR_REGISTRY,
    ConversationErrorCode,
    ErrorDef,
    make_conversation_error,
)
from app.chat.schemas import (
    ConversationItemResponse,
    ConversationListResponse,
    ConversationUpdateRequest,
)


# ---------------------------------------------------------------------------
# ConversationListResponse — 空列表
# ---------------------------------------------------------------------------


class TestConversationListResponse:
    """对话列表响应 schema 测试"""

    def test_empty_items(self):
        """空 items 列表序列化"""
        resp = ConversationListResponse(items=[])
        data = resp.model_dump()
        assert data["items"] == []
        assert data["cursor"] is None
        assert data["has_more"] is False

    def test_empty_items_json_roundtrip(self):
        """空列表 JSON 序列化/反序列化 roundtrip"""
        resp = ConversationListResponse(items=[])
        json_str = resp.model_dump_json()
        restored = ConversationListResponse.model_validate_json(json_str)
        assert restored.items == []
        assert restored.cursor is None
        assert restored.has_more is False

    def test_with_cursor_and_has_more(self):
        """带 cursor 和 has_more 的响应"""
        resp = ConversationListResponse(items=[], cursor="abc123", has_more=True)
        data = resp.model_dump()
        assert data["cursor"] == "abc123"
        assert data["has_more"] is True


# ---------------------------------------------------------------------------
# ConversationItemResponse — 全字段序列化
# ---------------------------------------------------------------------------


class TestConversationItemResponse:
    """对话列表项 schema 测试"""

    def test_full_serialization(self):
        """所有字段正确序列化"""
        now = datetime(2026, 5, 25, 12, 0, 0, tzinfo=timezone.utc)
        pinned_time = datetime(2026, 5, 20, 8, 30, 0, tzinfo=timezone.utc)

        item = ConversationItemResponse(
            id="conv-001",
            title="测试对话",
            pinned=True,
            pinned_at=pinned_time,
            message_count=5,
            created_at=now,
            updated_at=now,
        )
        data = item.model_dump()

        assert data["id"] == "conv-001"
        assert data["title"] == "测试对话"
        assert data["pinned"] is True
        assert data["pinned_at"] == pinned_time
        assert data["message_count"] == 5
        assert data["created_at"] == now
        assert data["updated_at"] == now

    def test_pinned_at_none(self):
        """pinned_at 为 None 时正确序列化"""
        now = datetime(2026, 5, 25, tzinfo=timezone.utc)
        item = ConversationItemResponse(
            id="conv-002",
            title="未置顶对话",
            pinned=False,
            pinned_at=None,
            message_count=0,
            created_at=now,
            updated_at=now,
        )
        data = item.model_dump()
        assert data["pinned"] is False
        assert data["pinned_at"] is None

    def test_json_roundtrip(self):
        """JSON 序列化 roundtrip"""
        now = datetime(2026, 5, 25, 12, 0, 0, tzinfo=timezone.utc)
        item = ConversationItemResponse(
            id="conv-003",
            title="Roundtrip",
            pinned=False,
            message_count=3,
            created_at=now,
            updated_at=now,
        )
        json_str = item.model_dump_json()
        restored = ConversationItemResponse.model_validate_json(json_str)
        assert restored.id == "conv-003"
        assert restored.title == "Roundtrip"
        assert restored.message_count == 3


# ---------------------------------------------------------------------------
# ConversationUpdateRequest — 仅 title
# ---------------------------------------------------------------------------


class TestConversationUpdateRequest:
    """对话更新请求 schema 测试"""

    def test_title_only_pinned_defaults_none(self):
        """仅设置 title，pinned 默认为 None"""
        req = ConversationUpdateRequest(title="新标题")
        assert req.title == "新标题"
        assert req.pinned is None

    def test_pinned_only_title_defaults_none(self):
        """仅设置 pinned，title 默认为 None"""
        req = ConversationUpdateRequest(pinned=True)
        assert req.title is None
        assert req.pinned is True

    def test_both_fields(self):
        """同时设置 title 和 pinned"""
        req = ConversationUpdateRequest(title="新标题", pinned=False)
        assert req.title == "新标题"
        assert req.pinned is False

    def test_empty_construction(self):
        """无参数构造，两个字段均为 None"""
        req = ConversationUpdateRequest()
        assert req.title is None
        assert req.pinned is None

    def test_title_only_json_roundtrip(self):
        """仅 title 的 JSON roundtrip"""
        req = ConversationUpdateRequest(title="JSON标题")
        json_str = req.model_dump_json()
        restored = ConversationUpdateRequest.model_validate_json(json_str)
        assert restored.title == "JSON标题"
        assert restored.pinned is None


# ---------------------------------------------------------------------------
# ConversationErrorCode — 03901-03904 存在性
# ---------------------------------------------------------------------------


class TestConversationErrorCode:
    """对话管理错误码枚举测试"""

    EXPECTED_CODES = {
        "NOT_FOUND": "03901",
        "PIN_LIMIT": "03902",
        "TITLE_INVALID": "03903",
        "CREATE_FAILED": "03904",
    }

    def test_all_error_codes_exist(self):
        """03901-03904 四个错误码均存在"""
        for name, code_value in self.EXPECTED_CODES.items():
            assert hasattr(ConversationErrorCode, name), (
                f"ConversationErrorCode 缺少 {name}"
            )
            assert ConversationErrorCode[name].value == code_value, (
                f"{name} 的值应为 {code_value}"
            )

    def test_exactly_four_codes(self):
        """枚举恰好包含四个值"""
        members = list(ConversationErrorCode)
        assert len(members) == 4

    def test_registry_covers_all_codes(self):
        """CONVERSATION_ERROR_REGISTRY 覆盖所有枚举值"""
        for code in ConversationErrorCode:
            assert code in CONVERSATION_ERROR_REGISTRY, (
                f"CONVERSATION_ERROR_REGISTRY 缺少 {code.name}"
            )

    def test_registry_error_def_fields(self):
        """注册表中的 ErrorDef 字段完整且 code 值一致"""
        for code in ConversationErrorCode:
            defn = CONVERSATION_ERROR_REGISTRY[code]
            assert isinstance(defn, ErrorDef)
            assert defn.code == code.value, (
                f"{code.name} 注册表 code 不匹配: {defn.code} != {code.value}"
            )
            assert defn.message, f"{code.name} 缺少 message"
            assert defn.action in ("retry", "refresh", "unpin_first", "wait"), (
                f"{code.name} 未知 action: {defn.action}"
            )


# ---------------------------------------------------------------------------
# make_conversation_error — 错误字典生成
# ---------------------------------------------------------------------------


class TestMakeConversationError:
    """make_conversation_error 函数测试"""

    def test_returns_expected_structure(self):
        """返回包含 code/message/action 的字典"""
        for code in ConversationErrorCode:
            result = make_conversation_error(code)
            assert isinstance(result, dict)
            assert set(result.keys()) == {"code", "message", "action"}
            assert result["code"] == code.value

    def test_not_found_error(self):
        """NOT_FOUND 错误具体内容"""
        result = make_conversation_error(ConversationErrorCode.NOT_FOUND)
        assert result["code"] == "03901"
        assert result["message"] == "对话不存在"
        assert result["action"] == "refresh"

    def test_pin_limit_error(self):
        """PIN_LIMIT 错误具体内容"""
        result = make_conversation_error(ConversationErrorCode.PIN_LIMIT)
        assert result["code"] == "03902"
        assert "置顶" in result["message"]

    def test_title_invalid_error(self):
        """TITLE_INVALID 错误具体内容"""
        result = make_conversation_error(ConversationErrorCode.TITLE_INVALID)
        assert result["code"] == "03903"
        assert "标题" in result["message"]

    def test_create_failed_error(self):
        """CREATE_FAILED 错误具体内容"""
        result = make_conversation_error(ConversationErrorCode.CREATE_FAILED)
        assert result["code"] == "03904"
        assert "创建" in result["message"]
