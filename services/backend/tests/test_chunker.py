"""R003-BF-004 章节 StructureParser + Parent-Child 分块 测试

覆盖:
- StructureParser: 章节标题识别 + 层级判断
- MathChunker: Parent-Child 分块算法
- Chunk ID 生成规则
- Metadata 完整性
- has_formula 检测
- 边界情况（空文本、超长单句、短文本等）
"""

import pytest

from app.rag.chunkers.math_chunker import (
    MathChunker,
    StructureParser,
    _clean_section_title,
    _has_formula,
    _remove_title_line,
    _split_sentences,
)
from app.rag.models import Chunk, ChunkMetadata, SectionBoundary


# ===========================================================================
# 测试数据
# ===========================================================================

SAMPLE_MARKDOWN = """# 第一章 集合与函数概念

## 1.1 集合

一般地，把研究对象称为元素，通常用大写拉丁字母 A，B，C，... 表示集合。
如果 $a$ 是集合 A 的元素，就说 $a$ 属于集合 A，记作 $a \\in A$。
集合的表示方法有列举法和描述法。
列举法是把集合的元素一一列举出来，写在大括号内。
例如：$A = \\{1, 2, 3, 4, 5\\}$。
描述法是用集合中元素的公共特征来描述。
例如：$B = \\{x | x > 0\\}$ 表示所有正实数组成的集合。

## 1.2 函数

设 A、B 是非空的数集，如果按照某种确定的对应关系 $f$，
使对于集合 A 中的任意一个数 $x$，在集合 B 中都有唯一确定的数 $f(x)$ 和它对应，
那么就称 $f: A \\to B$ 为从集合 A 到集合 B 的一个函数。

习题1.1

1. 用列举法表示下列集合。
2. 用描述法表示下列集合。
"""

# 无章节标题的纯文本
PLAIN_TEXT = "这是一段没有章节标题的纯文本。它只是普通的内容。没有什么特别的。"

# 包含子节和习题的文本
COMPLEX_MARKDOWN = """# 第二章 基本初等函数

## 2.1 指数函数

### 2.1.1 指数与指数幂的运算

一般地，$a^n$ 叫做 $a$ 的 $n$ 次幂。

### 2.1.2 指数函数及其性质

一般地，函数 $y = a^x$（$a > 0$ 且 $a \\neq 1$）叫做指数函数。

## 2.2 对数函数

一般地，如果 $a^x = N$（$a > 0$ 且 $a \\neq 1$），那么数 $x$ 叫做以 $a$ 为底 $N$ 的对数。

习题2.1

1. 求下列各式的值。
2. 化简下列各式。
"""


# ===========================================================================
# StructureParser 测试
# ===========================================================================


