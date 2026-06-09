"""R010 Summary Fidelity 专项测试

构建超长对话触发 summarize 节点，然后用 LLM Judge 评估摘要保真度。

使用方式（在 Docker 容器内运行）：
    docker exec octotutor-backend python3 -m eval.test_summary_fidelity
"""

from __future__ import annotations

import asyncio
import json
import sys
import time

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver


# 每轮发送的题目 — 选择能触发长回答的数学问题
TURNS = [
    "请用至少800字详细解释函数的概念，包括定义域、值域、对应法则、表示方法，每种都举例说明",
    "接着上面，用至少800字详细讲解函数的单调性和奇偶性，每种性质各举三个不同的函数例子",
    "用至少800字详细讲解指数函数的定义、图像特征（单调性、过定点）、性质，并举两个实际应用例子",
    "用至少800字详细讲解对数函数的定义、与指数函数的关系、运算法则（含推导），举三个例子",
    "用至少800字详细讲解三角函数的定义（正弦、余弦、正切），从单位圆出发推导定义",
    "用至少800字详细讲解三角函数的图像（y=sinx, y=cosx, y=tanx）、周期性、最大值最小值、变换",
    "用至少800字详细讲解向量的概念、表示方法、加法、减法、数乘运算及其几何意义",
    "用至少800字详细讲解向量的数量积（内积）定义、性质、坐标运算、几何意义，举三个例子",
    "用至少800字详细讲解等差数列的定义、通项公式推导、前n项和公式推导，举两个应用题",
    "用至少800字详细讲解等比数列的定义、通项公式推导、前n项和公式推导，举两个应用题",
    "用至少800字详细讲解概率的基本概念、古典概型的定义和计算方法，举三个例子",
    "用至少800字详细讲解条件概率的定义、乘法公式、全概率公式和贝叶斯公式，各举一例",
    "用至少800字详细讲解二次函数的三种形式、顶点坐标、对称轴、最值问题和图像变换",
    "用至少800字详细讲解幂函数的定义、五种常见幂函数的图像特征和性质比较",
    "用至少800字详细讲解圆的标准方程和一般方程推导，以及点与圆、直线与圆的位置关系判定",
    "用至少800字详细讲解椭圆的定义（两个焦点）、标准方程推导、离心率、焦点和准线",
    "用至少800字详细讲解双曲线的定义、标准方程推导、渐近线方程、离心率和光学性质",
    "用至少800字详细讲解抛物线的定义、四种标准方程、焦点和准线、光学应用",
    "用至少800字详细讲解空间几何体的三视图（正视图、侧视图、俯视图）和直观图画法",
    "用至少800字详细讲解空间中线面平行和线面垂直的判定定理和性质定理",
    "用至少800字详细讲解空间向量的坐标运算、法向量求法、空间距离和夹角计算",
    "用至少800字详细讲解导数的概念（极限定义）、几何意义（切线斜率）、基本求导公式表",
    "用至少800字详细讲解导数的应用：函数单调性判断、极值求法、最值问题，各举两例",
    "用至少800字详细讲解定积分的概念（分割、近似、取极限）、性质和微积分基本定理",
    "用至少800字详细讲解复数的概念（虚数单位）、代数形式、加减乘除运算和几何意义",
    "用至少800字详细讲解排列组合的基本原理（分类加法、分步乘法）、排列数和组合数公式",
    "用至少800字详细讲解二项式定理的推导、通项公式、二项式系数性质和常见应用",
    "用至少800字详细讲解离散型随机变量的分布列、期望（均值）和方差的定义与计算",
    "用至少800字详细讲解正态分布的概念、密度曲线特征、3σ原则和标准化变换",
    "用至少800字详细讲解算法的基本概念、程序框图的三种基本逻辑结构（顺序、条件、循环）",
    "用至少800字详细讲解简单随机抽样、系统抽样、分层抽样的方法和适用场景",
    "用至少800字详细讲解两个变量的线性相关、回归分析（最小二乘法）和相关系数",
    "用至少800字详细讲解独立性检验的基本思想、方法和应用，举一个完整例子",
    "用至少800字详细讲解合情推理（归纳推理和类比推理）与演绎推理的区别和应用",
    "用至少800字详细讲解数学归纳法的原理、步骤和常见应用，举两个证明例子",
    "用至少800字详细讲解数列求和的常用方法：公式法、裂项相消、错位相减，各举一例",
    "用至少800字详细讲解不等式的基本性质、均值不等式及其在求最值中的应用",
    "用至少800字详细讲解线性规划的概念、图解法和实际应用，举一个完整例子",
    "用至少800字详细讲解参数方程的概念、常见曲线（圆、椭圆、直线）的参数方程",
    "用至少800字详细讲解极坐标的概念、极坐标与直角坐标的互化和常见曲线的极坐标方程",
    "用至少800字详细讲解随机变量的期望和方差的性质：线性变换、独立变量和差的期望和方差",
    "用至少800字详细讲解条件分布和独立性的关系，以及独立性的判定方法，各举一例",
    "用至少800字详细讲解二项分布的定义、期望方差公式推导、和正态近似（棣莫弗-拉普拉斯）",
    "用至少800字详细讲解超几何分布的定义、与二项分布的区别和联系，举一个实际例子",
    "用至少800字详细讲解空间直角坐标系的建立、空间两点距离公式和中点公式",
    "用至少800字详细讲解空间平面的方程（点法式、一般式、截距式）及其相互转化",
    "用至少800字详细讲解空间直线的方程（参数式、对称式、一般式）及线面位置关系",
    "用至少800字详细讲解圆锥曲线统一定义（焦准距定义）和离心率与曲线形状的关系",
    "用至少800字详细讲解极坐标中圆锥曲线的统一方程推导和各参数的几何意义",
]


