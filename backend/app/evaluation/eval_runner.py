"""检索质量评估运行器

基于评估集运行检索质量评估，计算 Hit Rate@K 和 MRR，
支持 ANY/ALL mode 判定，输出结构化评估报告。

扩展：Context Precision、Faithfulness、Regression、Full 评估模式。

Usage:
    from app.evaluation.eval_runner import EvalRunner
    from app.evaluation.eval_set_loader import EvalSetLoader
    from app.rag.embeddings import DashScopeEmbedding
    from app.rag.vector_store import ChromaDBStore

    runner = EvalRunner(
        embedding_service=embedding_svc,
        vector_store=store,
        eval_loader=EvalSetLoader("data/evaluation"),
    )
    report = runner.run()
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field

from app.config import Settings
from app.domain.protocols import Generator, Reranker
from app.evaluation.eval_set_loader import EvalSetLoader
from app.evaluation.eval_types import EvalItem, EvalSource
from app.rag.embeddings import DashScopeEmbedding
from app.rag.vector_store import ChromaDBStore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 评估结果数据模型
# ---------------------------------------------------------------------------


@dataclass
class EvalDetail:
    """单条评估结果

    Attributes:
        id: 评估问题 ID
        question: 查询问题文本
        hit: 是否命中（Span Hit，@max_k）
        first_rank: 第一个命中的排名（1-based），未命中为 0
        mode: 判定模式 "ANY" | "ALL" | "NEGATIVE"
        section_hit: Section Hit@max_k 是否命中
        keyword_coverage: Keyword Coverage@max_k 覆盖率
        retrieved_texts: top-K 检索结果文本列表
    """

    id: str
    question: str
    hit: bool
    first_rank: int
    mode: str
    section_hit: bool = False
    keyword_coverage: float = 0.0
    retrieved_texts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "question": self.question,
            "hit": self.hit,
            "first_rank": self.first_rank,
            "mode": self.mode,
            "section_hit": self.section_hit,
            "keyword_coverage": self.keyword_coverage,
        }


@dataclass
class BookMetrics:
    """按书汇总的评估指标

    Attributes:
        hit_rate_at_5: Span Hit Rate@5
        hit_rate_at_10: Span Hit Rate@10
        mrr: Mean Reciprocal Rank
        count: 该书的评估条数
        section_hit_at_5: Section Hit@5
        section_hit_at_10: Section Hit@10
        keyword_coverage_at_10: Keyword Coverage@10
    """

    hit_rate_at_5: float
    hit_rate_at_10: float
    mrr: float
    count: int
    section_hit_at_5: float = 0.0
    section_hit_at_10: float = 0.0
    keyword_coverage_at_10: float = 0.0

    def to_dict(self) -> dict:
        return {
            "hit_rate_at_5": self.hit_rate_at_5,
            "hit_rate_at_10": self.hit_rate_at_10,
            "mrr": self.mrr,
            "count": self.count,
            "section_hit_at_5": self.section_hit_at_5,
            "section_hit_at_10": self.section_hit_at_10,
            "keyword_coverage_at_10": self.keyword_coverage_at_10,
        }


@dataclass
class OverallMetrics:
    """总体评估指标

    Attributes:
        hit_rate_at_5: Span Hit Rate@5
        hit_rate_at_10: Span Hit Rate@10
        mrr: Mean Reciprocal Rank
        total_questions: 总评估条数
        section_hit_at_5: Section Hit@5
        section_hit_at_10: Section Hit@10
        keyword_coverage_at_10: Keyword Coverage@10
        negative_pass_rate: Negative Pass Rate
    """

    hit_rate_at_5: float
    hit_rate_at_10: float
    mrr: float
    total_questions: int
    section_hit_at_5: float = 0.0
    section_hit_at_10: float = 0.0
    keyword_coverage_at_10: float = 0.0
    negative_pass_rate: float = 0.0

    def to_dict(self) -> dict:
        return {
            "hit_rate_at_5": self.hit_rate_at_5,
            "hit_rate_at_10": self.hit_rate_at_10,
            "mrr": self.mrr,
            "total_questions": self.total_questions,
            "section_hit_at_5": self.section_hit_at_5,
            "section_hit_at_10": self.section_hit_at_10,
            "keyword_coverage_at_10": self.keyword_coverage_at_10,
            "negative_pass_rate": self.negative_pass_rate,
        }


@dataclass
class EvalReport:
    """评估报告

    Attributes:
        overall: 总体指标
        by_book: 按书汇总（key=书名）
        details: 逐条评估结果
    """

    overall: OverallMetrics
    by_book: dict[str, BookMetrics]
    details: list[EvalDetail]

    def to_dict(self) -> dict:
        """转换为 JSON 可序列化的字典"""
        return {
            "overall": self.overall.to_dict(),
            "by_book": {
                book: metrics.to_dict() for book, metrics in self.by_book.items()
            },
            "details": [d.to_dict() for d in self.details],
        }


# ---------------------------------------------------------------------------
# 扩展评估数据模型 (BB007)
# ---------------------------------------------------------------------------


@dataclass
class ContextPrecisionDetail:
    """单条 Context Precision 评估结果

    Attributes:
        item_id: 评估问题 ID
        question: 查询问题文本
        precision_at_k: Precision@K 分数 (0.0~1.0)
        matched_count: 匹配 truth source 的检索结果数
        total_k: 检索结果总数 K
    """

    item_id: str
    question: str
    precision_at_k: float
    matched_count: int
    total_k: int

    def to_dict(self) -> dict:
        return {
            "item_id": self.item_id,
            "question": self.question,
            "precision_at_k": self.precision_at_k,
            "matched_count": self.matched_count,
            "total_k": self.total_k,
        }


@dataclass
class ContextPrecisionReport:
    """Context Precision 评估报告

    Attributes:
        overall_precision: 平均 Precision@K
        details: 逐条评估详情
    """

    overall_precision: float
    details: list[ContextPrecisionDetail]

    def to_dict(self) -> dict:
        return {
            "overall_precision": self.overall_precision,
            "details": [d.to_dict() for d in self.details],
        }


@dataclass
class FaithfulnessDetail:
    """单条 Faithfulness 评估结果

    Attributes:
        item_id: 评估问题 ID
        question: 查询问题文本
        faithfulness: 忠实度分数 (0.0~1.0)
        coverage: 覆盖度分数 (0.0~1.0)
        unknown_ratio: Unknown 声明占比 (0.0~1.0)
        deterministic_passed: 确定性检查是否通过
        claims: 事实声明判定列表
        coverage_results: 知识点覆盖度判定列表
    """

    item_id: str
    question: str
    faithfulness: float
    coverage: float
    unknown_ratio: float
    deterministic_passed: bool
    claims: list[dict] = field(default_factory=list)
    coverage_results: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "item_id": self.item_id,
            "question": self.question,
            "faithfulness": self.faithfulness,
            "coverage": self.coverage,
            "unknown_ratio": self.unknown_ratio,
            "deterministic_passed": self.deterministic_passed,
            "claims": self.claims,
            "coverage_results": self.coverage_results,
        }


@dataclass
class FaithfulnessReport:
    """Faithfulness 评估报告

    Attributes:
        overall_faithfulness: 平均忠实度分数
        overall_coverage: 平均覆盖度分数
        avg_unknown_ratio: 平均 Unknown 比例
        details: 逐条评估详情
    """

    overall_faithfulness: float
    overall_coverage: float
    avg_unknown_ratio: float
    details: list[FaithfulnessDetail]

    def to_dict(self) -> dict:
        return {
            "overall_faithfulness": self.overall_faithfulness,
            "overall_coverage": self.overall_coverage,
            "avg_unknown_ratio": self.avg_unknown_ratio,
            "details": [d.to_dict() for d in self.details],
        }


@dataclass
class FullEvalReport:
    """全量评估报告（汇总所有指标）

    Attributes:
        regression: 回归测试报告 (None 如果无 regression items)
        context_precision: Context Precision 报告
        faithfulness: Faithfulness 报告
    """

    regression: EvalReport | None
    context_precision: ContextPrecisionReport | None
    faithfulness: FaithfulnessReport | None

    def to_dict(self) -> dict:
        return {
            "regression": self.regression.to_dict() if self.regression else None,
            "context_precision": (
                self.context_precision.to_dict() if self.context_precision else None
            ),
            "faithfulness": (
                self.faithfulness.to_dict() if self.faithfulness else None
            ),
        }


# ---------------------------------------------------------------------------
# 评估运行器
# ---------------------------------------------------------------------------


class EvalRunner:
    """检索质量评估运行器

    编排评估流程：加载评估集 → 逐条查询 → 判定 Hit → 计算指标 → 生成报告。

    Args:
        embedding_service: DashScopeEmbedding 实例（提供 embed_query）
        vector_store: ChromaDBStore 实例（提供 query）
        eval_loader: EvalSetLoader 实例（提供 load），为 None 时使用默认路径
        reranker: Reranker 实例（可选，run_faithfulness/run_full 需要）
        generator: Generator 实例（可选，run_faithfulness/run_full 需要）
        settings: Settings 实例（可选，提供 similarity_threshold 等配置）
    """

    def __init__(
        self,
        embedding_service: DashScopeEmbedding,
        vector_store: ChromaDBStore,
        eval_loader: EvalSetLoader | None = None,
        reranker: Reranker | None = None,
        generator: Generator | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._embedding_service = embedding_service
        self._vector_store = vector_store
        self._eval_loader = eval_loader or EvalSetLoader()
        self._reranker = reranker
        self._generator = generator
        self._settings = settings
        self._indexed_pages_by_book: dict[str, list[int]] | None = None

    def run(
        self,
        eval_filename: str = "eval_set.json",
        top_k_values: list[int] | None = None,
    ) -> EvalReport:
        """运行评估

        对评估集中的每条问题：
        1. 调用 embedding_service.embed_query 获取查询向量
        2. 调用 vector_store.query 获取 top-K 结果（K=max(top_k_values)）
        3. 提取每个结果的 (book, page) 元组
        4. 用 retrieval_truth.check_hit 判定是否命中
        5. 记录第一个命中的排名

        Args:
            eval_filename: 评估集文件名
            top_k_values: 需要计算的 K 值列表，默认 [5, 10]

        Returns:
            EvalReport 评估报告
        """
        if top_k_values is None:
            top_k_values = [5, 10]

        max_k = max(top_k_values)

        # 加载评估集
        items = self._eval_loader.load(eval_filename)
        logger.info("评估集加载完成: %d 条", len(items))

        # 逐条评估
        details: list[EvalDetail] = []
        for item in items:
            detail = self._evaluate_item(item, max_k)
            details.append(detail)
            logger.debug(
                "评估 %s: hit=%s, first_rank=%d, mode=%s",
                item.id,
                detail.hit,
                detail.first_rank,
                detail.mode,
            )

        # 计算指标并生成报告
        report = self._build_report(details, items, top_k_values)
        logger.info(
            "评估完成: Hit Rate@5=%.4f, Hit Rate@10=%.4f, MRR=%.4f",
            report.overall.hit_rate_at_5,
            report.overall.hit_rate_at_10,
            report.overall.mrr,
        )

        return report

    # ------------------------------------------------------------------
    # BB007: 扩展评估方法
    # ------------------------------------------------------------------

    def run_context_precision(
        self,
        eval_filename: str = "eval_set.json",
        top_k: int = 10,
    ) -> ContextPrecisionReport:
        """运行 Context Precision 评估

        对评估集中的每条问题，执行检索并计算 section_id 匹配的 Precision@K。
        Precision@K = 匹配 truth source 的检索结果数 / K

        Args:
            eval_filename: 评估集文件名
            top_k: 检索 top-K 值

        Returns:
            ContextPrecisionReport
        """
        items = self._eval_loader.load(eval_filename)
        logger.info("Context Precision 评估集加载完成: %d 条", len(items))

        details: list[ContextPrecisionDetail] = []
        for item in items:
            # 跳过 NEGATIVE 模式
            if item.retrieval_truth.mode == "NEGATIVE":
                details.append(
                    ContextPrecisionDetail(
                        item_id=item.id,
                        question=item.question,
                        precision_at_k=0.0,
                        matched_count=0,
                        total_k=0,
                    )
                )
                continue

            # 执行检索
            query_embedding = self._embedding_service.embed_query(item.question)
            results = self._vector_store.query(
                query_embedding=query_embedding,
                top_k=top_k,
            )

            # 计算 section_id 匹配数
            matched = 0
            truth_section_ids = set()
            for source in item.retrieval_truth.sources:
                if source.section_id:
                    truth_section_ids.add(source.section_id)

            for r in results:
                chunk_section_id = getattr(r.metadata, "section_id", None)
                if chunk_section_id and chunk_section_id in truth_section_ids:
                    matched += 1
                elif not truth_section_ids:
                    # 无 section_id 时 fallback 到 page range 匹配
                    for source in item.retrieval_truth.sources:
                        if source.overlaps_page_range(
                            r.metadata.book,
                            r.metadata.page_start,
                            r.metadata.page_end,
                        ):
                            matched += 1
                            break

            actual_k = len(results)
            precision = matched / actual_k if actual_k > 0 else 0.0

            details.append(
                ContextPrecisionDetail(
                    item_id=item.id,
                    question=item.question,
                    precision_at_k=precision,
                    matched_count=matched,
                    total_k=actual_k,
                )
            )

        overall = (
            sum(d.precision_at_k for d in details) / len(details) if details else 0.0
        )

        report = ContextPrecisionReport(
            overall_precision=overall,
            details=details,
        )
        logger.info("Context Precision 完成: overall=%.4f", overall)
        return report

    def run_faithfulness(
        self,
        eval_filename: str = "eval_set.json",
        top_k: int = 10,
    ) -> FaithfulnessReport:
        """运行 Faithfulness + Coverage 评估

        管线: embed -> vector_store.query -> threshold filter -> rerank -> generate
              -> deterministic check -> LLM judge

        需要 reranker + generator，缺失时抛出 RuntimeError。

        Args:
            eval_filename: 评估集文件名
            top_k: 检索 top-K 值

        Returns:
            FaithfulnessReport

        Raises:
            RuntimeError: 缺少 reranker 或 generator
        """
        if self._reranker is None:
            raise RuntimeError(
                "run_faithfulness 需要 reranker，请在构造 EvalRunner 时传入"
            )
        if self._generator is None:
            raise RuntimeError(
                "run_faithfulness 需要 generator，请在构造 EvalRunner 时传入"
            )

        from app.evaluation.graders.deterministic import DeterministicGrader
        from app.evaluation.graders.llm_judge import LLMJudge

        threshold = self._settings.similarity_threshold if self._settings else 0.70
        rerank_top_n = self._settings.rerank_top_n if self._settings else 3

        items = self._eval_loader.load(eval_filename)
        logger.info("Faithfulness 评估集加载完成: %d 条", len(items))

        # 初始化 graders
        deterministic_grader = DeterministicGrader()

        llm_judge = LLMJudge(
            api_key=self._settings.newapi_api_key if self._settings else "",
            base_url=self._settings.newapi_base_url
            if self._settings
            else "http://localhost:13000/v1",
            model=self._settings.llm_model if self._settings else "glm-5.1",
        )

        details: list[FaithfulnessDetail] = []
        for item in items:
            detail = self._evaluate_faithfulness_item(
                item=item,
                top_k=top_k,
                threshold=threshold,
                rerank_top_n=rerank_top_n,
                deterministic_grader=deterministic_grader,
                llm_judge=llm_judge,
            )
            details.append(detail)

        # 汇总指标
        if details:
            overall_faith = sum(d.faithfulness for d in details) / len(details)
            overall_cov = sum(d.coverage for d in details) / len(details)
            avg_unknown = sum(d.unknown_ratio for d in details) / len(details)
        else:
            overall_faith = 0.0
            overall_cov = 0.0
            avg_unknown = 0.0

        report = FaithfulnessReport(
            overall_faithfulness=overall_faith,
            overall_coverage=overall_cov,
            avg_unknown_ratio=avg_unknown,
            details=details,
        )
        logger.info(
            "Faithfulness 完成: faith=%.4f, coverage=%.4f, unknown=%.4f",
            overall_faith,
            overall_cov,
            avg_unknown,
        )
        return report

    def _evaluate_faithfulness_item(
        self,
        item: EvalItem,
        top_k: int,
        threshold: float,
        rerank_top_n: int,
        deterministic_grader,
        llm_judge,
    ) -> FaithfulnessDetail:
        """评估单条 Faithfulness item

        Args:
            item: 评估条目
            top_k: 检索 top-K 值
            threshold: 相似度阈值
            rerank_top_n: reranker 返回结果数
            deterministic_grader: 确定性评分器实例
            llm_judge: LLM Judge 实例

        Returns:
            FaithfulnessDetail
        """
        # 1. embed -> vector_store.query
        query_embedding = self._embedding_service.embed_query(item.question)
        results = self._vector_store.query(
            query_embedding=query_embedding,
            top_k=top_k,
        )

        # 2. cosine 阈值过滤
        filtered = [r for r in results if r.score >= threshold]

        # 3. rerank（如 reranker 可用）
        if filtered and self._reranker is not None:
            filtered = self._reranker.rerank(item.question, filtered, rerank_top_n)

        # 4. generator.generate
        if not filtered:
            return FaithfulnessDetail(
                item_id=item.id,
                question=item.question,
                faithfulness=0.0,
                coverage=0.0,
                unknown_ratio=0.0,
                deterministic_passed=False,
            )

        answer, sources = self._generator.generate(item.question, filtered)

        # 5. deterministic check
        det_result = deterministic_grader.check(answer, sources, filtered)

        # 6. LLM judge（合并 context 文本）
        context_text = "\n\n".join(r.text for r in filtered)
        judge_result = llm_judge.judge(
            answer=answer,
            context=context_text,
            key_facts=item.key_facts,
        )

        return FaithfulnessDetail(
            item_id=item.id,
            question=item.question,
            faithfulness=judge_result.faithfulness,
            coverage=judge_result.coverage_score,
            unknown_ratio=judge_result.unknown_ratio,
            deterministic_passed=det_result.passed,
            claims=[
                {"claim": c.claim, "verdict": c.verdict} for c in judge_result.claims
            ],
            coverage_results=[
                {"fact": cr.fact, "status": cr.status} for cr in judge_result.coverage
            ],
        )

    def run_regression(
        self,
        eval_filename: str = "eval_set.json",
        top_k_values: list[int] | None = None,
    ) -> EvalReport:
        """运行回归测试

        筛选 suite="regression" 的 items，调用现有 run() 的底层逻辑。

        Args:
            eval_filename: 评估集文件名
            top_k_values: 需要计算的 K 值列表，默认 [5, 10]

        Returns:
            EvalReport
        """
        if top_k_values is None:
            top_k_values = [5, 10]

        max_k = max(top_k_values)

        # 加载全部 items，筛选 regression
        all_items = self._eval_loader.load(eval_filename)
        regression_items = [item for item in all_items if item.suite == "regression"]
        logger.info("回归测试: %d/%d 条", len(regression_items), len(all_items))

        # 复用现有评估逻辑
        details: list[EvalDetail] = []
        for item in regression_items:
            detail = self._evaluate_item(item, max_k)
            details.append(detail)

        report = self._build_report(details, regression_items, top_k_values)
        logger.info(
            "回归测试完成: Hit Rate@5=%.4f, Hit Rate@10=%.4f, MRR=%.4f",
            report.overall.hit_rate_at_5,
            report.overall.hit_rate_at_10,
            report.overall.mrr,
        )
        return report

    def run_full(
        self,
        eval_filename: str = "eval_set.json",
        top_k_values: list[int] | None = None,
    ) -> FullEvalReport:
        """运行全量评估（汇总所有指标）

        汇总 regression + context_precision + faithfulness。
        需要 reranker + generator。

        Args:
            eval_filename: 评估集文件名
            top_k_values: 需要计算的 K 值列表，默认 [5, 10]

        Returns:
            FullEvalReport

        Raises:
            RuntimeError: 缺少 reranker 或 generator
        """
        if self._reranker is None:
            raise RuntimeError("run_full 需要 reranker，请在构造 EvalRunner 时传入")
        if self._generator is None:
            raise RuntimeError("run_full 需要 generator，请在构造 EvalRunner 时传入")

        if top_k_values is None:
            top_k_values = [5, 10]

        top_k = max(top_k_values)

        # 1. Regression
        regression_report = self.run_regression(eval_filename, top_k_values)

        # 2. Context Precision
        context_precision_report = self.run_context_precision(eval_filename, top_k)

        # 3. Faithfulness
        faithfulness_report = self.run_faithfulness(eval_filename, top_k)

        report = FullEvalReport(
            regression=regression_report,
            context_precision=context_precision_report,
            faithfulness=faithfulness_report,
        )
        logger.info("全量评估完成")
        return report

    def _evaluate_item(self, item: EvalItem, max_k: int) -> EvalDetail:
        """评估单条问题

        Args:
            item: 评估条目
            max_k: 最大 top-K 值

        Returns:
            评估详情
        """
        if item.retrieval_truth.mode == "NEGATIVE":
            # NEGATIVE 模式不使用检索结果，跳过 API 调用
            return EvalDetail(
                id=item.id,
                question=item.question,
                hit=False,
                first_rank=0,
                mode=item.retrieval_truth.mode,
                section_hit=False,
                keyword_coverage=0.0,
            )

        # 获取查询向量
        query_embedding = self._embedding_service.embed_query(item.question)

        # 检索 top-K 结果
        results = self._vector_store.query(
            query_embedding=query_embedding,
            top_k=max_k,
        )

        # 提取检索结果覆盖的页码区间。
        # Chroma 中的 page 常是章节起始页；用下一 indexed page 推断当前 chunk 覆盖范围，
        # 这样 truth 可以标真实答案页段，而不是被迫标整章起始页。
        book_page_ranges = [
            self._infer_result_page_range(r.metadata.book, r.metadata.page)
            for r in results
        ]

        # 判定是否命中（check_hit_ranges 统一处理 ANY/ALL/NEGATIVE）
        hit = item.retrieval_truth.check_hit_ranges(book_page_ranges)

        # 计算第一个命中的排名
        first_rank = self._find_first_rank(item, book_page_ranges)

        # 计算 Section Hit
        section_hit = self._check_section_hit(item, results)

        # 计算 Keyword Coverage
        keyword_coverage = self._calc_keyword_coverage_for_item(item, results)

        # 收集检索文本
        retrieved_texts = [r.text for r in results]

        return EvalDetail(
            id=item.id,
            question=item.question,
            hit=hit,
            first_rank=first_rank,
            mode=item.retrieval_truth.mode,
            section_hit=section_hit,
            keyword_coverage=keyword_coverage,
            retrieved_texts=retrieved_texts,
        )

    def _infer_result_page_range(self, book: str, page: int) -> tuple[str, int, int]:
        """根据当前 Chroma indexed page 推断检索结果覆盖的页码区间"""
        pages_by_book = self._get_indexed_pages_by_book()
        pages = pages_by_book.get(book, [])
        page_end = page
        for indexed_page in pages:
            if indexed_page > page:
                page_end = indexed_page - 1
                break
        return (book, page, page_end)

    def _get_indexed_pages_by_book(self) -> dict[str, list[int]]:
        """读取 Chroma 元数据，按书缓存 indexed page 列表

        单元测试中的 mock store 没有 Chroma collection，此时退化为空映射，
        检索结果按单页处理。
        """
        if self._indexed_pages_by_book is not None:
            return self._indexed_pages_by_book

        collection = getattr(self._vector_store, "_collection", None)
        if collection is None:
            self._indexed_pages_by_book = {}
            return self._indexed_pages_by_book

        indexed_pages: dict[str, set[int]] = defaultdict(set)
        try:
            data = collection.get(include=["metadatas"])
        except Exception:
            logger.debug(
                "读取 Chroma indexed pages 失败，退化为单页命中判定", exc_info=True
            )
            self._indexed_pages_by_book = {}
            return self._indexed_pages_by_book

        for metadata in data.get("metadatas") or []:
            book = metadata.get("book")
            page = metadata.get("page")
            if not book or page is None:
                continue
            indexed_pages[str(book)].add(int(page))

        self._indexed_pages_by_book = {
            book: sorted(pages) for book, pages in indexed_pages.items()
        }
        return self._indexed_pages_by_book

    def _check_section_hit(self, item: EvalItem, results: list) -> bool:
        """检查 Section Hit

        如果 truth source 和 chunk 都有 section_id，直接比较 section_id。
        如果任一方缺少 section_id，fallback 到 page range 匹配（即 Span Hit 逻辑）。

        Args:
            item: 评估条目
            results: QueryResult 列表

        Returns:
            是否 Section Hit
        """
        truth = item.retrieval_truth
        if truth.mode == "NEGATIVE":
            return False

        if truth.mode == "ANY":
            for source in truth.sources:
                for r in results:
                    if self._section_matches(source, r):
                        return True
            return False
        else:  # ALL
            for source in truth.sources:
                matched = False
                for r in results:
                    if self._section_matches(source, r):
                        matched = True
                        break
                if not matched:
                    return False
            return True

    @staticmethod
    def _section_matches(source: EvalSource, result) -> bool:
        """判定单个 source 与单个 result 是否 section 匹配

        如果双方都有 section_id，直接比较。
        否则 fallback 到 page range 匹配。
        """
        chunk_section_id = getattr(result.metadata, "section_id", None)

        if source.section_id is not None and chunk_section_id:
            return source.section_id == chunk_section_id
        # Fallback: 使用 page range 匹配
        return source.overlaps_page_range(
            result.metadata.book,
            result.metadata.page_start,
            result.metadata.page_end,
        )

    def _calc_keyword_coverage_for_item(self, item: EvalItem, results: list) -> float:
        """计算单条问题的 Keyword Coverage

        对每个 source 的 required_keywords，检查 top-K 结果的 chunk text 是否包含。
        覆盖率 = 所有 source 的被找到关键词总数 / 所有 source 的总关键词数。
        没有任何 required_keywords 时返回 0.0。

        Args:
            item: 评估条目
            results: QueryResult 列表

        Returns:
            Keyword Coverage（0.0 ~ 1.0）
        """
        all_keywords: list[str] = []
        for source in item.retrieval_truth.sources:
            all_keywords.extend(source.required_keywords)

        if not all_keywords:
            return 0.0

        texts = " ".join(r.text for r in results).lower()
        found = sum(1 for kw in all_keywords if kw.lower() in texts)
        return found / len(all_keywords)

    @staticmethod
    def _find_first_rank(
        item: EvalItem,
        book_page_ranges: list[tuple[str, int] | tuple[str, int, int]],
    ) -> int:
        """找到第一个命中的排名位置

        使用 ANY 语义：遍历 book_page_ranges，找到第一个
        与任一 source 范围重叠的结果，返回其 1-based 排名。
        未命中返回 0。

        Args:
            item: 评估条目
            book_page_ranges: 检索结果的 (book, page_start, page_end) 元组列表

        Returns:
            第一个命中的 1-based 排名，未命中返回 0
        """
        for rank, result_range in enumerate(book_page_ranges, start=1):
            if len(result_range) == 2:
                book, page_start = result_range
                page_end = page_start
            else:
                book, page_start, page_end = result_range
            for source in item.retrieval_truth.sources:
                if source.overlaps_page_range(book, page_start, page_end):
                    return rank
        return 0

    @staticmethod
    def _build_report(
        details: list[EvalDetail],
        items: list[EvalItem],
        top_k_values: list[int],
    ) -> EvalReport:
        """构建评估报告

        Args:
            details: 逐条评估结果
            items: 评估条目（用于确定每条所属的书）
            top_k_values: K 值列表

        Returns:
            完整的评估报告
        """
        total = len(details)
        if total == 0:
            return EvalReport(
                overall=OverallMetrics(
                    hit_rate_at_5=0.0,
                    hit_rate_at_10=0.0,
                    mrr=0.0,
                    total_questions=0,
                ),
                by_book={},
                details=[],
            )

        # NEGATIVE 条目不计入 Hit/MRR/Section/Keyword 指标计算，在此统一过滤
        eligible_details = [d for d in details if d.mode != "NEGATIVE"]

        # 按 K 值计算 Span Hit Rate
        hit_rate_by_k: dict[int, float] = {}
        for k in top_k_values:
            hit_rate_by_k[k] = _calc_hit_rate_at_k(eligible_details, k)

        # 计算 MRR
        mrr = _calc_mrr(eligible_details)

        # 计算 Section Hit@K
        section_hit_by_k: dict[int, float] = {}
        for k in top_k_values:
            section_hit_by_k[k] = _calc_section_hit_at_k(eligible_details, k)

        # 计算 Keyword Coverage@K
        keyword_coverage_by_k: dict[int, float] = {}
        for k in top_k_values:
            keyword_coverage_by_k[k] = _calc_keyword_coverage_at_k(
                eligible_details, items, k
            )

        # 计算 Negative Pass Rate
        negative_pass_rate = _calc_negative_pass_rate(details)

        # Overall 指标
        overall = OverallMetrics(
            hit_rate_at_5=hit_rate_by_k.get(5, 0.0),
            hit_rate_at_10=hit_rate_by_k.get(10, 0.0),
            mrr=mrr,
            total_questions=total,
            section_hit_at_5=section_hit_by_k.get(5, 0.0),
            section_hit_at_10=section_hit_by_k.get(10, 0.0),
            keyword_coverage_at_10=keyword_coverage_by_k.get(10, 0.0),
            negative_pass_rate=negative_pass_rate,
        )

        # 按书分组（NEGATIVE 条目不参与）
        eligible_items = [
            item for item in items if item.retrieval_truth.mode != "NEGATIVE"
        ]
        book_groups = _group_by_book(eligible_details, eligible_items)
        by_book: dict[str, BookMetrics] = {}
        for book, group_details in book_groups.items():
            count = len(group_details)
            if count == 0:
                continue

            book_hr5 = _calc_hit_rate_at_k(group_details, 5)
            book_hr10 = _calc_hit_rate_at_k(group_details, 10)
            book_mrr = _calc_mrr(group_details)
            book_sh5 = _calc_section_hit_at_k(group_details, 5)
            book_sh10 = _calc_section_hit_at_k(group_details, 10)
            book_kc10 = _calc_keyword_coverage_at_k(group_details, eligible_items, 10)

            by_book[book] = BookMetrics(
                hit_rate_at_5=book_hr5,
                hit_rate_at_10=book_hr10,
                mrr=book_mrr,
                count=count,
                section_hit_at_5=book_sh5,
                section_hit_at_10=book_sh10,
                keyword_coverage_at_10=book_kc10,
            )

        return EvalReport(
            overall=overall,
            by_book=by_book,
            details=details,
        )


# ---------------------------------------------------------------------------
# 指标计算辅助函数（模块级别，便于测试）
# ---------------------------------------------------------------------------


def _calc_hit_rate_at_k(
    details: list[EvalDetail],
    k: int,
) -> float:
    """计算 Hit Rate@K

    判定规则：
    - ANY mode: first_rank <= K 即为命中
    - ALL mode: hit=True 即为命中（check_hit 已基于 max_k 判定，max_k >= K）

    Args:
        details: 评估详情列表（已排除 NEGATIVE 条目）
        k: top-K 的 K 值

    Returns:
        Hit Rate@K（0.0 ~ 1.0）
    """
    if not details:
        return 0.0

    hit_count = 0
    for d in details:
        if d.mode == "ANY":
            if d.first_rank > 0 and d.first_rank <= k:
                hit_count += 1
        else:  # ALL
            if d.hit:
                hit_count += 1

    return hit_count / len(details)


def _calc_mrr(details: list[EvalDetail]) -> float:
    """计算 MRR (Mean Reciprocal Rank)

    MRR = sum(1/rank) / total
    未命中的条目得分为 0。

    Args:
        details: 评估详情列表（已排除 NEGATIVE 条目）

    Returns:
        MRR 值（0.0 ~ 1.0）
    """
    if not details:
        return 0.0

    total_score = 0.0
    for d in details:
        if d.first_rank > 0:
            total_score += 1.0 / d.first_rank

    return total_score / len(details)


def _group_by_book(
    details: list[EvalDetail],
    items: list[EvalItem],
) -> dict[str, list[EvalDetail]]:
    """将评估详情按所属书名分组

    每条 EvalItem 的 retrieval_truth.sources 可能涉及多本书，
    我们取第一个 source 的 book 作为该条目的"主书"。

    Args:
        details: 评估详情列表
        items: 对应的 EvalItem 列表

    Returns:
        按书名分组的详情字典
    """
    # 建立 id -> book 的映射
    id_to_book: dict[str, str] = {}
    for item in items:
        # 取第一个 source 的 book 作为主书
        if item.retrieval_truth.sources:
            id_to_book[item.id] = item.retrieval_truth.sources[0].book

    groups: dict[str, list[EvalDetail]] = defaultdict(list)
    for detail in details:
        book = id_to_book.get(detail.id, "unknown")
        groups[book].append(detail)

    return dict(groups)


def _calc_section_hit_at_k(details: list[EvalDetail], k: int) -> float:
    """计算 Section Hit@K

    判定规则与 _calc_hit_rate_at_k 相同，但使用 section_hit 而非 hit/first_rank。
    - ANY mode: section_hit=True 即为命中
    - ALL mode: section_hit=True 即为命中

    Args:
        details: 评估详情列表（已排除 NEGATIVE 条目）
        k: top-K 的 K 值（用于向后兼容，当前 section_hit 基于 max_k 判定）

    Returns:
        Section Hit@K（0.0 ~ 1.0）
    """
    if not details:
        return 0.0

    hit_count = sum(1 for d in details if d.section_hit)
    return hit_count / len(details)


def _calc_keyword_coverage_at_k(
    details: list[EvalDetail],
    items: list[EvalItem],
    k: int,
) -> float:
    """计算 Keyword Coverage@K

    对每个有 required_keywords 的条目，取其 keyword_coverage 的平均值。
    没有 required_keywords 的条目不参与计算。

    Args:
        details: 评估详情列表（已排除 NEGATIVE 条目）
        items: 对应的 EvalItem 列表
        k: top-K 的 K 值

    Returns:
        平均 Keyword Coverage@K（0.0 ~ 1.0），无符合条目时返回 0.0
    """
    if not details or not items:
        return 0.0

    # 建立 id -> item 的映射，用于判断是否有 required_keywords
    id_to_item: dict[str, EvalItem] = {item.id: item for item in items}

    coverages: list[float] = []
    for d in details:
        item = id_to_item.get(d.id)
        if item is None:
            continue
        has_keywords = any(
            source.required_keywords for source in item.retrieval_truth.sources
        )
        if has_keywords:
            coverages.append(d.keyword_coverage)

    if not coverages:
        return 0.0
    return sum(coverages) / len(coverages)


def _calc_negative_pass_rate(details: list[EvalDetail]) -> float:
    """计算 Negative Pass Rate

    NEGATIVE 模式的条目中 hit=False 的比例。越高越好。
    现有逻辑中 NEGATIVE 不走检索，直接 hit=False，所以应该总是 100%。

    Args:
        details: 全部评估详情列表（含 NEGATIVE 条目）

    Returns:
        Negative Pass Rate（0.0 ~ 1.0），无 NEGATIVE 条目时返回 0.0
    """
    negative_details = [d for d in details if d.mode == "NEGATIVE"]
    if not negative_details:
        return 0.0

    pass_count = sum(1 for d in negative_details if not d.hit)
    return pass_count / len(negative_details)
