class TokenBudget:
    CONTEXT_WINDOW = 200_000       # LLM context window 上限
    SUMMARIZE_THRESHOLD = 0.65     # 65% 时触发摘要（130K）
    RESERVED_FOR_RAG = 8_000       # 预留给 RAG context + system prompt
    RESERVED_FOR_OUTPUT = 4_000    # 预留给 LLM 输出
    RECENT_MESSAGES_KEEP = 10      # 摘要时保留最近 10 条消息（5 轮）


def estimate_tokens(text: str) -> int:
    """保守估算文本 token 数（中文 1 字 ≈ 1.5 token）"""
    return int(len(text) * 1.5)
