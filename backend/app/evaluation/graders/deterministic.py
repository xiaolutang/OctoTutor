"""确定性评分器 — 0 成本前置检查

在调用 LLM judge 之前执行确定性规则检查：
1. answer 非空
2. sources 非空
3. 引用页码在 context 范围内
4. 无重复 chunk_id

任一检查不通过则标记 FAIL，跳过 LLM judge。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.models import SourceReference
from app.rag.models import QueryResult


@dataclass
class GradingResult:
    """确定性评分结果

    Attributes:
        passed: 是否通过全部检查
        failures: 未通过的检查项描述列表
    """

    passed: bool
    failures: list[str] = field(default_factory=list)


class DeterministicGrader:
    """确定性前置检查评分器

    执行 0 成本的规则检查，不调用任何 LLM。
    用于在 LLM judge 前过滤明显不合格的回答。

    Usage:
        grader = DeterministicGrader()
        result = grader.check(answer, sources, context)
        if not result.passed:
            # 跳过 LLM judge，直接标记 FAIL
    """

    def check(
        self,
        answer: str,
        sources: list[SourceReference],
        context: list[QueryResult],
    ) -> GradingResult:
        """执行全部确定性检查

        Args:
            answer: 模型生成的回答文本
            sources: 回答中引用的来源列表
            context: 检索到的上下文 chunk 列表

        Returns:
            GradingResult，passed=True 表示通过全部检查
        """
        failures: list[str] = []

        # 检查 1: answer 非空
        if not answer or not answer.strip():
            failures.append("answer 为空")

        # 检查 2: sources 非空
        if not sources:
            failures.append("sources 为空")

        # 检查 3: 引用页码在 context 范围内
        page_failures = self._check_page_ranges(sources, context)
        failures.extend(page_failures)

        # 检查 4: 无重复 chunk_id
        dup_failures = self._check_duplicate_chunk_ids(sources)
        failures.extend(dup_failures)

        return GradingResult(passed=len(failures) == 0, failures=failures)

    def _check_page_ranges(
        self,
        sources: list[SourceReference],
        context: list[QueryResult],
    ) -> list[str]:
        """检查每个 source 的页码范围是否与 context 中任一 chunk 有交集

        对于每个 source，遍历 context 中的所有 chunk，只要找到任意一个
        同 book 且页码范围有交集的 chunk 即视为通过。
        未找到匹配的 source 记录为失败。

        Args:
            sources: 回答中引用的来源列表
            context: 检索到的上下文 chunk 列表

        Returns:
            失败描述列表
        """
        if not sources or not context:
            return []

        failures: list[str] = []
        for source in sources:
            found = False
            for chunk in context:
                meta = chunk.metadata
                if meta.book != source.book:
                    continue
                # 检查页码范围是否有交集
                if max(meta.page_start, source.page_start) <= min(
                    meta.page_end, source.page_end
                ):
                    found = True
                    break
            if not found:
                failures.append(
                    f"source 页码范围无匹配: {source.book} "
                    f"p{source.page_start}-{source.page_end}"
                )

        return failures

    def _check_duplicate_chunk_ids(
        self,
        sources: list[SourceReference],
    ) -> list[str]:
        """检查 sources 中是否有重复的 chunk_id

        Args:
            sources: 回答中引用的来源列表

        Returns:
            失败描述列表
        """
        if not sources:
            return []

        seen: set[str] = set()
        duplicates: set[str] = set()
        for source in sources:
            if source.chunk_id in seen:
                duplicates.add(source.chunk_id)
            else:
                seen.add(source.chunk_id)

        if duplicates:
            return [f"重复 chunk_id: {', '.join(sorted(duplicates))}"]
        return []