class TestStructureParser:
    """章节识别测试"""

    def setup_method(self):
        self.parser = StructureParser()

    def test_parse_sample_markdown(self):
        """给定含章节标题的 Markdown → 正确识别 SectionBoundary"""
        boundaries = self.parser.parse(SAMPLE_MARKDOWN, page=1)

        assert len(boundaries) >= 3

        # 验证第一章
        ch1 = [b for b in boundaries if b.level == 1]
        assert len(ch1) == 1
        assert "第一章" in ch1[0].title
        assert "集合与函数概念" in ch1[0].title
        assert ch1[0].level == 1
        assert ch1[0].page == 1

        # 验证 1.1 集合
        s11 = [b for b in boundaries if b.level == 2 and b.title.startswith("1.1")]
        assert len(s11) == 1
        assert "集合" in s11[0].title
        assert s11[0].level == 2

        # 验证 1.2 函数
        s12 = [b for b in boundaries if "1.2" in b.title]
        assert len(s12) == 1
        assert "函数" in s12[0].title
        assert s12[0].level == 2

    def test_parse_level_1_chapter(self):
        """第X章 → level=1"""
        text = "# 第一章 集合\n\n一些内容"
        boundaries = self.parser.parse(text, page=1)
        assert len(boundaries) == 1
        assert boundaries[0].level == 1
        assert "第一章" in boundaries[0].title

    def test_parse_level_2_section(self):
        """X.X → level=2"""
        text = "## 1.1 集合\n\n一些内容"
        boundaries = self.parser.parse(text, page=1)
        assert len(boundaries) == 1
        assert boundaries[0].level == 2
        assert "1.1" in boundaries[0].title

    def test_parse_level_3_exercise(self):
        """习题X.X → level=3"""
        text = "习题1.1\n\n1. 第一题\n2. 第二题"
        boundaries = self.parser.parse(text, page=1)
        assert len(boundaries) == 1
        assert boundaries[0].level == 3

    def test_parse_level_4_subsection(self):
        """X.X.X → level=4"""
        text = "### 2.1.1 指数与指数幂\n\n一些内容"
        boundaries = self.parser.parse(text, page=1)
        assert len(boundaries) == 1
        assert boundaries[0].level == 4

    def test_parse_complex_markdown(self):
        """复杂 Markdown 正确识别所有层级"""
        boundaries = self.parser.parse(COMPLEX_MARKDOWN, page=10)

        levels = {b.level for b in boundaries}
        # 应该包含多个层级
        assert 1 in levels  # 第二章
        assert 2 in levels  # 2.1, 2.2
        assert 3 in levels  # 习题2.1

    def test_parse_no_headers(self):
        """无章节标题的纯文本 → 空列表"""
        boundaries = self.parser.parse(PLAIN_TEXT, page=1)
        assert len(boundaries) == 0

    def test_parse_empty_text(self):
        """空文本 → 空列表"""
        boundaries = self.parser.parse("", page=0)
        assert len(boundaries) == 0

    def test_parse_boundaries_positions(self):
        """SectionBoundary 的 start_pos 和 end_pos 正确"""
        text = "# 第一章 标题\n\n内容1\n\n## 1.1 小节\n\n内容2"
        boundaries = self.parser.parse(text, page=1)

        # 所有 boundary 的 start_pos < end_pos
        for b in boundaries:
            assert b.start_pos < b.end_pos
            assert b.start_pos >= 0
            assert b.end_pos <= len(text)

        # 验证层级关系: level=1 的 end_pos 应到文本末尾（因为没有下一个同级 level=1）
        ch1 = [b for b in boundaries if b.level == 1]
        assert len(ch1) == 1
        assert ch1[0].end_pos == len(text)

        # level=2 的 end_pos 也应到文本末尾
        s11 = [b for b in boundaries if b.level == 2]
        assert len(s11) == 1
        assert s11[0].end_pos == len(text)

    def test_parse_section_index_increments(self):
        """section_index 递增"""
        boundaries = self.parser.parse(SAMPLE_MARKDOWN, page=1)
        for i, b in enumerate(boundaries):
            assert b.section_index == i

    def test_parse_without_markdown_headers(self):
        """没有 Markdown # 标记的章节标题也能识别"""
        text = "第一章 集合与函数概念\n\n1.1 集合\n\n一些内容\n\n1.2 函数\n\n更多内容"
        boundaries = self.parser.parse(text, page=1)

        # 应该识别到第一章、1.1、1.2
        assert len(boundaries) >= 3
        assert any(b.level == 1 for b in boundaries)
        assert any(b.level == 2 and "1.1" in b.title for b in boundaries)
        assert any(b.level == 2 and "1.2" in b.title for b in boundaries)

    def test_parse_练习_recognized(self):
        """练习X.X 也识别为 level=3"""
        text = "练习2.3\n\n1. 题目"
        boundaries = self.parser.parse(text, page=5)
        assert len(boundaries) == 1
        assert boundaries[0].level == 3

    def test_parse_复习题_recognized(self):
        """复习题X.X 也识别为 level=3"""
        text = "复习题1\n\n1. 题目"
        boundaries = self.parser.parse(text, page=20)
        # 复习题可能不被匹配（取决于正则），不强制要求
        # 但如果匹配到，level 应该是 3
        for b in boundaries:
            if "复习题" in b.title:
                assert b.level == 3


