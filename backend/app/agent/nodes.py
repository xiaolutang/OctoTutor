"""Agent 节点函数 -- classify / refuse"""

from langchain_core.messages import AIMessage

from app.domain.classifier import classify_question


# ---------------------------------------------------------------------------
# classify 节点
# ---------------------------------------------------------------------------

async def classify_node(state: dict) -> dict:
    question = state.get("question", "")
    intent = classify_question(question)
    return {"intent": intent}


# ---------------------------------------------------------------------------
# refuse 节点 — 非课程问题返回静态拒绝消息（不调 LLM）
# ---------------------------------------------------------------------------

_REFUSE_MESSAGE = "我是课程学习助手，专注于帮你理解教材内容。如果你有课程相关的问题，随时问我！"


def refuse_node(state: dict) -> dict:
    """非课程问题返回静态拒绝消息"""
    return {"messages": [AIMessage(content=_REFUSE_MESSAGE)]}
