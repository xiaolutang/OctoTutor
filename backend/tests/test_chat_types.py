"""BF001 测试：SSE 事件模型 + 错误码体系 + RetrieveResult"""
import pytest

from app.chat.errors import ChatErrorCode, ErrorDef, ERROR_REGISTRY, make_error
from app.chat.schemas import StreamEvent, StatusPayload
from app.chat.service import RetrieveResult


# ── ChatErrorCode 枚举 ──────────────────────────────────────────

class TestChatErrorCode:
    """枚举值验证"""

    EXPECTED_CODES = {
        "EMBEDDING_FAILED": "02102",
        "VECTOR_STORE_ERROR": "02103",
        "LLM_CONNECT_FAILED": "02201",
        "LLM_STREAM_ERROR": "02202",
        "LLM_EMPTY_RESPONSE": "02203",
        "LLM_TIMEOUT": "02204",
        "LLM_RATE_LIMITED": "02205",
        "INTERNAL_ERROR": "02901",
    }

    def test_enum_count(self):
        assert len(ChatErrorCode) == 8

    def test_all_values_are_strings(self):
        for member in ChatErrorCode:
            assert isinstance(member.value, str), f"{member.name} value is not str"

    def test_expected_values(self):
        for name, value in self.EXPECTED_CODES.items():
            assert ChatErrorCode[name].value == value


# ── ERROR_REGISTRY 完整性 ────────────────────────────────────────

class TestErrorRegistry:
    def test_registry_covers_all_enum_members(self):
        for member in ChatErrorCode:
            assert member in ERROR_REGISTRY, f"{member.name} not in ERROR_REGISTRY"

    def test_registry_entries_are_error_def(self):
        for key, defn in ERROR_REGISTRY.items():
            assert isinstance(defn, ErrorDef)
            assert isinstance(defn.code, str)
            assert isinstance(defn.message, str)
            assert defn.action in ("retry", "edit", "wait")


# ── make_error() ────────────────────────────────────────────────

class TestMakeError:
    def test_returns_dict_with_required_keys(self):
        result = make_error(ChatErrorCode.EMBEDDING_FAILED)
        assert isinstance(result, dict)
        assert set(result.keys()) == {"code", "message", "action"}

    def test_embedding_failed_values(self):
        result = make_error(ChatErrorCode.EMBEDDING_FAILED)
        assert result == {"code": "02102", "message": "检索服务异常，请重试", "action": "retry"}

    def test_rate_limited_action_is_wait(self):
        result = make_error(ChatErrorCode.LLM_RATE_LIMITED)
        assert result["action"] == "wait"

    def test_all_codes_produce_valid_error(self):
        for member in ChatErrorCode:
            result = make_error(member)
            assert result["code"] == member.value
            assert len(result["message"]) > 0
            assert result["action"] in ("retry", "edit", "wait")


# ── RetrieveResult ──────────────────────────────────────────────

class TestRetrieveResult:
    def test_defaults(self):
        r = RetrieveResult(chunks=[])
        assert r.degraded is False
        assert r.degradation_reason is None

    def test_with_values(self):
        r = RetrieveResult(chunks=[], degraded=True, degradation_reason="rerank_failed")
        assert r.degraded is True
        assert r.degradation_reason == "rerank_failed"


# ── StreamEvent ─────────────────────────────────────────────────

class TestStreamEvent:
    @pytest.mark.parametrize("event_type", ["status", "sources", "token", "done", "error"])
    def test_valid_types(self, event_type):
        e = StreamEvent(type=event_type, data="test")
        assert e.type == event_type

    def test_data_can_be_any(self):
        e = StreamEvent(type="token", data={"key": "val"})
        assert e.data == {"key": "val"}


# ── StatusPayload ───────────────────────────────────────────────

class TestStatusPayload:
    @pytest.mark.parametrize("stage", ["retrieving", "generating"])
    def test_valid_stages(self, stage):
        p = StatusPayload(stage=stage, message="loading")
        assert p.stage == stage
        assert p.message == "loading"