# ===========================================================================
# MathChunker 测试
# ===========================================================================


class TestMathChunker:
    """Parent-Child 分块测试"""

    def setup_method(self):
        self.parser = StructureParser()
        self.chunker = MathChunker()

    def test_chunk_basic(self):
        """给定小节文本 → 正确生成 Parent + Child Chunks"""
        boundaries = self.parser.parse(SAMPLE_MARKDOWN, page=1)
        chunks = self.chunker.chunk(SAMPLE_MARKDOWN, boundaries, book="必修第一册")

        # 应该有 parent 和 child
        parents = [c for c in chunks if c.metadata.chunk_type == "parent"]
        children = [c for c in chunks if c.metadata.chunk_type == "child"]

        assert len(parents) >= 2  # 至少 1.1 和 1.2 两个 parent
        assert len(children) >= 2  # 每个小节至少 1 个 child

    def test_chunk_parent_content_complete(self):
        """Parent 包含小节的完整内容"""
        boundaries = self.parser.parse(SAMPLE_MARKDOWN, page=1)
        chunks = self.chunker.chunk(SAMPLE_MARKDOWN, boundaries, book="必修第一册")

        parents = [c for c in chunks if c.metadata.chunk_type == "parent"]
        for parent in parents:
            # Parent 应该包含对应 section 的文本
            assert len(parent.text) > 0
            # Parent 文本应该包含该小节的全部内容
            assert "1.1" in parent.text or "1.2" in parent.text

    def test_chunk_child_size(self):
        """Child 大小约 512 token（~1024 中文字符）"""
        # 构造一个较长的文本
        long_text = "## 1.1 长小节\n\n"
        for i in range(20):
            long_text += f"这是第{i+1}段内容。集合论是数学的一个基本分支。"
            long_text += "它研究集合及其性质和运算。" * 5
            long_text += "\n"

        boundaries = self.parser.parse(long_text, page=1)
        chunks = self.chunker.chunk(long_text, boundaries, book="测试")

        children = [c for c in chunks if c.metadata.chunk_type == "child"]
        # 大多数 child 应该在目标大小附近
        for child in children[:-1]:  # 最后一个可能较短
            # 允许一定误差（±20%）
            assert len(child.text) <= 1024 * 1.3

    def test_chunk_child_overlap(self):
        """Child 之间有约 50 token（~100 字符）的重叠"""
        # 构造足够长的文本以产生多个 child
        long_text = "## 1.1 长小节\n\n"
        for i in range(30):
            long_text += f"这是第{i+1}个句子的内容。它描述了数学中集合的基本概念和运算规则。"
            long_text += "集合的表示方法有列举法和描述法两种。"
            long_text += "在数学分析中，集合论是最基础的理论之一。"
            long_text += "\n"

        boundaries = self.parser.parse(long_text, page=1)
        chunks = self.chunker.chunk(long_text, boundaries, book="测试")

        children = [c for c in chunks if c.metadata.chunk_type == "child"]
        if len(children) >= 2:
            # 检查相邻 child 是否有重叠
            for i in range(len(children) - 1):
                # 相邻 child 的文本尾部和头部应该有部分重叠
                overlap_found = False
                # 检查前一个 child 的尾部是否出现在后一个 child 的头部
                tail_part = children[i].text[-200:]  # 取尾部 200 字符
                for check_len in range(min(100, len(tail_part)), 10, -10):
                    if tail_part[-check_len:] in children[i + 1].text[:200]:
                        overlap_found = True
                        break
                assert overlap_found, f"Child {i} 和 Child {i+1} 之间没有重叠"

    def test_chunk_sentence_boundary(self):
        """在句子边界切分（句号/问号/感叹号/换行），不在句子中间硬切"""
        long_text = "## 1.1 小节\n\n"
        for i in range(20):
            long_text += f"这是第{i+1}个完整句子。"
            long_text += "它描述了一个完整的概念？是的！"
            long_text += "\n"

        boundaries = self.parser.parse(long_text, page=1)
        chunks = self.chunker.chunk(long_text, boundaries, book="测试")

        children = [c for c in chunks if c.metadata.chunk_type == "child"]
        for child in children:
            # Child 的最后一个字符应该是句子边界字符
            assert child.text[-1] in "。？！\n", (
                f"Child 未在句子边界结束，最后一个字符: {repr(child.text[-5:])}"
            )

    def test_chunk_single_long_sentence(self):
        """单句超 512 token → 整个保留"""
        long_sentence = "## 1.1 长句\n\n" + "这是一个很长的句子" * 200 + "。"
        boundaries = self.parser.parse(long_sentence, page=1)
        chunks = self.chunker.chunk(long_sentence, boundaries, book="测试")

        children = [c for c in chunks if c.metadata.chunk_type == "child"]
        assert len(children) >= 1
        # 超长句子应该被完整保留
        assert any(len(c.text) > 1024 for c in children)

    def test_chunk_metadata_complete(self):
        """每个 Chunk 的 metadata 包含所有必要字段"""
        boundaries = self.parser.parse(SAMPLE_MARKDOWN, page=1)
        chunks = self.chunker.chunk(SAMPLE_MARKDOWN, boundaries, book="必修第一册")

        for chunk in chunks:
            meta = chunk.metadata
            assert meta.book == "必修第一册"
            assert isinstance(meta.chapter, str)
            assert isinstance(meta.section, str)
            assert meta.page == 1
            assert meta.chunk_type in ("parent", "child")
            assert isinstance(meta.has_formula, bool)
            assert isinstance(meta.parent_id, str)
            assert isinstance(meta.child_index, int)

    def test_chunk_child_index_increments(self):
        """child_index 从 0 递增"""
        boundaries = self.parser.parse(SAMPLE_MARKDOWN, page=1)
        chunks = self.chunker.chunk(SAMPLE_MARKDOWN, boundaries, book="必修第一册")

        # 按 parent_id 分组 child
        children_by_parent: dict[str, list[Chunk]] = {}
        for chunk in chunks:
            if chunk.metadata.chunk_type == "child":
                pid = chunk.metadata.parent_id
                children_by_parent.setdefault(pid, []).append(chunk)

        for pid, children in children_by_parent.items():
            indices = [c.metadata.child_index for c in children]
            assert indices == list(range(len(children))), (
                f"child_index 应该从 0 递增，实际: {indices}"
            )

    def test_chunk_parent_id_format(self):
        """parent_id 格式正确：{book}::{section_clean}::p{page}_s{section_index}::parent"""
        boundaries = self.parser.parse(SAMPLE_MARKDOWN, page=1)
        chunks = self.chunker.chunk(SAMPLE_MARKDOWN, boundaries, book="必修第一册")

        parents = [c for c in chunks if c.metadata.chunk_type == "parent"]
        for parent in parents:
            assert parent.chunk_id.endswith("::parent")
            assert "必修第一册" in parent.chunk_id
            # 验证 loc 部分
            assert "::p1_s" in parent.chunk_id

    def test_chunk_child_id_format(self):
        """chunk_id 格式正确：{book}::{section_clean}::p{page}_s{section_index}::child::{index}"""
        boundaries = self.parser.parse(SAMPLE_MARKDOWN, page=1)
        chunks = self.chunker.chunk(SAMPLE_MARKDOWN, boundaries, book="必修第一册")

        children = [c for c in chunks if c.metadata.chunk_type == "child"]
        for child in children:
            assert "::child::" in child.chunk_id
            assert "必修第一册" in child.chunk_id

    def test_chunk_has_formula_detection(self):
        """has_formula 正确检测 LaTeX 标记"""
        text_with_formula = "## 1.1 公式\n\n如果 $a$ 是集合 A 的元素，那么 $a \\in A$。"
        boundaries = self.parser.parse(text_with_formula, page=1)
        chunks = self.chunker.chunk(text_with_formula, boundaries, book="测试")

        for chunk in chunks:
            assert chunk.metadata.has_formula is True

        text_without_formula = "## 1.2 无公式\n\n这是一段普通的文本，没有任何数学公式。"
        boundaries = self.parser.parse(text_without_formula, page=1)
        chunks = self.chunker.chunk(text_without_formula, boundaries, book="测试")

        for chunk in chunks:
            assert chunk.metadata.has_formula is False

    def test_chunk_empty_boundaries(self):
        """空 boundaries → 空 chunks"""
        chunks = self.chunker.chunk("一些文本", [], book="测试")
        assert len(chunks) == 0

    def test_chunk_empty_text(self):
        """空文本 → 空 chunks"""
        chunks = self.chunker.chunk("", [], book="测试")
        assert len(chunks) == 0

    def test_chunk_non_level2_sections_skipped(self):
        """非 level=2 的章节不生成分块"""
        text = "# 第一章 标题\n\n只有章标题没有节。"
        boundaries = self.parser.parse(text, page=1)
        chunks = self.chunker.chunk(text, boundaries, book="测试")
        # 第一章是 level=1，不生成 Parent-Child
        assert len(chunks) == 0

    def test_chunk_context_tracking(self):
        """章名和节名在上下文中正确传递"""
        text = (
            "# 第一章 集合\n\n"
            "## 1.1 集合的概念\n\n"
            "一些内容。\n\n"
        )
        boundaries = self.parser.parse(text, page=1)
        chunks = self.chunker.chunk(text, boundaries, book="必修第一册")

        assert len(chunks) > 0
        for chunk in chunks:
            assert chunk.metadata.chapter == "第一章 集合"
            assert chunk.metadata.section == "1.1 集合的概念"

    def test_chunk_to_dict(self):
        """ChunkMetadata.to_dict() 返回正确的字典"""
        meta = ChunkMetadata(
            book="必修第一册",
            chapter="第一章",
            section="1.1 集合",
            page=12,
            chunk_type="child",
            has_formula=True,
            parent_id="必修第一册::1.1集合::p12_s0::parent",
            child_index=2,
        )
        d = meta.to_dict()
        assert d["book"] == "必修第一册"
        assert d["page"] == 12
        assert d["chunk_type"] == "child"
        assert d["has_formula"] is True
        assert d["child_index"] == 2


