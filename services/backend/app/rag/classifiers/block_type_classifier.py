"""block_type LLM 分类器

对每个 child chunk 调 DashScope LLM（qwen-turbo）分类为
definition/property/example/exercise/explanation/unknown。
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

BLOCK_TYPES = frozenset({"definition", "property", "example", "exercise", "explanation", "unknown"})


class BlockTypeClassifier:
    """基于 LLM 的 block_type 分类器

    对 child chunk 文本进行批量分类，每 batch_size 条一组调用一次 LLM。
    不可识别的标签或调用失败均回退为 'unknown'。

    Args:
        api_key: DashScope API Key
        model: LLM 模型名称，默认 qwen-turbo
    """

    def __init__(self, api_key: str, model: str = "qwen-turbo") -> None:
        self._api_key = api_key
        self._model = model

    def classify_batch(self, texts: list[str], batch_size: int = 10) -> list[str]:
        """批量分类 chunk 文本的 block_type

        每 batch_size 条一组，调一次 LLM（把多条文本放在一个 prompt 里）。
        失败的条目标 'unknown'。

        Args:
            texts: 待分类文本列表
            batch_size: 每批数量，默认 10

        Returns:
            与 texts 等长的 block_type 列表
        """
        results: list[str] = ["unknown"] * len(texts)

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            try:
                batch_results = self._classify_single_batch(batch)
                for j, bt in enumerate(batch_results):
                    if bt in BLOCK_TYPES:
                        results[i + j] = bt
                    else:
                        results[i + j] = "unknown"
            except Exception:
                # 整批失败，保持 'unknown'
                logger.warning(
                    "block_type 分类批次失败 (index=%d, size=%d)，回退为 unknown",
                    i,
                    len(batch),
                )

        return results

    def _classify_single_batch(self, texts: list[str]) -> list[str]:
        """对一批文本做 LLM 分类，返回标签列表"""
        # 构建 prompt
        numbered = "\n".join(f"{i + 1}. {t[:300]}" for i, t in enumerate(texts))
        prompt = f"""请判断以下数学教材片段的内容类型，每条只返回一个词（definition/property/example/exercise/explanation）。

definition（定义）: 概念定义、术语解释
property（性质/定理/公式）: 定理、性质、公式推导
example（例题）: 例题及解答
exercise（练习/习题）: 练习题、习题（无解答过程）
explanation（解释/说明）: 背景介绍、方法说明、总结

片段：
{numbered}

请逐行返回类型（只返回类型词，用换行分隔）："""

        # 调 DashScope API（OpenAI 兼容接口）—— lazy import 避免循环依赖
        from openai import OpenAI

        client = OpenAI(
            api_key=self._api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
        response = client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=200,
        )

        content = response.choices[0].message.content.strip()
        lines = content.split("\n")

        # 清理每行（去掉编号、标点等）
        results: list[str] = []
        for line in lines:
            line = line.strip().lower()
            # 去掉可能的编号前缀如 "1. " "1) "
            line = re.sub(r"^\d+[\.\)]\s*", "", line).strip()
            if line in BLOCK_TYPES:
                results.append(line)
            else:
                results.append("unknown")

        return results
