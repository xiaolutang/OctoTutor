"""Agent 节点函数 -- classify / retrieve / respond / refuse"""

from langchain_core.messages import AIMessage

from app.agent.prompts import TEACHING_SYSTEM_PROMPT
from app.chat.question_classifier import classify_question


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


# ---------------------------------------------------------------------------
# retrieve 节点 — 复用 ChatService._retrieve 的检索管线
# 实际调用在 graph.py create_graph 中通过闭包绑定
# ---------------------------------------------------------------------------

async def retrieve_node(state: dict) -> dict:
    """复用 ChatService._retrieve 的检索管线 — 通过闭包注入"""
    return {}


# ---------------------------------------------------------------------------
# respond 节点 — 教学策略 prompt + LLM 流式生成
# 实际 LLM 调用在 graph.py create_graph 中通过闭包注入
# ---------------------------------------------------------------------------

async def respond_node(state: dict) -> dict:
    """教学策略 prompt + LLM 流式生成 — 通过闭包注入"""
    return {}
