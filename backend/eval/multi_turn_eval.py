"""R010 多轮对话确定性评估

使用方式：
    cd backend
    python -m eval.multi_turn_eval --dataset eval/datasets/multi_turn_eval.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from eval.graders import (
    TestCaseResult,
    state_check,
    tool_calls_check,
    transcript_check,
    deterministic_filter,
)


def _build_graph():
    """构建 graph：真实 LLM（GLM-5.1）+ 真实检索管线"""
    import os
    from dataclasses import dataclass
    from dotenv import dotenv_values

    from app.agent.graph import create_graph
    from app.infra.llm import LLMGenerator
    from app.rag.vector_store import ChromaDBStore
    from app.rag.embeddings import DashScopeEmbedding
    from app.infra.bm25 import BM25Retriever
    from app.infra.reranker import DashScopeReranker
    from app.chat.service import ChatService

    env = dotenv_values(".env")

    def _conf(key: str, default: str = "") -> str:
        """优先 .env，其次环境变量"""
        return env.get(key, "") or os.environ.get(key, default)

    # LLM 配置
    api_key = _conf("NEWAPI_API_KEY")
    base_url = _conf("NEWAPI_BASE_URL", "http://localhost:13000/v1")
    model = _conf("LLM_MODEL", "glm-5.1")
    print(f"[eval] LLM: {model} @ {base_url}")

    generator = LLMGenerator(
        api_key=api_key,
        base_url=base_url,
        model=model,
    )

    # 真实检索管线
    dashscope_key = _conf("DASHSCOPE_API_KEY")
    print("[eval] 真实检索管线: ChromaDB + DashScope Embedding + BM25 + Reranker")

    vector_store = ChromaDBStore(
        persist_directory="data/chroma_db",
        collection_name="octotutor_chunks",
    )
    embedding = DashScopeEmbedding(
        api_key=dashscope_key,
        model="text-embedding-v4",
        dimension=1024,
    )
    bm25 = BM25Retriever()
    all_chunks = vector_store.get_all_chunks()
    if all_chunks:
        bm25.build_index(all_chunks)
    print(f"[eval] ChromaDB chunks: {len(all_chunks)}")

    reranker = DashScopeReranker(
        api_key=dashscope_key,
        model="gte-rerank",
    )

    # 简化 settings（只包含检索相关配置）
    @dataclass
    class _SimpleSettings:
        retrieval_top_k: int = 20
        similarity_threshold: float = 0.70
        bm25_enabled: bool = True
        rrf_k: int = 60
        rerank_top_n: int = 3
        chat_max_context_tokens: int = 3000

    chat_service = ChatService(
        embedding=embedding,
        vector_store=vector_store,
        bm25=bm25,
        reranker=reranker,
        generator=generator,
        settings=_SimpleSettings(),
    )

    graph = create_graph(
        checkpointer=MemorySaver(),
        chat_service=chat_service,
        generator=generator,
    )

    return graph, chat_service, generator


def _merge_state_from_events(events: list[dict]) -> dict:
    """从 LangGraph astream 事件列表合并最终 state"""
    merged = {}
    for evt in events:
        for _node_name, node_output in evt.items():
            if isinstance(node_output, dict):
                for k, v in node_output.items():
                    if k == "messages":
                        # 保留最后的 AI 消息内容
                        for msg in reversed(v):
                            if hasattr(msg, "type") and msg.type == "ai":
                                merged["last_ai_answer"] = str(msg.content)
                                break
                    else:
                        merged[k] = v
    return merged


def _extract_event_keys(events: list[dict]) -> list[str]:
    """从事件列表提取节点执行顺序"""
    return [list(e.keys())[0] for e in events]


def _get_last_turn_events(all_events: list[dict]) -> list[dict]:
    """从全部事件中提取最后一轮的事件"""
    last_turn_events = []
    for evt in reversed(all_events):
        key = list(evt.keys())[0]
        last_turn_events.insert(0, evt)
        if key == "summarize":
            break

    return last_turn_events if last_turn_events else all_events


async def _run_single_case(
    graph,
    case: dict,
) -> tuple[TestCaseResult, dict]:
    """执行单条评估用例，返回 (result, final_state)"""
    turns = case["turns"]
    expected = case["expected"]
    is_negative = case.get("negative", False)

    start_time = time.perf_counter()

    all_events: list[dict] = []
    all_states: list[dict] = []
    conversation_id = f"eval-{case['id']}"

    config = {
        "configurable": {
            "thread_id": conversation_id,
        }
    }

    for _i, turn in enumerate(turns):
        user_msg = turn["content"]

        input_state = {
            "messages": [HumanMessage(content=user_msg)],
            "question": user_msg,
        }

        turn_events: list[dict] = []
        async for event in graph.astream(input_state, config=config):
            turn_events.append(event)

        all_events.extend(turn_events)
        merged = _merge_state_from_events(turn_events)
        all_states.append(merged)

    elapsed_ms = (time.perf_counter() - start_time) * 1000

    final_state = all_states[-1] if all_states else {}
    final_state["question"] = turns[-1]["content"]
    is_first_turn = len(turns) == 1

    last_turn_events = _get_last_turn_events(all_events)
    last_turn_keys = _extract_event_keys(last_turn_events)

    # 运行 graders
    sc = state_check(final_state, expected, is_first_turn=is_first_turn)
    tc = tool_calls_check(last_turn_keys, expected, is_first_turn=is_first_turn)
    tr = transcript_check(all_events, elapsed_ms, is_first_turn=is_first_turn)
    df = deterministic_filter(final_state, all_events, expected, is_negative)

    metrics = {
        "n_events": len(all_events),
        "n_turns": len(turns),
        "time_to_last_token_ms": round(elapsed_ms, 1),
    }

    result = TestCaseResult(
        test_id=case["id"],
        level=case["level"],
        category=case["category"],
        negative=is_negative,
        state_check=sc,
        tool_calls=tc,
        transcript=tr,
        deterministic_filter=df,
        tracked_metrics=metrics,
        execution_time_ms=elapsed_ms,
    )
    return result, final_state


async def run_eval(
    dataset_path: str,
) -> tuple[list[TestCaseResult], list[dict]]:
    """运行完整评估，返回 (results, all_final_states)"""
    with open(dataset_path, "r", encoding="utf-8") as f:
        cases = json.load(f)

    graph, _, _ = _build_graph()

    results = []
    all_states = []
    for case in cases:
        result, final_state = await _run_single_case(graph, case)
        results.append(result)
        all_states.append(final_state)

    return results, all_states


def print_report(results: list[TestCaseResult]) -> bool:
    """打印评估报告，返回 True 如果全部通过"""
    print("\n" + "=" * 60)
    print("R010 多轮对话确定性评估报告（GLM-5.1 真实 LLM）")
    print("=" * 60)

    all_passed = True
    for r in results:
        graders_all_pass = (
            r.state_check.passed
            and r.tool_calls.passed
            and r.transcript.passed
            and r.deterministic_filter.passed
        )
        status = "PASS" if graders_all_pass else "FAIL"
        if status == "FAIL":
            all_passed = False
        neg_tag = " [NEG]" if r.negative else ""
        print(f"\n{r.test_id}{neg_tag}: {status}")

        for grader in [
            r.state_check,
            r.tool_calls,
            r.transcript,
            r.deterministic_filter,
        ]:
            icon = "v" if grader.passed else "X"
            detail_str = (
                "pass"
                if grader.passed
                else "FAIL - " + "; ".join(grader.details)
            )
            print(f"  [{icon}] {grader.name}: {detail_str}")

        print(f"  metrics: {r.execution_time_ms:.0f}ms | {r.tracked_metrics}")

    total = len(results)
    passed = sum(
        1
        for r in results
        if all(
            [
                r.state_check.passed,
                r.tool_calls.passed,
                r.transcript.passed,
                r.deterministic_filter.passed,
            ]
        )
    )

    print(f"\n{'=' * 60}")
    print(
        f"汇总: {passed}/{total} 通过"
        f" ({'ALL PASS' if all_passed else 'HAS FAILURES'})"
    )
    print(f"{'=' * 60}\n")

    return all_passed


def main():
    parser = argparse.ArgumentParser(
        description="R010 多轮对话确定性评估"
    )
    parser.add_argument(
        "--dataset", required=True, help="评估数据集 JSON 路径"
    )
    args = parser.parse_args()

    results, _ = asyncio.run(run_eval(args.dataset))
    all_passed = print_report(results)

    print("--- static_analysis ---")
    import subprocess

    try:
        r = subprocess.run(
            ["python3", "-m", "ruff", "check", "eval/"],
            capture_output=True,
            text=True,
        )
        if r.returncode == 0:
            print("ruff check eval/: PASS")
        else:
            print(f"ruff check eval/: FAIL\n{r.stdout}")
            all_passed = False
    except FileNotFoundError:
        print("ruff: SKIPPED (not installed)")

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
