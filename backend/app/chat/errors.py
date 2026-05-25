"""对话模块错误码体系

MMPPN 五位数字编码：MM=模块, PP=阶段, N=序号
示例：02205 = 对话模块(02) + 生成阶段(2) + 第05号错误(LLM限流)
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ChatErrorCode(Enum):
    """对话模块错误码 — MMPPN 编码，字符串值避免前导零问题"""
    EMBEDDING_FAILED = "02102"
    VECTOR_STORE_ERROR = "02103"
    LLM_CONNECT_FAILED = "02201"
    LLM_STREAM_ERROR = "02202"
    LLM_EMPTY_RESPONSE = "02203"
    LLM_TIMEOUT = "02204"
    LLM_RATE_LIMITED = "02205"
    INTERNAL_ERROR = "02901"


@dataclass(frozen=True)
class ErrorDef:
    """错误定义"""
    code: str
    message: str
    action: str  # "retry" | "edit" | "wait"


ERROR_REGISTRY: dict[ChatErrorCode, ErrorDef] = {
    ChatErrorCode.EMBEDDING_FAILED: ErrorDef("02102", "检索服务异常，请重试", "retry"),
    ChatErrorCode.VECTOR_STORE_ERROR: ErrorDef("02103", "检索服务异常，请重试", "retry"),
    ChatErrorCode.LLM_CONNECT_FAILED: ErrorDef("02201", "AI 服务连接失败，请重试", "retry"),
    ChatErrorCode.LLM_STREAM_ERROR: ErrorDef("02202", "生成中断，已保留部分内容", "retry"),
    ChatErrorCode.LLM_EMPTY_RESPONSE: ErrorDef("02203", "AI 未能生成回答，请重试", "retry"),
    ChatErrorCode.LLM_TIMEOUT: ErrorDef("02204", "AI 响应超时，请重试", "retry"),
    ChatErrorCode.LLM_RATE_LIMITED: ErrorDef("02205", "请求太频繁，请稍后再试", "wait"),
    ChatErrorCode.INTERNAL_ERROR: ErrorDef("02901", "服务异常，请重试", "retry"),
}


def make_error(code: ChatErrorCode) -> dict:
    """根据 ChatErrorCode 枚举值生成错误字典"""
    defn = ERROR_REGISTRY[code]
    return {"code": defn.code, "message": defn.message, "action": defn.action}


# ---------------------------------------------------------------------------
# 对话管理模块错误码 (03xxx) — R009
# ---------------------------------------------------------------------------

class ConversationErrorCode(Enum):
    """对话管理模块错误码"""
    NOT_FOUND = "03901"        # 对话不存在
    PIN_LIMIT = "03902"        # 置顶超限
    TITLE_INVALID = "03903"    # 标题校验失败
    CREATE_FAILED = "03904"    # 对话创建失败


CONVERSATION_ERROR_REGISTRY: dict[ConversationErrorCode, ErrorDef] = {
    ConversationErrorCode.NOT_FOUND: ErrorDef("03901", "对话不存在", "refresh"),
    ConversationErrorCode.PIN_LIMIT: ErrorDef("03902", "最多置顶 5 条对话", "unpin_first"),
    ConversationErrorCode.TITLE_INVALID: ErrorDef("03903", "标题不能为空且不超过200字", "retry"),
    ConversationErrorCode.CREATE_FAILED: ErrorDef("03904", "对话创建失败", "retry"),
}


def make_conversation_error(code: ConversationErrorCode) -> dict:
    """根据 ConversationErrorCode 枚举值生成错误字典"""
    defn = CONVERSATION_ERROR_REGISTRY[code]
    return {"code": defn.code, "message": defn.message, "action": defn.action}
