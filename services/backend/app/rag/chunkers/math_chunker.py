"""数学教材分块模块

实现 StructureParser（章节识别）和 MathChunker（Parent-Child 分块）。

Usage:
    from app.rag.chunkers.math_chunker import StructureParser, MathChunker

    # 1. 章节识别
    parser = StructureParser()
    boundaries = parser.parse(markdown_text, page=12)

    # 2. Parent-Child 分块
    chunker = MathChunker()
    chunks = chunker.chunk(markdown_text, boundaries, book="必修第一册")
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import List

from app.rag.models import Chunk, ChunkMetadata, SectionBoundary


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# 分块参数（字符数近似 token，中文 ~2 字符/token）
CHILD_TARGET_CHARS = 1024  # 512 token * 2
CHILD_OVERLAP_CHARS = 100  # 50 token * 2

# 句子边界字符
SENTENCE_BOUNDARY_PATTERN = re.compile(r"(?<=[。？！\n])")

# LaTeX 公式检测模式
LATEX_PATTERNS = [
    re.compile(r"\$[^$]+\$"),  # $...$
    re.compile(r"\$\$[^$]+\$\$"),  # $$...$$
    re.compile(r"\\begin\{equation\}"),  # \begin{equation}
    re.compile(r"\\begin\{align\}"),  # \begin{align}
    re.compile(r"\\\["),  # \[
    re.compile(r"\\\("),  # \(
]

# 章节正则匹配模式（按优先级排列，优先匹配更具体的模式）
SECTION_PATTERNS = [
    # level=4: X.X.X 子节（如 "1.1.1 子节标题"）
    (re.compile(r"^(#{1,4}\s*)?(\d+\.\d+\.\d+)\s+(.+)$", re.MULTILINE), 4),
    # level=3: 习题/练习（如 "习题1.1"）
    (re.compile(r"^(#{1,4}\s*)?(习题|练习|复习题)\s*(\d+\.\d+).*$", re.MULTILINE), 3),
    # level=2: X.X 节（如 "1.1 集合"）
    (re.compile(r"^(#{1,4}\s*)?(\d+\.\d+)\s+(.+)$", re.MULTILINE), 2),
    # level=1: 第X章（如 "第一章 集合与函数概念"）
    (
        re.compile(r"^(#{1,4}\s*)?第[一二三四五六七八九十百千\d]+章\s+(.+)$", re.MULTILINE),
        1,
    ),
]


# ---------------------------------------------------------------------------
# StructureParser: 章节识别
# ---------------------------------------------------------------------------


class StructureParser:
    """从 OCR 后的 Markdown 文本中识别章节标题和层级。

    使用正则表达式匹配以下格式：
    - 第X章 ... → level=1（章）
    - X.X ...   → level=2（节）
    - 习题X.X   → level=3（习题/练习）
    - X.X.X ... → level=4（子节）
    """

    def parse(self, text: str, page: int = 0) -> List[SectionBoundary]:
        """识别文本中的章节结构。

        Args:
            text: OCR 后的 Markdown 文本
            page: 当前页码

        Returns:
            按出现位置排序的 SectionBoundary 列表
        """
        raw_matches: list[tuple[int, int, str]] = []  # (start_pos, level, title)

        for pattern, level in SECTION_PATTERNS:
            for m in pattern.finditer(text):
                # 提取标题文本：去掉 Markdown 标题标记 # 和前后空白
                title = m.group(0).lstrip("#").strip()
                raw_matches.append((m.start(), level, title))

        # 去重：同一位置可能被多个模式匹配，保留优先级最高的
        # 按位置排序，相同位置取 level 最小的（最宽泛的匹配）
        raw_matches.sort(key=lambda x: (x[0], x[1]))

        deduped: list[tuple[int, int, str]] = []
        for match in raw_matches:
            if deduped and deduped[-1][0] == match[0]:
                # 同一位置，保留 level 更小的
                if match[1] < deduped[-1][1]:
                    deduped[-1] = match
            else:
                deduped.append(match)

        # 构造 SectionBoundary 列表
        boundaries: List[SectionBoundary] = []
        # 跟踪每页内的 section 计数
        section_counter = 0

        for i, (start_pos, level, title) in enumerate(deduped):
            # end_pos = 下一个同级或更高级 section 的 start_pos 或文本末尾
            # 子节（level > 当前 level）不应截断父节的范围
            end_pos = len(text)
            for j in range(i + 1, len(deduped)):
                next_level = deduped[j][1]
                if next_level <= level:
                    end_pos = deduped[j][0]
                    break

            boundaries.append(
                SectionBoundary(
                    title=title,
                    level=level,
                    start_pos=start_pos,
                    end_pos=end_pos,
                    page=page,
                    section_index=section_counter,
                )
            )
            section_counter += 1

        return boundaries


# ---------------------------------------------------------------------------
# MathChunker: Parent-Child 分块
# ---------------------------------------------------------------------------


class MathChunker:
    """Parent-Child 分块模块。

    Parent = level=2 小节为切割边界，保留完整内容。
    Child = 512 token（~1024 中文字符），50 token（~100 字符）重叠，
            在句子边界（句号/问号/感叹号/换行）切分。
    """

    def __init__(
        self,
        child_target_chars: int = CHILD_TARGET_CHARS,
        child_overlap_chars: int = CHILD_OVERLAP_CHARS,
    ):
        self.child_target_chars = child_target_chars
        self.child_overlap_chars = child_overlap_chars

    def chunk(
        self,
        text: str,
        boundaries: List[SectionBoundary],
        book: str = "",
    ) -> List[Chunk]:
        """对文本进行 Parent-Child 分块。

        Args:
            text: 完整 Markdown 文本
            boundaries: StructureParser 识别出的章节边界
            book: 书名

        Returns:
            包含 Parent 和 Child 的 Chunk 列表
        """
        if not boundaries:
            return []

        chunks: List[Chunk] = []

        # 跟踪当前上下文（章名、节名）
        current_chapter = ""
        current_section = ""

        for boundary in boundaries:
            # 更新上下文
            if boundary.level == 1:
                current_chapter = boundary.title
            elif boundary.level == 2:
                current_section = boundary.title
            elif boundary.level == 3:
                # 习题等也作为 section 级别处理
                pass
            elif boundary.level == 4:
                pass

            # 只对 level=2 的小节做 Parent-Child 分块
            if boundary.level != 2:
                continue

            # 提取该小节的文本内容
            section_text = text[boundary.start_pos : boundary.end_pos].strip()
            if not section_text:
                continue

            # 生成 Chunk ID 的共用部分
            section_clean = _clean_section_title(boundary.title)
            loc = f"p{boundary.page}_s{boundary.section_index}"
            parent_id_str = f"{book}::{section_clean}::{loc}::parent"

            # Parent Chunk
            parent_chunk = Chunk(
                chunk_id=parent_id_str,
                text=section_text,
                metadata=ChunkMetadata(
                    book=book,
                    chapter=current_chapter,
                    section=boundary.title,
                    page=boundary.page,
                    chunk_type="parent",
                    has_formula=_has_formula(section_text),
                    parent_id=parent_id_str,
                    child_index=0,
                ),
            )
            chunks.append(parent_chunk)

            # Child Chunks
            # 提取标题行之后的内容作为 Child 的文本源
            child_source = _remove_title_line(section_text)
            if not child_source.strip():
                continue

            child_texts = self._split_into_children(child_source)

            for idx, child_text in enumerate(child_texts):
                child_id_str = f"{book}::{section_clean}::{loc}::child::{idx}"
                chunks.append(
                    Chunk(
                        chunk_id=child_id_str,
                        text=child_text,
                        metadata=ChunkMetadata(
                            book=book,
                            chapter=current_chapter,
                            section=boundary.title,
                            page=boundary.page,
                            chunk_type="child",
                            has_formula=_has_formula(child_text),
                            parent_id=parent_id_str,
                            child_index=idx,
                        ),
                    )
                )

        return chunks

    def _split_into_children(self, text: str) -> List[str]:
        """将文本按句子边界切分为多个 Child。

        算法:
        1. 预处理: 按句子边界字符切分为 sentences[]
        2. 从头累积 sentences:
           - 累积字符数 < target → 继续添加
           - 累积字符数 >= target → 当前累积为一个 child
           - 回退 overlap 字符对应的 sentences 作为下一个 child 的起始
        3. 单个 sentence > target → 整个作为一个 child

        Args:
            text: 待切分文本（已去除标题行）

        Returns:
            Child 文本列表
        """
        if not text.strip():
            return []

        # 按句子边界切分
        sentences = _split_sentences(text)
        if not sentences:
            return [text] if text.strip() else []

        children: List[str] = []
        current_sentences: List[str] = []
        current_len = 0

        i = 0
        while i < len(sentences):
            sentence = sentences[i]
            sentence_len = len(sentence)

            # 单句超过 target → 整个作为一个 child
            if sentence_len >= self.child_target_chars and not current_sentences:
                children.append(sentence)
                i += 1
                continue

            # 尝试添加当前句子
            if current_len + sentence_len < self.child_target_chars or not current_sentences:
                current_sentences.append(sentence)
                current_len += sentence_len
                i += 1
            else:
                # 达到目标大小，输出当前 child
                child_text = "".join(current_sentences)
                children.append(child_text)

                # 回退 overlap 字符对应的句子
                overlap_sentences: List[str] = []
                overlap_len = 0
                # 从当前累积的句子末尾向前回退
                for s in reversed(current_sentences):
                    if overlap_len + len(s) <= self.child_overlap_chars:
                        overlap_sentences.insert(0, s)
                        overlap_len += len(s)
                    else:
                        break

                # 开始新的累积
                current_sentences = overlap_sentences
                current_len = overlap_len

        # 处理剩余内容
        if current_sentences:
            child_text = "".join(current_sentences)
            # 如果最后一个 child 与前一个重叠过多（内容基本相同），跳过
            if children and child_text == children[-1]:
                pass
            else:
                children.append(child_text)

        return children


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _clean_section_title(title: str) -> str:
    """清理章节标题用于 ID 生成。

    去除空格和标点，只保留字母、数字和中文。
    例如: "1.1 集合" → "1.1集合"
    """
    # 去除 Markdown 标题标记
    title = title.lstrip("#").strip()
    # 去除空格
    result = title.replace(" ", "")
    return result


def _has_formula(text: str) -> bool:
    """检测文本是否包含 LaTeX 公式标记。"""
    for pattern in LATEX_PATTERNS:
        if pattern.search(text):
            return True
    return False


def _remove_title_line(text: str) -> str:
    """去除文本的第一行（标题行），返回剩余内容。

    如果第一行是标题行（以 # 开头或以数字编号开头），则去除。
    否则返回原文。
    """
    lines = text.split("\n")
    if not lines:
        return text

    first_line = lines[0].strip()
    # 判断第一行是否是标题行
    if first_line.startswith("#") or re.match(
        r"^\d+\.\d+(\.\d+)?\s+", first_line
    ):
        return "\n".join(lines[1:])

    return text


def _split_sentences(text: str) -> List[str]:
    """按句子边界切分文本。

    在句号、问号、感叹号、换行处切分，保留分隔符在句子末尾。
    """
    if not text:
        return []

    # 使用正则在句子边界字符之后切分，保留分隔符
    parts = SENTENCE_BOUNDARY_PATTERN.split(text)
    # 过滤空字符串
    return [p for p in parts if p.strip()]