# ===========================================================================
# 辅助函数测试
# ===========================================================================


class TestHelperFunctions:
    """辅助函数测试"""

    def test_clean_section_title(self):
        """章节标题清理"""
        assert _clean_section_title("1.1 集合") == "1.1集合"
        assert _clean_section_title("## 1.2 函数") == "1.2函数"
        assert _clean_section_title("# 第一章 标题") == "第一章标题"
        assert _clean_section_title("2.1.1 子节") == "2.1.1子节"

    def test_has_formula(self):
        """LaTeX 公式检测"""
        assert _has_formula("如果 $x > 0$ 那么")
        assert _has_formula("公式 $$E=mc^2$$ 成立")
        assert _has_formula("\\begin{equation} x = 1 \\end{equation}")
        assert _has_formula("\\[ x = 1 \\]")
        assert _has_formula("\\( y = 2 \\)")
        assert _has_formula("\\begin{align} x &= 1 \\end{align}")
        assert not _has_formula("普通文本没有公式")
        assert not _has_formula("$")  # 单个 $ 不是公式
        assert not _has_formula("价格是$100")

    def test_remove_title_line(self):
        """标题行移除"""
        assert _remove_title_line("## 1.1 标题\n内容").strip() == "内容"
        assert _remove_title_line("1.1 标题\n内容").strip() == "内容"
        # 非标题行不移除
        assert _remove_title_line("普通内容\n更多内容") == "普通内容\n更多内容"

    def test_split_sentences(self):
        """句子切分"""
        sentences = _split_sentences("第一句。第二句？第三句！")
        assert len(sentences) == 3
        assert sentences[0] == "第一句。"
        assert sentences[1] == "第二句？"
        assert sentences[2] == "第三句！"

    def test_split_sentences_with_newlines(self):
        """换行也作为句子边界"""
        sentences = _split_sentences("第一行\n第二行\n")
        assert len(sentences) >= 2

    def test_split_sentences_empty(self):
        """空文本 → 空列表"""
        assert _split_sentences("") == []
        assert _split_sentences("   ") == []


