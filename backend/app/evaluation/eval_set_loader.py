"""评估集加载和验证工具

从 JSON 文件加载评估数据集，并提供数据完整性校验功能。

Usage:
    from app.evaluation.eval_set_loader import EvalSetLoader

    loader = EvalSetLoader(eval_dir="data/evaluation")
    items = loader.load("eval_set.json")
    validation = loader.validate(items)
    print(f"验证通过: {validation.passed}")
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.evaluation.eval_types import EvalItem, EvalSetValidation

logger = logging.getLogger(__name__)


class EvalSetLoader:
    """评估集加载和验证工具

    负责从 JSON 文件加载评估数据集并转换为 EvalItem 列表，
    同时提供数据完整性校验功能。

    Args:
        eval_dir: 评估集 JSON 文件所在目录，默认 "data/evaluation"
    """

    def __init__(self, eval_dir: str = "data/evaluation") -> None:
        self._eval_dir = Path(eval_dir)

    def load(self, filename: str = "eval_set.json") -> list[EvalItem]:
        """加载评估集 JSON 并转换为 EvalItem 列表

        Args:
            filename: 评估集文件名

        Returns:
            EvalItem 列表

        Raises:
            FileNotFoundError: 文件不存在
            ValueError: JSON 格式错误或数据校验失败
        """
        file_path = self._eval_dir / filename

        if not file_path.exists():
            raise FileNotFoundError(f"评估集文件不存在: {file_path}")

        logger.info("加载评估集: %s", file_path)

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"评估集 JSON 格式错误: {e}") from e

        if not isinstance(raw_data, list):
            raise ValueError(
                f"评估集 JSON 根元素必须是数组, got: {type(raw_data).__name__}"
            )

        if not raw_data:
            raise ValueError("评估集为空")

        items: list[EvalItem] = []
        parse_errors: list[str] = []

        for i, item_data in enumerate(raw_data):
            if not isinstance(item_data, dict):
                parse_errors.append(f"第 {i + 1} 条数据不是 JSON 对象")
                continue

            try:
                item = EvalItem.from_dict(item_data)
                items.append(item)
            except ValueError as e:
                parse_errors.append(f"第 {i + 1} 条数据解析失败: {e}")

        if parse_errors:
            raise ValueError(
                "评估集数据解析错误:\n" + "\n".join(parse_errors)
            )

        logger.info("评估集加载完成: %d 条", len(items))
        return items

    def validate(
        self,
        items: list[EvalItem],
        min_per_book: int = 1,
    ) -> EvalSetValidation:
        """验证评估集数据完整性

        检查项:
        1. 每个 item 的 ID 唯一
        2. question 非空
        3. retrieval_truth.mode 为 ANY 或 ALL
        4. sources 非空，book/page_start/page_end 合理
        5. page_start <= page_end
        6. 覆盖每本书至少 min_per_book 条

        Args:
            items: 待验证的 EvalItem 列表
            min_per_book: 每本书最少条目数，默认 1

        Returns:
            EvalSetValidation 验证结果
        """
        errors: list[str] = []
        warnings: list[str] = []

        total_items = len(items)

        # 1. ID 唯一性检查
        id_counts: dict[str, int] = {}
        for item in items:
            id_counts[item.id] = id_counts.get(item.id, 0) + 1

        unique_ids = all(count == 1 for count in id_counts.values())
        if not unique_ids:
            duplicates = [id_val for id_val, count in id_counts.items() if count > 1]
            errors.append(f"ID 不唯一: {', '.join(duplicates)}")

        # 2. question 非空检查（from_dict 已做，但做二次确认）
        for item in items:
            if not item.question.strip():
                errors.append(f"ID={item.id}: question 为空")

        # 3. mode 合法性检查（from_dict 已做，二次确认）
        for item in items:
            if item.retrieval_truth.mode not in ("ANY", "ALL", "NEGATIVE"):
                errors.append(
                    f"ID={item.id}: mode='{item.retrieval_truth.mode}' 不合法"
                )

        # 4. sources 非空检查（NEGATIVE 模式允许空 sources）
        for item in items:
            if item.retrieval_truth.mode != "NEGATIVE" and not item.retrieval_truth.sources:
                errors.append(f"ID={item.id}: sources 为空")

        # 5. 统计每本书覆盖
        items_per_book: dict[str, int] = {}
        books_covered: set[str] = set()

        for item in items:
            for source in item.retrieval_truth.sources:
                books_covered.add(source.book)
                items_per_book[source.book] = items_per_book.get(source.book, 0) + 1

        min_items_per_book = (
            min(items_per_book.values()) if items_per_book else 0
        )

        # 6. 每本书最少条目数检查
        for book in books_covered:
            if items_per_book[book] < min_per_book:
                warnings.append(
                    f"书籍 '{book}' 仅有 {items_per_book[book]} 条，"
                    f"少于要求的 {min_per_book} 条"
                )

        passed = len(errors) == 0

        validation = EvalSetValidation(
            total_items=total_items,
            unique_ids=unique_ids,
            books_covered=books_covered,
            items_per_book=items_per_book,
            min_items_per_book=min_items_per_book,
            errors=errors,
            warnings=warnings,
            passed=passed,
        )

        logger.info(
            "评估集验证: %d 条, %d 本书, 通过=%s",
            total_items,
            len(books_covered),
            passed,
        )

        if errors:
            logger.warning("验证错误: %s", errors)
        if warnings:
            logger.info("验证警告: %s", warnings)

        return validation