async def run():
    from eval.multi_turn_eval import _build_graph, _merge_state_from_events
    from eval._helpers import get_llm_config, call_llm_json
    from eval.llm_judge_eval import _make_judge_result
    from eval.judge_prompts import SUMMARY_FIDELITY_PROMPT

    graph, _, _ = _build_graph()

    conversation_id = "eval-summary-fidelity"
    config = {"configurable": {"thread_id": conversation_id}}

    all_events = []
    all_summaries = []
    summarize_triggered = False

    from app.agent.token_budget import estimate_tokens, TokenBudget
    threshold = int(TokenBudget.CONTEXT_WINDOW * TokenBudget.SUMMARIZE_THRESHOLD)

    print(f"\n{'='*60}")
    print(f"Summary Fidelity 专项测试")
    print(f"需要 {len(TURNS)} 轮对话触发 summarize（阈值 {threshold} tokens）")
    print(f"{'='*60}\n")

    for i, user_msg in enumerate(TURNS):
        input_state = {
            "messages": [HumanMessage(content=user_msg)],
            "question": user_msg,
        }

        turn_start = time.perf_counter()
        turn_events = []
        async for event in graph.astream(input_state, config=config):
            turn_events.append(event)

        elapsed = (time.perf_counter() - turn_start) * 1000

        # 检查是否触发了 summarize
        merged = _merge_state_from_events(turn_events)
        summary = merged.get("conversation_summary")
        if summary:
            summarize_triggered = True
            all_summaries.append(summary)

        # 估算当前累积 token
        all_text = ""
        for evt in all_events:
            for _n, out in evt.items():
                if isinstance(out, dict):
                    for m in out.get("messages", []):
                        if hasattr(m, "content"):
                            all_text += m.content
        current_tokens = estimate_tokens(all_text) + TokenBudget.RESERVED_FOR_RAG + TokenBudget.RESERVED_FOR_OUTPUT
        pct = current_tokens / threshold * 100

        status = "SUMMARIZE!" if summary else "..."
        print(f"  Turn {i+1:2d}/{len(TURNS)}: {elapsed/1000:.1f}s {status} [{current_tokens/1000:.0f}K/{threshold/1000:.0f}K = {pct:.0f}%]")

        all_events.extend(turn_events)

    # 获取最终 state
    final_merged = _merge_state_from_events(all_events)
    final_summary = final_merged.get("conversation_summary", "")

    print(f"\n{'='*60}")
    if not summarize_triggered:
        print("Summarize 未触发 — 对话长度不足以达到 65% 阈值")
        print(f"需要更多轮次或更长的回答才能触发")
        print(f"{'='*60}")
        sys.exit(1)

    print(f"Summarize 已触发!")
    print(f"{'='*60}")

    # 用用户消息构建原始对话
    original_text = "\n".join(
        f"用户：{t}" for t in TURNS
    )

    print(f"\n--- 摘要内容 ---")
    print(final_summary[:500])
    if len(final_summary) > 500:
        print(f"... (共 {len(final_summary)} 字符)")
    print()

    # LLM Judge 评估
    llm_config = get_llm_config()
    prompt = SUMMARY_FIDELITY_PROMPT.format(
        original_messages=original_text,
        summary=final_summary,
    )

    judge_output = call_llm_json(prompt, llm_config)
    judge_result = _make_judge_result("summary_fidelity", judge_output)

    print(f"--- LLM Judge 评估 ---")
    print(f"  维度: summary_fidelity")
    print(f"  得分: {judge_result.score}/5")
    print(f"  断言: {judge_result.assertions}")
    print(f"  理由: {judge_result.reasoning}")
    if judge_result.error:
        print(f"  错误: {judge_result.error}")

    # 判定
    passed = judge_result.score >= 3 and sum(judge_result.assertions) >= 2
    print(f"\n{'='*60}")
    print(f"结论: {'PASS' if passed else 'FAIL'} (score={judge_result.score}/5, assertions={sum(judge_result.assertions)}/3)")
    print(f"{'='*60}")

    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    asyncio.run(run())
