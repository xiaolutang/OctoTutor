"""R010 改动后实际评估脚本

运行全量评估：regression + context_precision + faithfulness
输出对比报告。
"""

import json
import os
import sys
import time

os.environ.setdefault("JWT_SECRET_KEY", "eval-only")

from app.config import settings
from app.rag.embeddings import DashScopeEmbedding
from app.rag.vector_store import ChromaDBStore
from app.infra.reranker import DashScopeReranker
from app.infra.llm import LLMGenerator
from app.evaluation.eval_runner import EvalRunner
from app.evaluation.eval_set_loader import EvalSetLoader


def main():
    print("=" * 60)
    print("R010 实际评估")
    print("=" * 60)
    print(f"LLM: {settings.llm_model}")
    print(f"Relevance Threshold: {settings.relevance_threshold}")
    print(f"Similarity Threshold: {settings.similarity_threshold}")
    print(f"Eval dir: data/evaluation/")
    print()

    # 初始化依赖
    print("[1/5] 初始化 Embedding + ChromaDB...")
    embedding = DashScopeEmbedding(
        api_key=settings.dashscope_api_key,
        dimension=settings.dashscope_embedding_dimension,
    )
    vector_store = ChromaDBStore(persist_directory=settings.chroma_persist_dir)
    print(f"  向量库文档数: {vector_store.count()}")

    print("[2/5] 初始化 Reranker + Generator...")
    # Reranker API 无权限，用 mock 透传（跳过 rerank 步骤）
    from unittest.mock import MagicMock
    reranker = MagicMock()
    reranker.rerank = lambda query, results, top_n: results[:top_n]
    generator = LLMGenerator(
        api_key=settings.newapi_api_key,
        base_url=settings.newapi_base_url,
        model=settings.llm_model,
    )

    print("[3/5] 初始化 EvalRunner...")
    loader = EvalSetLoader(eval_dir="data/evaluation")
    runner = EvalRunner(
        embedding_service=embedding,
        vector_store=vector_store,
        eval_loader=loader,
        reranker=reranker,
        generator=generator,
        settings=settings,
    )

    # Run regression
    print("\n[4/5] 运行 Regression (eval_set.json)...")
    t0 = time.time()
    reg_report = runner.run_regression("eval_set.json")
    print(f"  耗时: {time.time() - t0:.1f}s")
    print(f"  Total: {reg_report.overall.total_questions}")
    print(f"  Hit Rate@5:  {reg_report.overall.hit_rate_at_5:.2%}")
    print(f"  Hit Rate@10: {reg_report.overall.hit_rate_at_10:.2%}")
    print(f"  MRR:         {reg_report.overall.mrr:.4f}")
    print(f"  Section Hit@5:  {reg_report.overall.section_hit_at_5:.2%}")
    print(f"  Section Hit@10: {reg_report.overall.section_hit_at_10:.2%}")
    print(f"  Negative Pass:  {reg_report.overall.negative_pass_rate:.2%}")

    # Run context precision
    print("\n[5/5] 运行 Context Precision...")
    t0 = time.time()
    ctx_report = runner.run_context_precision("eval_set.json")
    print(f"  耗时: {time.time() - t0:.1f}s")
    print(f"  Overall Precision: {ctx_report.overall_precision:.2%}")
    print(f"  Details: {len(ctx_report.details)} items")

    # Run faithfulness (核心指标) — 全量
    print("\n[BONUS] 运行 Faithfulness 评估 (eval_set_faithfulness.json)...")
    print("  这一步会调用真实 LLM，耗时较长...")
    t0 = time.time()
    faith_report = runner.run_faithfulness("eval_set_faithfulness.json")
    elapsed = time.time() - t0
    print(f"  耗时: {elapsed:.1f}s")
    print(f"  Details: {len(faith_report.details)} items")
    print(f"  Overall Faithfulness: {faith_report.overall_faithfulness:.2%}")
    print(f"  Overall Coverage:     {faith_report.overall_coverage:.2%}")
    print(f"  Avg Unknown Ratio:    {faith_report.avg_unknown_ratio:.2%}")
    print(f"  Overall Relevance:    {faith_report.overall_relevance:.2%}")

    # 确定性检查通过率
    det_pass = sum(1 for d in faith_report.details if d.deterministic_passed)
    print(f"  Deterministic Pass:   {det_pass}/{len(faith_report.details)} ({det_pass/len(faith_report.details):.0%})")

    # Faithfulness 分布
    bins = {">=0.8": 0, "0.5-0.8": 0, "<0.5": 0}
    for d in faith_report.details:
        if d.faithfulness >= 0.8:
            bins[">=0.8"] += 1
        elif d.faithfulness >= 0.5:
            bins["0.5-0.8"] += 1
        else:
            bins["<0.5"] += 1
    print(f"  Faithfulness 分布: {bins}")

    # 保存报告
    print("\n保存报告...")
    with open("data/evaluation/report_r010_regression.json", "w") as f:
        json.dump(reg_report.to_dict(), f, ensure_ascii=False, indent=2)
    with open("data/evaluation/report_r010_faithfulness.json", "w") as f:
        json.dump(faith_report.to_dict(), f, ensure_ascii=False, indent=2)

    print("完成！")


if __name__ == "__main__":
    main()