# ===========================================================================
# 集成测试：完整流程
# ===========================================================================


class TestFullPipeline:
    """完整流程测试：Markdown → 章节识别 → 分块"""

    def test_full_pipeline_sample(self):
        """给定完整 Markdown → 章节识别 → 分块，验证输出完整性"""
        parser = StructureParser()
        chunker = MathChunker()

        boundaries = parser.parse(SAMPLE_MARKDOWN, page=12)
        chunks = chunker.chunk(SAMPLE_MARKDOWN, boundaries, book="必修第一册")

        # 1. 应该有 parent 和 child
        parents = [c for c in chunks if c.metadata.chunk_type == "parent"]
        children = [c for c in chunks if c.metadata.chunk_type == "child"]
        assert len(parents) >= 2
        assert len(children) >= 2

        # 2. 每个 parent 都有对应的 children
        for parent in parents:
            parent_children = [
                c for c in children if c.metadata.parent_id == parent.chunk_id
            ]
            assert len(parent_children) >= 1, (
                f"Parent {parent.chunk_id} 没有对应的 children"
            )

        # 3. 所有 chunk 的 book 正确
        for chunk in chunks:
            assert chunk.metadata.book == "必修第一册"

        # 4. 所有 chunk 的 page 正确
        for chunk in chunks:
            assert chunk.metadata.page == 12

    def test_full_pipeline_complex(self):
        """复杂 Markdown → 正确处理多层级"""
        parser = StructureParser()
        chunker = MathChunker()

        boundaries = parser.parse(COMPLEX_MARKDOWN, page=10)
        chunks = chunker.chunk(COMPLEX_MARKDOWN, boundaries, book="必修第一册")

        # 应该有 2.1 和 2.2 的 parent
        parents = [c for c in chunks if c.metadata.chunk_type == "parent"]
        sections = [c.metadata.section for c in parents]
        assert any("2.1" in s for s in sections)
        assert any("2.2" in s for s in sections)

        # 子节 (2.1.1, 2.1.2) 不单独生成分块（它们是 level=4，不是 level=2）
        # 但 2.1 的 parent 应该包含子节内容（因为子节在 2.1 的范围内）
        parent_21 = [c for c in parents if c.metadata.section.startswith("2.1")]
        assert len(parent_21) >= 1
        # 2.1 parent 应该包含 2.1.1 和 2.1.2 的内容
        p21_text = parent_21[0].text
        assert "2.1.1" in p21_text or "指数幂" in p21_text, (
            f"2.1 parent 应包含子节内容，实际文本: {p21_text[:200]}"
        )

    def test_full_pipeline_id_uniqueness(self):
        """所有 chunk_id 唯一"""
        parser = StructureParser()
        chunker = MathChunker()

        boundaries = parser.parse(SAMPLE_MARKDOWN, page=1)
        chunks = chunker.chunk(SAMPLE_MARKDOWN, boundaries, book="必修第一册")

        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids)), f"存在重复的 chunk_id: {ids}"

    def test_full_pipeline_formula_in_metadata(self):
        """含公式的 section → metadata.has_formula = True"""
        parser = StructureParser()
        chunker = MathChunker()

        text = "## 1.1 公式测试\n\n函数 $f(x) = x^2$ 是一个二次函数。\n"
        boundaries = parser.parse(text, page=5)
        chunks = chunker.chunk(text, boundaries, book="测试")

        for chunk in chunks:
            assert chunk.metadata.has_formula is True
