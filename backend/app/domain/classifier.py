"""问题意图分类 — 判断用户输入是否需要检索教材

分类结果：
- "textbook":  需要检索教材后生成回答（数学问题、具体知识点提问）
- "unrelated": 直接走 LLM 生成，不检索（闲聊、问候、太短、非数学）

分类依据（按优先级）：
1. 长度过短（<=3 字）→ unrelated
2. 常见问候/闲聊模式 → unrelated
2b. 社交噪音（去问候后残余为空）→ unrelated
3. 包含数学符号/公式标记 → textbook
4. 包含数学关键词 → textbook
5. 默认 → unrelated（宁可拒答，不误答）
"""

from __future__ import annotations

import re

# 常见问候/闲聊模式（全匹配）
_GREETING_PATTERNS: set[str] = {
    "你好", "您好", "嗨", "hi", "hello", "hey",
    "谢谢", "感谢", "thanks", "ok", "好的", "嗯", "哦",
    "再见", "拜拜", "bye",
    "你是谁", "你叫什么", "介绍一下你自己",
    "哈哈", "呵呵", "嘿嘿", "嘻嘻",   # 社交笑声
    "嗯嗯", "哦哦",                    # 重复语气词
}

# 数学关键词（出现任意一个即判定为需要检索）
_MATH_KEYWORDS: set[str] = {
    "函数", "方程", "不等式", "数列", "集合", "概率", "统计",
    "三角", "向量", "导数", "积分", "极限", "矩阵",
    "直线", "圆", "椭圆", "双曲线", "抛物线", "圆锥",
    "求", "计算", "证明", "解", "化简", "推导",
    "最大值", "最小值", "极值", "单调", "奇偶",
    "排列", "组合", "二项式", "分布",
    "平面", "空间", "坐标", "角度", "距离",
    "公式", "定理", "性质", "定义",
    "题",   # "这道题"、"做几道题"、"题目"
    "算",   # "帮我算一下"、"怎么算"、"算出"
}

# 数学符号正则：$...$, 数字+运算符, 希腊字母, 上下标
_MATH_SYMBOL_RE = re.compile(
    r"\$.*?\$"       # LaTeX inline math
    r"|[\d]+\s*[+\-*/=^]"  # 数字 + 运算符
    r"|α|β|γ|δ|θ|φ|ω|π|∑|∏|∫|√|±|≈|≠|≤|≥|∈|∩|∪|⊥|∠"
)


def classify_question(question: str) -> str:
    """判断用户问题是否需要检索教材

    Args:
        question: 用户输入的问题文本（已去首尾空格）

    Returns:
        "textbook"  — 需要检索教材
        "unrelated" — 直接走 LLM，不检索
    """
    text = question.strip()
    if not text:
        return "unrelated"

    # 1. 长度过短
    if len(text) <= 3:
        return "unrelated"

    # 2. 常见问候/闲聊（精确匹配）
    normalized = text.lower().rstrip("。！？!?. ")
    if normalized in _GREETING_PATTERNS:
        return "unrelated"

    # 2b. 社交噪音检测（去问候后残余为空 → 纯噪音）
    cleaned = normalized
    for g in _GREETING_PATTERNS:
        cleaned = cleaned.replace(g, "")
    cleaned = cleaned.strip("。！？!?. ")
    if not cleaned:
        return "unrelated"

    # 3. 数学符号
    if _MATH_SYMBOL_RE.search(text):
        return "textbook"

    # 4. 数学关键词
    if any(kw in text for kw in _MATH_KEYWORDS):
        return "textbook"

    # 5. 默认 unrelated（宁可拒答，不误答）
    return "unrelated"
