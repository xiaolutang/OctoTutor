from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.domain.models import SourceReference


class ImageRef(BaseModel):
    """图片引用"""
    url: str
    image_id: str


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000, description="学生问题")
    top_k: int = Field(default=10, ge=3, le=20, description="检索数量")
    conversation_id: str | None = Field(default=None, description="对话 ID，为空时自动创建")
    images: list[ImageRef] = Field(default_factory=list, max_length=3, description="图片引用列表")

    @field_validator("question")
    @classmethod
    def validate_question(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("问题不能为纯空格")
        return v.strip()


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceReference]
    context_used: int
    degraded: bool = False
    degradation_reason: str | None = None


@dataclass
class StreamEvent:
    """SSE 结构化事件"""
    type: Literal["status", "sources", "token", "thinking", "done", "title", "error"]
    data: Any


@dataclass
class StatusPayload:
    """status 事件数据"""
    stage: Literal["recognizing", "retrieving", "generating"]
    message: str


@dataclass
class ThinkingPayload:
    """thinking 事件数据 — 思考步骤"""
    text: str
    index: int = 0


class ApiMessage(BaseModel):
    """对话消息 — GET /api/conversations/current 响应中的消息格式"""
    id: str
    role: str
    content: str | list[dict]
    status: str = "completed"
    sources: list[SourceReference] = Field(default_factory=list)
    thinking_steps: list[ThinkingPayload] = Field(default_factory=list)
    images: list[ImageRef] = Field(default_factory=list)
    created_at: str = ""


# ---------------------------------------------------------------------------
# Conversation 对话管理 Schema (R009)
# ---------------------------------------------------------------------------

class ConversationItemResponse(BaseModel):
    """对话列表项"""
    id: str
    title: str
    pinned: bool
    pinned_at: datetime | None = None
    message_count: int
    created_at: datetime
    updated_at: datetime


class ConversationListResponse(BaseModel):
    """对话列表响应"""
    items: list[ConversationItemResponse]
    cursor: str | None = None
    has_more: bool = False


class ConversationUpdateRequest(BaseModel):
    """对话更新请求"""
    title: str | None = None
    pinned: bool | None = None


class StopRequest(BaseModel):
    """停止对话请求 — POST /api/chat/stop"""
    conversation_id: str
