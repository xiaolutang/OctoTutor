from pydantic import BaseModel, Field, field_validator

from app.domain.models import SourceReference


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000, description="学生问题")
    top_k: int = Field(default=10, ge=3, le=20, description="检索数量")

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
