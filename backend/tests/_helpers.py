"""共享测试辅助函数

由 conftest.py 和各测试文件共同引用。
"""

from __future__ import annotations

import json
import tempfile
import os
from unittest.mock import AsyncMock, MagicMock

from jose import jwt

from app.domain.models import SourceReference
from app.evaluation.eval_types import EvalItem, EvalSource, RetrievalTruth
from app.middleware.auth import ALGORITHM

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

TEST_SECRET = "test-jwt-secret-key"


# ---------------------------------------------------------------------------
# 认证
# ---------------------------------------------------------------------------

def make_auth_headers(token: str | None = None) -> dict:
    """构造 Bearer token 认证头"""
    if token is None:
        token = jwt.encode(
            {"sub": "user-123", "client_id": "testuser", "exp": 9999999999, "type": "access"},
            TEST_SECRET,
            algorithm=ALGORITHM,
        )
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Mock 构造
# ---------------------------------------------------------------------------

def make_mock_chat_service(chunks=None, degraded=False, degradation_reason=None):
    """构造 mock ChatService，retrieve 返回指定 chunks"""
    svc = MagicMock()
    result_chunks = chunks or []
    result = MagicMock()
    result.chunks = result_chunks
    result.degraded = degraded
    result.degradation_reason = degradation_reason
    svc.retrieve.return_value = result
    return svc


def make_mock_generator(tokens=None, title=None):
    """构造 mock LLMGenerator"""
    from langchain_core.messages import AIMessage
    gen = MagicMock()

    gen.generate_title = AsyncMock(return_value=title)

    mock_chat_model = MagicMock()
    mock_chat_model.ainvoke = AsyncMock(return_value=AIMessage(content="mock answer"))
    gen.get_chat_model.return_value = mock_chat_model
    return gen


# ---------------------------------------------------------------------------
# SSE 解析
# ---------------------------------------------------------------------------

def parse_sse_frames(text: str) -> list[dict]:
    """解析 SSE 文本为 [{type, data}] 列表"""
    frames = []
    for part in text.split("\n\n"):
        part = part.strip()
        if not part:
            continue
        event_type = ""
        data_str = ""
        for line in part.split("\n"):
            if line.startswith("event: "):
                event_type = line[7:]
            elif line.startswith("data: "):
                data_str = line[6:]
        if event_type:
            data = json.loads(data_str) if data_str != "null" else None
            frames.append({"type": event_type, "data": data})
    return frames


# ---------------------------------------------------------------------------
# Settings / SourceRef / EvalItem 工厂
# ---------------------------------------------------------------------------

def make_settings(**overrides):
    """构造 mock Settings 对象"""
    defaults = dict(
        retrieval_top_k=20,
        similarity_threshold=0.70,
        bm25_enabled=True,
        rrf_k=60,
        rerank_top_n=3,
        chat_max_context_tokens=3000,
    )
    defaults.update(overrides)
    return MagicMock(**defaults)


def make_source_ref(
    chunk_id: str = "ref_1",
    book: str = "必修第一册",
    section: str = "1.1 集合",
    page_start: int = 1,
    page_end: int = 2,
) -> SourceReference:
    """构造 SourceReference"""
    return SourceReference(
        chunk_id=chunk_id,
        book=book,
        section=section,
        page_start=page_start,
        page_end=page_end,
    )


def make_eval_item(
    item_id: str = "q001",
    question: str = "测试问题",
    mode: str = "ANY",
    sources: list[dict] | None = None,
    key_facts: list[str] | None = None,
    suite: str = "regression",
    section_id: str | None = None,
) -> EvalItem:
    """构造 EvalItem（完整签名，兼容 test_eval_runner 和 test_eval_runner_extended）"""
    if sources is None:
        sources = [{"book": "必修第一册", "page_start": 1, "page_end": 10}]

    eval_sources = [EvalSource(**s) for s in sources]
    if section_id and len(eval_sources) == 1:
        eval_sources[0].section_id = section_id
    truth = RetrievalTruth(mode=mode, sources=eval_sources)
    return EvalItem(
        id=item_id,
        question=question,
        retrieval_truth=truth,
        key_facts=key_facts or [],
        suite=suite,
    )
