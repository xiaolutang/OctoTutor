"""block_type_classifier 单元测试 + 入库管线集成测试

覆盖验收条件：
1. mock LLM → block_type_classifier 正确解析分类标签
2. LLM 返回无法识别的标签 → fallback 为 'unknown'
3. LLM 调用失败 → 标 'unknown'，不抛异常
4. IngestionPipeline 在 upsert 后调用 block_type 分类
5. batch 分组正确（每 10 条一组）
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.rag.classifiers.block_type_classifier import BlockTypeClassifier, BLOCK_TYPES
from app.rag.models import Chunk, ChunkMetadata


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_llm_response(content: str) -> MagicMock:
    """构造一个模拟的 OpenAI chat completion response"""
    message = MagicMock()
    message.content = content
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    return response


def _make_child_chunk(
    text: str = "测试内容",
    chunk_id: str = "child1",
    book: str = "test_book",
) -> Chunk:
    """构造一个 child 类型的 Chunk"""
    return Chunk(
        chunk_id=chunk_id,
        text=text,
        metadata=ChunkMetadata(
            book=book,
            chapter="第一章",
            section="1.1 测试",
            section_id=f"{book}::1.1",
            page=1,
            page_start=1,
            page_end=1,
            source_pages=[1],
            chunk_type="child",
            block_type="unknown",
            has_formula=False,
            parent_id="parent1",
            child_index=0,
        ),
    )


def _make_parent_chunk(
    chunk_id: str = "parent1",
    book: str = "test_book",
) -> Chunk:
    """构造一个 parent 类型的 Chunk"""
    return Chunk(
        chunk_id=chunk_id,
        text="parent 文本内容",
        metadata=ChunkMetadata(
            book=book,
            chapter="第一章",
            section="1.1 测试",
            section_id=f"{book}::1.1",
            page=1,
            page_start=1,
            page_end=1,
            source_pages=[1],
            chunk_type="parent",
            block_type="unknown",
            has_formula=False,
            parent_id=chunk_id,
            child_index=0,
        ),
    )


# ---------------------------------------------------------------------------
# 1. mock LLM → 正确解析分类标签
# ---------------------------------------------------------------------------


class TestCorrectClassification:
    """验收条件 1: mock LLM 正确解析分类标签"""

    @patch("app.rag.classifiers.block_type_classifier.BlockTypeClassifier._classify_single_batch")
    def test_single_batch_correct_labels(self, mock_batch):
        """单批次: 所有标签正确解析"""
        mock_batch.return_value = ["definition", "property", "example"]
        clf = BlockTypeClassifier(api_key="fake-key")

        results = clf.classify_batch(
            ["定义内容", "定理内容", "例题内容"],
            batch_size=10,
        )

        assert results == ["definition", "property", "example"]

    @patch("app.rag.classifiers.block_type_classifier.BlockTypeClassifier._classify_single_batch")
    def test_all_five_types(self, mock_batch):
        """五种合法标签均可识别"""
        mock_batch.return_value = [
            "definition",
            "property",
            "example",
            "exercise",
            "explanation",
        ]
        clf = BlockTypeClassifier(api_key="fake-key")

        results = clf.classify_batch(
            ["t1", "t2", "t3", "t4", "t5"],
            batch_size=10,
        )

        assert results == [
            "definition",
            "property",
            "example",
            "exercise",
            "explanation",
        ]

    def test_parse_llm_output_with_numbered_lines(self):
        """LLM 返回带编号的行 → 正确清理"""
        clf = BlockTypeClassifier(api_key="fake-key")

        with patch.object(clf, "_classify_single_batch") as mock_batch:
            # 模拟 LLM 返回 "1. definition\n2. property" 的解析
            mock_batch.return_value = ["definition", "property"]
            results = clf.classify_batch(["t1", "t2"])
            assert results == ["definition", "property"]


# ---------------------------------------------------------------------------
# 2. LLM 返回无法识别的标签 → fallback 为 'unknown'
# ---------------------------------------------------------------------------


class TestUnknownFallback:
    """验收条件 2: 无法识别的标签 → 'unknown'"""

    @patch("app.rag.classifiers.block_type_classifier.BlockTypeClassifier._classify_single_batch")
    def test_invalid_label_fallback(self, mock_batch):
        """LLM 返回无效标签 → 回退为 'unknown'"""
        mock_batch.return_value = ["definition", "invalid_label", "example"]
        clf = BlockTypeClassifier(api_key="fake-key")

        results = clf.classify_batch(["t1", "t2", "t3"])

        assert results == ["definition", "unknown", "example"]

    @patch("app.rag.classifiers.block_type_classifier.BlockTypeClassifier._classify_single_batch")
    def test_all_invalid_labels(self, mock_batch):
        """全部无效标签 → 全部 'unknown'"""
        mock_batch.return_value = ["foo", "bar", "baz"]
        clf = BlockTypeClassifier(api_key="fake-key")

        results = clf.classify_batch(["t1", "t2", "t3"])

        assert results == ["unknown", "unknown", "unknown"]

    @patch("app.rag.classifiers.block_type_classifier.BlockTypeClassifier._classify_single_batch")
    def test_mixed_valid_invalid(self, mock_batch):
        """有效与无效标签混合"""
        mock_batch.return_value = ["definition", "nonsense", "exercise", "garbage"]
        clf = BlockTypeClassifier(api_key="fake-key")

        results = clf.classify_batch(["t1", "t2", "t3", "t4"])

        assert results == ["definition", "unknown", "exercise", "unknown"]


# ---------------------------------------------------------------------------
# 3. LLM 调用失败 → 标 'unknown'，不抛异常
# ---------------------------------------------------------------------------


class TestLLMFailure:
    """验收条件 3: LLM 调用失败 → 'unknown'，不抛异常"""

    @patch("app.rag.classifiers.block_type_classifier.BlockTypeClassifier._classify_single_batch")
    def test_llm_exception_returns_unknown(self, mock_batch):
        """LLM 抛异常 → 全批 'unknown'"""
        mock_batch.side_effect = RuntimeError("API 超时")
        clf = BlockTypeClassifier(api_key="fake-key")

        results = clf.classify_batch(["t1", "t2", "t3"])

        assert results == ["unknown", "unknown", "unknown"]

    @patch("app.rag.classifiers.block_type_classifier.BlockTypeClassifier._classify_single_batch")
    def test_llm_connection_error(self, mock_batch):
        """网络错误 → 全批 'unknown'"""
        mock_batch.side_effect = ConnectionError("网络不通")
        clf = BlockTypeClassifier(api_key="fake-key")

        results = clf.classify_batch(["t1"])

        assert results == ["unknown"]

    @patch("app.rag.classifiers.block_type_classifier.BlockTypeClassifier._classify_single_batch")
    def test_partial_batch_failure(self, mock_batch):
        """多批次中部分失败 → 失败批次为 unknown，成功批次正常"""
        call_count = 0

        def side_effect(texts):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return ["definition", "property"]
            else:
                raise RuntimeError("第二批失败")

        mock_batch.side_effect = side_effect
        clf = BlockTypeClassifier(api_key="fake-key")

        # batch_size=2，4 条文本会分为 2 批
        results = clf.classify_batch(["t1", "t2", "t3", "t4"], batch_size=2)

        assert results == ["definition", "property", "unknown", "unknown"]


# ---------------------------------------------------------------------------
# 4. IngestionPipeline 在 upsert 后调用 block_type 分类
# ---------------------------------------------------------------------------


class TestPipelineIntegration:
    """验收条件 4: IngestionPipeline 集成 block_type 分类"""

    def test_pipeline_calls_classifier_on_child_chunks(self):
        """Pipeline 在 upsert 后对 child chunks 调用 block_type 分类"""
        from app.ingestion.pipeline import IngestionPipeline

        # 准备 mock 依赖
        mock_pdf_reader = MagicMock()
        mock_structure_parser = MagicMock()
        mock_chunker = MagicMock()
        mock_embedding_service = MagicMock()
        mock_vector_store = MagicMock()
        mock_classifier = MagicMock()

        # 构造 chunks：1 个 parent + 2 个 child
        parent = _make_parent_chunk("parent1")
        child1 = _make_child_chunk("child text 1", "child1")
        child2 = _make_child_chunk("child text 2", "child2")
        chunks = [parent, child1, child2]

        # Mock 返回值
        mock_pdf_reader.read_pdf.return_value = [
            MagicMock(page_number=1, content="内容", from_cache=True),
        ]
        mock_structure_parser.parse.return_value = []
        mock_chunker.chunk.return_value = chunks
        mock_embedding_service.embed.return_value = [[0.1] * 768 for _ in range(3)]
        mock_classifier.classify_batch.return_value = ["definition", "exercise"]

        # 创建临时 raw_dir
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as raw_dir:
            pdf_path = os.path.join(raw_dir, "测试书.pdf")
            with open(pdf_path, "w") as f:
                f.write("")

            pipeline = IngestionPipeline(
                pdf_reader=mock_pdf_reader,
                structure_parser=mock_structure_parser,
                chunker=mock_chunker,
                embedding_service=mock_embedding_service,
                vector_store=mock_vector_store,
                raw_dir=raw_dir,
                block_type_classifier=mock_classifier,
            )
            stats = pipeline.run("测试书")

        # 验证 classifier 被调用
        mock_classifier.classify_batch.assert_called_once_with(["child text 1", "child text 2"])

        # 验证 child chunks 的 block_type 被更新
        assert child1.metadata.block_type == "definition"
        assert child2.metadata.block_type == "exercise"

        # 验证 upsert 被调用 2 次：第一次全部 chunks，第二次只 child chunks
        assert mock_vector_store.upsert.call_count == 2

        # 验证统计正确
        assert stats.total_chunks == 3

    def test_pipeline_no_classifier_skips_classification(self):
        """Pipeline 不传 classifier → 跳过分类，行为与之前一致"""
        from app.ingestion.pipeline import IngestionPipeline

        mock_pdf_reader = MagicMock()
        mock_structure_parser = MagicMock()
        mock_chunker = MagicMock()
        mock_embedding_service = MagicMock()
        mock_vector_store = MagicMock()

        chunks = [_make_child_chunk("text", "c1")]

        mock_pdf_reader.read_pdf.return_value = [
            MagicMock(page_number=1, content="内容", from_cache=True),
        ]
        mock_structure_parser.parse.return_value = []
        mock_chunker.chunk.return_value = chunks
        mock_embedding_service.embed.return_value = [[0.1] * 768]

        import os
        import tempfile

        with tempfile.TemporaryDirectory() as raw_dir:
            pdf_path = os.path.join(raw_dir, "测试书.pdf")
            with open(pdf_path, "w") as f:
                f.write("")

            pipeline = IngestionPipeline(
                pdf_reader=mock_pdf_reader,
                structure_parser=mock_structure_parser,
                chunker=mock_chunker,
                embedding_service=mock_embedding_service,
                vector_store=mock_vector_store,
                raw_dir=raw_dir,
                block_type_classifier=None,
            )
            stats = pipeline.run("测试书")

        # block_type 保持默认 unknown
        assert chunks[0].metadata.block_type == "unknown"
        # upsert 只调用 1 次（无分类步骤的 re-upsert）
        assert mock_vector_store.upsert.call_count == 1

    def test_pipeline_classifier_failure_does_not_crash(self):
        """Pipeline 中 classifier 失败 → 不崩溃，child block_type 保持 unknown"""
        from app.ingestion.pipeline import IngestionPipeline

        mock_pdf_reader = MagicMock()
        mock_structure_parser = MagicMock()
        mock_chunker = MagicMock()
        mock_embedding_service = MagicMock()
        mock_vector_store = MagicMock()
        mock_classifier = MagicMock()

        chunks = [_make_child_chunk("text", "c1")]

        mock_pdf_reader.read_pdf.return_value = [
            MagicMock(page_number=1, content="内容", from_cache=True),
        ]
        mock_structure_parser.parse.return_value = []
        mock_chunker.chunk.return_value = chunks
        mock_embedding_service.embed.return_value = [[0.1] * 768]
        # classifier 内部会 catch 异常返回 unknown
        mock_classifier.classify_batch.return_value = ["unknown"]

        import os
        import tempfile

        with tempfile.TemporaryDirectory() as raw_dir:
            pdf_path = os.path.join(raw_dir, "测试书.pdf")
            with open(pdf_path, "w") as f:
                f.write("")

            pipeline = IngestionPipeline(
                pdf_reader=mock_pdf_reader,
                structure_parser=mock_structure_parser,
                chunker=mock_chunker,
                embedding_service=mock_embedding_service,
                vector_store=mock_vector_store,
                raw_dir=raw_dir,
                block_type_classifier=mock_classifier,
            )
            stats = pipeline.run("测试书")

        # 成功完成，无错误
        assert len(stats.errors) == 0
        assert chunks[0].metadata.block_type == "unknown"


# ---------------------------------------------------------------------------
# 5. batch 分组正确（每 10 条一组）
# ---------------------------------------------------------------------------


class TestBatchGrouping:
    """验收条件 5: batch 分组正确"""

    @patch("app.rag.classifiers.block_type_classifier.BlockTypeClassifier._classify_single_batch")
    def test_exactly_10_items(self, mock_batch):
        """恰好 10 条 → 1 个批次"""
        mock_batch.return_value = ["definition"] * 10
        clf = BlockTypeClassifier(api_key="fake-key")

        texts = [f"text{i}" for i in range(10)]
        results = clf.classify_batch(texts, batch_size=10)

        assert len(results) == 10
        assert all(r == "definition" for r in results)
        assert mock_batch.call_count == 1

    @patch("app.rag.classifiers.block_type_classifier.BlockTypeClassifier._classify_single_batch")
    def test_15_items_batch_size_10(self, mock_batch):
        """15 条 / batch_size=10 → 2 个批次 (10 + 5)"""
        mock_batch.side_effect = [
            ["definition"] * 10,
            ["property"] * 5,
        ]
        clf = BlockTypeClassifier(api_key="fake-key")

        texts = [f"text{i}" for i in range(15)]
        results = clf.classify_batch(texts, batch_size=10)

        assert len(results) == 15
        assert results[:10] == ["definition"] * 10
        assert results[10:] == ["property"] * 5
        assert mock_batch.call_count == 2

    @patch("app.rag.classifiers.block_type_classifier.BlockTypeClassifier._classify_single_batch")
    def test_25_items_batch_size_10(self, mock_batch):
        """25 条 / batch_size=10 → 3 个批次 (10 + 10 + 5)"""
        mock_batch.side_effect = [
            ["definition"] * 10,
            ["property"] * 10,
            ["example"] * 5,
        ]
        clf = BlockTypeClassifier(api_key="fake-key")

        texts = [f"text{i}" for i in range(25)]
        results = clf.classify_batch(texts, batch_size=10)

        assert len(results) == 25
        assert results[:10] == ["definition"] * 10
        assert results[10:20] == ["property"] * 10
        assert results[20:] == ["example"] * 5
        assert mock_batch.call_count == 3

    @patch("app.rag.classifiers.block_type_classifier.BlockTypeClassifier._classify_single_batch")
    def test_custom_batch_size(self, mock_batch):
        """自定义 batch_size=3，7 条 → 3 个批次 (3 + 3 + 1)"""
        mock_batch.side_effect = [
            ["definition", "property", "example"],
            ["exercise", "explanation", "definition"],
            ["property"],
        ]
        clf = BlockTypeClassifier(api_key="fake-key")

        texts = [f"text{i}" for i in range(7)]
        results = clf.classify_batch(texts, batch_size=3)

        assert len(results) == 7
        assert results == [
            "definition", "property", "example",
            "exercise", "explanation", "definition",
            "property",
        ]
        assert mock_batch.call_count == 3

    @patch("app.rag.classifiers.block_type_classifier.BlockTypeClassifier._classify_single_batch")
    def test_empty_list(self, mock_batch):
        """空列表 → 空结果，不调用 LLM"""
        clf = BlockTypeClassifier(api_key="fake-key")

        results = clf.classify_batch([], batch_size=10)

        assert results == []
        mock_batch.assert_not_called()

    @patch("app.rag.classifiers.block_type_classifier.BlockTypeClassifier._classify_single_batch")
    def test_single_item(self, mock_batch):
        """单条文本 → 1 个批次"""
        mock_batch.return_value = ["definition"]
        clf = BlockTypeClassifier(api_key="fake-key")

        results = clf.classify_batch(["单条文本"], batch_size=10)

        assert results == ["definition"]
        mock_batch.assert_called_once_with(["单条文本"])


# ---------------------------------------------------------------------------
# _classify_single_batch 解析测试
# ---------------------------------------------------------------------------


class TestClassifySingleBatchParsing:
    """测试 _classify_single_batch 的 LLM 输出解析

    使用 mock_openai fixture 注入假的 openai 模块，
    避免 openai 包未安装的问题。
    """

    @pytest.fixture(autouse=True)
    def mock_openai(self):
        """注入 mock openai 模块到 sys.modules"""
        import sys
        import types

        # 创建假的 openai 模块
        mock_module = types.ModuleType("openai")
        mock_module.OpenAI = MagicMock()
        # 保存原有模块（如果存在）
        original = sys.modules.get("openai")
        sys.modules["openai"] = mock_module
        yield mock_module
        # 恢复
        if original is not None:
            sys.modules["openai"] = original
        else:
            sys.modules.pop("openai", None)

    def _setup_mock_client(self, mock_module, response_content: str):
        """配置 mock OpenAI 客户端返回指定内容"""
        mock_client = MagicMock()
        mock_module.OpenAI.return_value = mock_client
        mock_response = _mock_llm_response(response_content)
        mock_client.chat.completions.create.return_value = mock_response

    def test_raw_llm_output_parsing(self, mock_openai):
        """直接测试 _classify_single_batch 对 LLM 返回内容的解析"""
        clf = BlockTypeClassifier(api_key="fake-key")
        self._setup_mock_client(mock_openai, "definition\nproperty\nexample")

        results = clf._classify_single_batch(["t1", "t2", "t3"])

        assert results == ["definition", "property", "example"]

    def test_raw_llm_output_with_numbered_lines(self, mock_openai):
        """LLM 返回带编号的行 → 正确清理编号前缀"""
        clf = BlockTypeClassifier(api_key="fake-key")
        self._setup_mock_client(mock_openai, "1. definition\n2. property\n3. example")

        results = clf._classify_single_batch(["t1", "t2", "t3"])

        assert results == ["definition", "property", "example"]

    def test_raw_llm_output_with_parenthesis_prefix(self, mock_openai):
        """LLM 返回 "1) definition" 格式 → 正确清理"""
        clf = BlockTypeClassifier(api_key="fake-key")
        self._setup_mock_client(mock_openai, "1) definition\n2) property")

        results = clf._classify_single_batch(["t1", "t2"])

        assert results == ["definition", "property"]

    def test_raw_llm_output_mixed_case(self, mock_openai):
        """LLM 返回大小写混合 → 正确转小写"""
        clf = BlockTypeClassifier(api_key="fake-key")
        self._setup_mock_client(mock_openai, "Definition\nPROPERTY\nExample")

        results = clf._classify_single_batch(["t1", "t2", "t3"])

        assert results == ["definition", "property", "example"]

    def test_raw_llm_output_with_invalid_lines(self, mock_openai):
        """LLM 返回中包含无法识别的行 → 回退为 unknown"""
        clf = BlockTypeClassifier(api_key="fake-key")
        self._setup_mock_client(mock_openai, "definition\n这是定义\nproperty")

        results = clf._classify_single_batch(["t1", "t2", "t3"])

        assert results == ["definition", "unknown", "property"]
