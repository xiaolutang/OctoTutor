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

# 页眉过滤正则：匹配 "第X章 ... 数字" 格式的页眉（如 "第六章 平面向量及其应用 7"）
HEADER_PAGE_NOISE_PATTERN = re.compile(
    r"^第[一二三四五六七八九十百千\d]+章\s+.+\s+\d+$"
)

# OCR 噪声过滤规则
# 1. 目录条目：含 3 个以上连续省略号/点号/cdots（如 "10.1 随机事件与概率 …… 228"）
TOC_ENTRY_PATTERN = re.compile(r"(?:[\.…·]){3,}|\\cdots")
# 2. LaTeX 表格行：含 & 和 \\ 的数字行（如 "0.5 & -3.7 & 2.7 & 1.1 & ..."）
TABLE_ROW_PATTERN = re.compile(r"&.*\\\\")
# 3. 纯数字序列：标题全是数字、空格、点号、负号和分隔符（如 "5.1 24.5 6.4 7.5"）
PURE_NUMERIC_PATTERN = re.compile(r"^[\d\s\.\-&\\,]+$")

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

        # 过滤页眉和 OCR 噪声
        deduped = [
            m for m in deduped
            if (m[1] != 1 or not HEADER_PAGE_NOISE_PATTERN.match(m[2]))
            and not _is_ocr_noise(m[2])
        ]

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
        page_offsets: list[tuple[int, int, int]] | None = None,
    ) -> List[Chunk]:
        """对文本进行 Parent-Child 分块。

        Args:
            text: 完整 Markdown 文本
            boundaries: StructureParser 识别出的章节边界
            book: 书名
            page_offsets: 页码偏移映射 [(start, end, page_number), ...]

        Returns:
            包含 Parent 和 Child 的 Chunk 列表
        """
        if not boundaries:
            return []

        chunks: List[Chunk] = []

        # 跟踪当前上下文（章名、节名）
        current_chapter = ""
        current_section = ""

        # 把 boundaries 转为 list，方便索引查找下一个同级 boundary
        boundaries_list = list(boundaries)

        # 获取最后一页页码（用于最后一个 section 的 page_end 兜底）
        last_page = (
            page_offsets[-1][2] if page_offsets else 0
        )

        for i, boundary in enumerate(boundaries_list):
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

            # 根据 page_offsets 查找正确的页码
            page = _lookup_page(boundary.start_pos, page_offsets) if page_offsets else boundary.page

            # section_id
            section_id = _extract_section_id(book, boundary.title)

            # Parent page range: 找下一个 level <= 2 的 boundary
            page_end = page  # 默认值
            for j in range(i + 1, len(boundaries_list)):
                if boundaries_list[j].level <= 2:
                    next_page = (
                        _lookup_page(boundaries_list[j].start_pos, page_offsets)
                        if page_offsets
                        else boundaries_list[j].page
                    )
                    if page_offsets:
                        page_end = next_page - 1
                    else:
                        # 无 page_offsets 时，同一页内的 section 直接用 page 作为 page_end
                        page_end = page
                    break
            else:
                # 没找到下一个同级 boundary → 使用最后一页
                if page_offsets:
                    page_end = last_page

            source_pages = list(range(page, page_end + 1))

            # 生成 Chunk ID 的共用部分
            section_clean = _clean_section_title(boundary.title)
            loc = f"p{page}_s{boundary.section_index}"
            parent_id_str = f"{book}::{section_clean}::{loc}::parent"

            # Parent Chunk
            parent_chunk = Chunk(
                chunk_id=parent_id_str,
                text=section_text,
                metadata=ChunkMetadata(
                    book=book,
                    chapter=current_chapter,
                    section=boundary.title,
                    section_id=section_id,
                    page=page,
                    page_start=page,
                    page_end=page_end,
                    source_pages=source_pages,
                    chunk_type="parent",
                    block_type="unknown",
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

            # 计算 child_source 在 full_text 中的偏移
            # section_text = text[boundary.start_pos : boundary.end_pos].strip()
            # 去除标题行后，child_source 的偏移 = boundary.start_pos + (len(section_text) - len(child_source))
            # 但需要注意 strip() 可能去掉了尾部空白，所以用文本匹配更安全
            title_line_len = len(section_text) - len(child_source)
            child_source_offset_in_full = boundary.start_pos + title_line_len

            child_texts = self._split_into_children(child_source)

            # 累积位置：跟踪每个 child 在 child_source 中的偏移
            cumulative_pos = 0
            for idx, child_text in enumerate(child_texts):
                # child 在 full_text 中的绝对位置
                abs_start = child_source_offset_in_full + cumulative_pos
                abs_end = abs_start + len(child_text)

                # 查找 child 的页码范围
                if page_offsets:
                    child_page_start = _lookup_page(abs_start, page_offsets)
                    child_page_end = _lookup_page(abs_end - 1, page_offsets)
                else:
                    child_page_start = page
                    child_page_end = page
                child_source_pages = list(
                    range(child_page_start, child_page_end + 1)
                )

                # 累加位置（child_texts 中各子串在 child_source 中依次排列，
                # 但 overlap 导致它们在 child_source 中有重叠，
                # 所以不能简单用 len(child_text) 推进。
                # 我们用 child_source 中查找子串的方式来计算下一个起始位置）
                if idx < len(child_texts) - 1:
                    next_child_text = child_texts[idx + 1]
                    # 在 child_source 中从 cumulative_pos 开始查找下一个 child 的开头
                    # overlap 意味着下一个 child 的起始位置 < cumulative_pos + len(child_text)
                    # 搜索 next_child_text 的前几个字符在 child_source 中的位置
                    search_len = min(50, len(next_child_text))
                    search_snippet = next_child_text[:search_len]
                    found_pos = child_source.find(
                        search_snippet, cumulative_pos
                    )
                    if found_pos >= 0:
                        cumulative_pos = found_pos
                    else:
                        # fallback: 直接推进 len(child_text)
                        cumulative_pos += len(child_text)
                else:
                    cumulative_pos += len(child_text)

                child_id_str = (
                    f"{book}::{section_clean}::{loc}::child::{idx}"
                )
                chunks.append(
                    Chunk(
                        chunk_id=child_id_str,
                        text=child_text,
                        metadata=ChunkMetadata(
                            book=book,
                            chapter=current_chapter,
                            section=boundary.title,
                            section_id=section_id,
                            page=page,
                            page_start=child_page_start,
                            page_end=child_page_end,
                            source_pages=child_source_pages,
                            chunk_type="child",
                            block_type="unknown",
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


def _is_ocr_noise(title: str) -> bool:
    """判断标题是否为 OCR 噪声（目录条目、表格行、纯数字序列）"""
    if TOC_ENTRY_PATTERN.search(title):
        return True
    if TABLE_ROW_PATTERN.search(title):
        return True
    if PURE_NUMERIC_PATTERN.match(title):
        return True
    return False


def _lookup_page(
    pos: int,
    page_offsets: list[tuple[int, int, int]],
) -> int:
    """根据字符偏移位置查找对应的页码。

    Args:
        pos: 在 full_text 中的字符位置
        page_offsets: [(start, end, page_number), ...] 列表

    Returns:
        对应的页码，未找到时返回 0
    """
    for start, end, page_num in page_offsets:
        if start <= pos < end:
            return page_num
    # 如果超出最后一个 range，返回最后一页
    if page_offsets and pos >= page_offsets[-1][1]:
        return page_offsets[-1][2]
    return 0


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


# section_id 提取用正则：匹配开头的编号部分（如 "2.1"、"2.1.3"）
_SECTION_NUMBER_RE = re.compile(r"^(\d+\.\d+(?:\.\d+)?)\s+")


def _extract_section_id(book: str, title: str) -> str:
    """从 boundary.title 中提取编号，生成稳定的 section_id。

    规则:
    - 如果标题以编号开头（如 '2.1 等式性质与不等式性质'），返回 '{book}::{numbered_part}'
    - 如果标题无编号（如 '练习'），返回 '{book}::{section_clean}'

    Args:
        book: 书名
        title: 章节标题文本

    Returns:
        格式为 '{book}::{id}' 的 section_id
    """
    m = _SECTION_NUMBER_RE.match(title)
    if m:
        return f"{book}::{m.group(1)}"
    return f"{book}::{_clean_section_title(title)}"


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
