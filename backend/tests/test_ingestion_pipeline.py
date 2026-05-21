"""入库管线编排测试

使用 mock 模拟 PDFReader, StructureParser, MathChunker, DashScopeEmbedding, ChromaDBStore。
不依赖真实 PDF 文件或 DashScope API。
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.ingestion.pipeline import IngestionPipeline, IngestionStats
from app.rag.models import Chunk, ChunkMetadata, SectionBoundary


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_pdf_reader():
    """Mock PDFReader"""
    reader = MagicMock()
    return reader


@pytest.fixture
def mock_structure_parser():
    """Mock StructureParser"""
    parser = MagicMock()
    return parser


@pytest.fixture
def mock_chunker():
    """Mock MathChunker"""
    chunker = MagicMock()
    return chunker


@pytest.fixture
def mock_embedding_service():
    """Mock DashScopeEmbedding"""
    service = MagicMock()
    # 默认返回 768 维向量
    service.embed.return_value = [[0.1] * 768 for _ in range(10)]
    return service


@pytest.fixture
def mock_vector_store():
    """Mock ChromaDBStore"""
    store = MagicMock()
    return store


@pytest.fixture
def raw_dir(tmp_path):
    """创建临时 raw_dir 目录"""
    raw = tmp_path / "raw"
    raw.mkdir()
    return str(raw)


def _make_chunk(book: str = "test_book", chunk_id: str = "id1") -> Chunk:
    """辅助：构造 Chunk"""
    return Chunk(
        chunk_id=chunk_id,
        text="测试文本内容",
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


def _make_page_result(page_number: int, content: str = "测试内容", from_cache: bool = False):
    """辅助：构造 PageResult mock"""
    pr = MagicMock()
    pr.page_number = page_number
    pr.content = content
    pr.from_cache = from_cache
    return pr


def _create_pdf_file(raw_dir: str, name: str = "测试书.pdf") -> str:
    """在 raw_dir 下创建空 PDF 文件"""
    path = os.path.join(raw_dir, name)
    with open(path, "w") as f:
        f.write("")
    return path


def _build_pipeline(
    mock_pdf_reader,
    mock_structure_parser,
    mock_chunker,
    mock_embedding_service,
    mock_vector_store,
    raw_dir,
) -> IngestionPipeline:
    """构建 IngestionPipeline"""
    return IngestionPipeline(
        pdf_reader=mock_pdf_reader,
        structure_parser=mock_structure_parser,
        chunker=mock_chunker,
        embedding_service=mock_embedding_service,
        vector_store=mock_vector_store,
        raw_dir=raw_dir,
    )


# ---------------------------------------------------------------------------
# 测试：全量入库
# ---------------------------------------------------------------------------


class TestFullIngestion:
    """全量入库测试"""

    def test_full_ingestion_all_books(
        self,
        mock_pdf_reader,
        mock_structure_parser,
        mock_chunker,
        mock_embedding_service,
        mock_vector_store,
        raw_dir,
    ):
        """全量入库多本书 → 所有书入库成功，统计正确"""
        # 准备 3 个 PDF 文件
        pdf1 = _create_pdf_file(raw_dir, "必修第一册.pdf")
        pdf2 = _create_pdf_file(raw_dir, "必修第二册.pdf")
        pdf3 = _create_pdf_file(raw_dir, "选修第一册.pdf")

        # Mock PDFReader：每本 2 页，每页有内容
        pages = [_make_page_result(1, "内容1", from_cache=True),
                 _make_page_result(2, "内容2", from_cache=False)]
        mock_pdf_reader.read_pdf.return_value = pages

        # Mock StructureParser
        mock_structure_parser.parse.return_value = [
            MagicMock(start_pos=0, end_pos=10, title="1.1 测试", level=2, page=1, section_index=0)
        ]

        # Mock Chunker
        chunks = [_make_chunk("必修第一册"), _make_chunk("必修第一册")]
        mock_chunker.chunk.return_value = chunks

        # Mock Embedding
        mock_embedding_service.embed.return_value = [[0.1] * 768, [0.1] * 768]

        pipeline = _build_pipeline(
            mock_pdf_reader, mock_structure_parser, mock_chunker,
            mock_embedding_service, mock_vector_store, raw_dir,
        )
        stats = pipeline.run()

        assert stats.total_books == 3
        assert stats.total_pages == 6  # 3 本 × 2 页
        assert stats.total_chunks == 6  # 3 本 × 2 chunks
        assert stats.ocr_cache_hits == 3  # 3 本 × 1 cached page
        assert stats.ocr_calls == 3  # 3 本 × 1 non-cached page
        assert len(stats.errors) == 0
        assert stats.duration_seconds > 0

        # 验证 delete 被调用 3 次（每本都先删旧数据）
        assert mock_vector_store.delete.call_count == 3

        # 验证 upsert 被调用 3 次
        assert mock_vector_store.upsert.call_count == 3

    def test_full_ingestion_empty_raw_dir(
        self,
        mock_pdf_reader,
        mock_structure_parser,
        mock_chunker,
        mock_embedding_service,
        mock_vector_store,
        raw_dir,
    ):
        """空 raw_dir → 无入库，无错误"""
        pipeline = _build_pipeline(
            mock_pdf_reader, mock_structure_parser, mock_chunker,
            mock_embedding_service, mock_vector_store, raw_dir,
        )
        stats = pipeline.run()

        assert stats.total_books == 0
        assert stats.total_pages == 0
        assert stats.total_chunks == 0
        assert len(stats.errors) == 0

        # 不应调用任何服务
        mock_pdf_reader.read_pdf.assert_not_called()
        mock_vector_store.upsert.assert_not_called()

    def test_full_ingestion_raw_dir_not_exists(
        self,
        mock_pdf_reader,
        mock_structure_parser,
        mock_chunker,
        mock_embedding_service,
        mock_vector_store,
        tmp_path,
    ):
        """raw_dir 不存在 → 无入库，无错误"""
        pipeline = _build_pipeline(
            mock_pdf_reader, mock_structure_parser, mock_chunker,
            mock_embedding_service, mock_vector_store,
            str(tmp_path / "nonexistent"),
        )
        stats = pipeline.run()

        assert stats.total_books == 0
        assert len(stats.errors) == 0


# ---------------------------------------------------------------------------
# 测试：指定书籍入库
# ---------------------------------------------------------------------------


class TestSingleBookIngestion:
    """指定书籍入库测试"""

    def test_single_book_ingestion(
        self,
        mock_pdf_reader,
        mock_structure_parser,
        mock_chunker,
        mock_embedding_service,
        mock_vector_store,
        raw_dir,
    ):
        """指定书籍入库 → 只入库该书"""
        _create_pdf_file(raw_dir, "必修第一册.pdf")
        _create_pdf_file(raw_dir, "必修第二册.pdf")

        pages = [_make_page_result(1, "内容1"), _make_page_result(2, "内容2")]
        mock_pdf_reader.read_pdf.return_value = pages

        mock_structure_parser.parse.return_value = []
        mock_chunker.chunk.return_value = [_make_chunk("必修第一册")]

        mock_embedding_service.embed.return_value = [[0.1] * 768]

        pipeline = _build_pipeline(
            mock_pdf_reader, mock_structure_parser, mock_chunker,
            mock_embedding_service, mock_vector_store, raw_dir,
        )
        stats = pipeline.run(book_name="必修第一册")

        assert stats.total_books == 1
        assert stats.total_pages == 2
        assert stats.total_chunks == 1

        # 只调用了一次 read_pdf
        mock_pdf_reader.read_pdf.assert_called_once()

    def test_single_book_not_found(
        self,
        mock_pdf_reader,
        mock_structure_parser,
        mock_chunker,
        mock_embedding_service,
        mock_vector_store,
        raw_dir,
    ):
        """指定书籍不存在 → 记录错误"""
        _create_pdf_file(raw_dir, "必修第一册.pdf")

        pipeline = _build_pipeline(
            mock_pdf_reader, mock_structure_parser, mock_chunker,
            mock_embedding_service, mock_vector_store, raw_dir,
        )
        stats = pipeline.run(book_name="不存在的书")

        assert stats.total_books == 0
        assert len(stats.errors) == 1
        assert "不存在的书" in stats.errors[0]


# ---------------------------------------------------------------------------
# 测试：幂等性
# ---------------------------------------------------------------------------


class TestIdempotency:
    """幂等性测试"""

    def test_idempotent_delete_before_upsert(
        self,
        mock_pdf_reader,
        mock_structure_parser,
        mock_chunker,
        mock_embedding_service,
        mock_vector_store,
        raw_dir,
    ):
        """入库前先 delete 旧数据 → 幂等"""
        _create_pdf_file(raw_dir, "必修第一册.pdf")

        pages = [_make_page_result(1, "内容")]
        mock_pdf_reader.read_pdf.return_value = pages

        mock_structure_parser.parse.return_value = []
        mock_chunker.chunk.return_value = [_make_chunk("必修第一册")]
        mock_embedding_service.embed.return_value = [[0.1] * 768]

        pipeline = _build_pipeline(
            mock_pdf_reader, mock_structure_parser, mock_chunker,
            mock_embedding_service, mock_vector_store, raw_dir,
        )

        # 第一次运行
        stats1 = pipeline.run()
        # 第二次运行
        stats2 = pipeline.run()

        # 两次结果一致
        assert stats1.total_books == stats2.total_books
        assert stats1.total_chunks == stats2.total_chunks

        # 每次运行都先 delete 再 upsert
        assert mock_vector_store.delete.call_count == 2
        assert mock_vector_store.upsert.call_count == 2

        # 验证 delete 参数
        mock_vector_store.delete.assert_called_with(where={"book": "必修第一册"})

    def test_repeat_run_same_chunk_count(
        self,
        mock_pdf_reader,
        mock_structure_parser,
        mock_chunker,
        mock_embedding_service,
        mock_vector_store,
        raw_dir,
    ):
        """重复运行 → chunks 数量不变"""
        _create_pdf_file(raw_dir, "必修第一册.pdf")

        pages = [_make_page_result(1, "内容"), _make_page_result(2, "内容")]
        mock_pdf_reader.read_pdf.return_value = pages

        chunks = [_make_chunk("必修第一册", f"id{i}") for i in range(5)]
        mock_structure_parser.parse.return_value = []
        mock_chunker.chunk.return_value = chunks
        mock_embedding_service.embed.return_value = [[0.1] * 768 for _ in range(5)]

        pipeline = _build_pipeline(
            mock_pdf_reader, mock_structure_parser, mock_chunker,
            mock_embedding_service, mock_vector_store, raw_dir,
        )

        stats1 = pipeline.run()
        stats2 = pipeline.run()

        assert stats1.total_chunks == stats2.total_chunks == 5


# ---------------------------------------------------------------------------
# 测试：OCR 缓存统计
# ---------------------------------------------------------------------------


class TestOCRCacheStats:
    """OCR 缓存统计测试"""

    def test_ocr_cache_hits_counted(
        self,
        mock_pdf_reader,
        mock_structure_parser,
        mock_chunker,
        mock_embedding_service,
        mock_vector_store,
        raw_dir,
    ):
        """OCR 缓存命中统计正确"""
        _create_pdf_file(raw_dir, "必修第一册.pdf")

        pages = [
            _make_page_result(1, "内容1", from_cache=True),
            _make_page_result(2, "内容2", from_cache=True),
            _make_page_result(3, "内容3", from_cache=False),
        ]
        mock_pdf_reader.read_pdf.return_value = pages

        mock_structure_parser.parse.return_value = []
        mock_chunker.chunk.return_value = [_make_chunk("必修第一册")]
        mock_embedding_service.embed.return_value = [[0.1] * 768]

        pipeline = _build_pipeline(
            mock_pdf_reader, mock_structure_parser, mock_chunker,
            mock_embedding_service, mock_vector_store, raw_dir,
        )
        stats = pipeline.run()

        assert stats.ocr_cache_hits == 2
        assert stats.ocr_calls == 1
        assert stats.total_pages == 3

    def test_all_pages_cached(
        self,
        mock_pdf_reader,
        mock_structure_parser,
        mock_chunker,
        mock_embedding_service,
        mock_vector_store,
        raw_dir,
    ):
        """全部缓存命中 → ocr_calls=0"""
        _create_pdf_file(raw_dir, "必修第一册.pdf")

        pages = [_make_page_result(i, f"内容{i}", from_cache=True) for i in range(1, 4)]
        mock_pdf_reader.read_pdf.return_value = pages

        mock_structure_parser.parse.return_value = []
        mock_chunker.chunk.return_value = [_make_chunk("必修第一册")]
        mock_embedding_service.embed.return_value = [[0.1] * 768]

        pipeline = _build_pipeline(
            mock_pdf_reader, mock_structure_parser, mock_chunker,
            mock_embedding_service, mock_vector_store, raw_dir,
        )
        stats = pipeline.run()

        assert stats.ocr_cache_hits == 3
        assert stats.ocr_calls == 0


# ---------------------------------------------------------------------------
# 测试：错误处理
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """错误处理测试"""

    def test_pdf_not_found(
        self,
        mock_pdf_reader,
        mock_structure_parser,
        mock_chunker,
        mock_embedding_service,
        mock_vector_store,
        raw_dir,
    ):
        """PDF 文件不存在 → 报错记录在 errors"""
        _create_pdf_file(raw_dir, "必修第一册.pdf")

        mock_pdf_reader.read_pdf.side_effect = FileNotFoundError("文件不存在")

        pipeline = _build_pipeline(
            mock_pdf_reader, mock_structure_parser, mock_chunker,
            mock_embedding_service, mock_vector_store, raw_dir,
        )
        stats = pipeline.run()

        assert stats.total_books == 0
        assert len(stats.errors) == 1
        assert "文件不存在" in stats.errors[0]

    def test_embedding_failure_no_crash(
        self,
        mock_pdf_reader,
        mock_structure_parser,
        mock_chunker,
        mock_embedding_service,
        mock_vector_store,
        raw_dir,
    ):
        """Embedding 失败 → 错误记录在 errors，不崩溃"""
        _create_pdf_file(raw_dir, "必修第一册.pdf")

        pages = [_make_page_result(1, "内容")]
        mock_pdf_reader.read_pdf.return_value = pages

        mock_structure_parser.parse.return_value = []
        mock_chunker.chunk.return_value = [_make_chunk("必修第一册")]

        mock_embedding_service.embed.side_effect = RuntimeError("API 限流")

        pipeline = _build_pipeline(
            mock_pdf_reader, mock_structure_parser, mock_chunker,
            mock_embedding_service, mock_vector_store, raw_dir,
        )
        stats = pipeline.run()

        assert stats.total_books == 0
        assert len(stats.errors) == 1
        assert "API 限流" in stats.errors[0]

    def test_one_book_failure_does_not_block_others(
        self,
        mock_pdf_reader,
        mock_structure_parser,
        mock_chunker,
        mock_embedding_service,
        mock_vector_store,
        raw_dir,
    ):
        """一本书失败不影响其他书"""
        _create_pdf_file(raw_dir, "必修第一册.pdf")
        _create_pdf_file(raw_dir, "必修第二册.pdf")

        # 第一本成功，第二本失败
        pages_ok = [_make_page_result(1, "内容")]
        pages_fail = MagicMock()
        pages_fail.side_effect = RuntimeError("OCR 失败")

        # read_pdf 依次返回不同结果
        call_count = [0]

        def read_pdf_side_effect(path):
            call_count[0] += 1
            if "第二册" in path:
                raise RuntimeError("OCR 失败")
            return pages_ok

        mock_pdf_reader.read_pdf.side_effect = read_pdf_side_effect

        mock_structure_parser.parse.return_value = []
        mock_chunker.chunk.return_value = [_make_chunk("必修第一册")]
        mock_embedding_service.embed.return_value = [[0.1] * 768]

        pipeline = _build_pipeline(
            mock_pdf_reader, mock_structure_parser, mock_chunker,
            mock_embedding_service, mock_vector_store, raw_dir,
        )
        stats = pipeline.run()

        assert stats.total_books == 1  # 第一本成功
        assert stats.total_chunks == 1
        assert len(stats.errors) == 1  # 第二本失败
        assert "OCR 失败" in stats.errors[0]

    def test_empty_text_no_chunks(
        self,
        mock_pdf_reader,
        mock_structure_parser,
        mock_chunker,
        mock_embedding_service,
        mock_vector_store,
        raw_dir,
    ):
        """PDF 内容为空 → chunks=0，不报错"""
        _create_pdf_file(raw_dir, "空白书.pdf")

        pages = [_make_page_result(1, ""), _make_page_result(2, "")]
        mock_pdf_reader.read_pdf.return_value = pages

        pipeline = _build_pipeline(
            mock_pdf_reader, mock_structure_parser, mock_chunker,
            mock_embedding_service, mock_vector_store, raw_dir,
        )
        stats = pipeline.run()

        assert stats.total_books == 1  # 书籍入库成功
        assert stats.total_pages == 2
        assert stats.total_chunks == 0  # 无内容无 chunks
        assert len(stats.errors) == 0

    def test_chunker_returns_empty(
        self,
        mock_pdf_reader,
        mock_structure_parser,
        mock_chunker,
        mock_embedding_service,
        mock_vector_store,
        raw_dir,
    ):
        """分块结果为空 → 不调用 embedding，不报错"""
        _create_pdf_file(raw_dir, "必修第一册.pdf")

        pages = [_make_page_result(1, "内容")]
        mock_pdf_reader.read_pdf.return_value = pages

        mock_structure_parser.parse.return_value = []
        mock_chunker.chunk.return_value = []  # 无 chunks

        pipeline = _build_pipeline(
            mock_pdf_reader, mock_structure_parser, mock_chunker,
            mock_embedding_service, mock_vector_store, raw_dir,
        )
        stats = pipeline.run()

        assert stats.total_books == 1
        assert stats.total_chunks == 0
        mock_embedding_service.embed.assert_not_called()
        mock_vector_store.upsert.assert_not_called()


# ---------------------------------------------------------------------------
# 测试：IngestionStats
# ---------------------------------------------------------------------------


class TestIngestionStats:
    """IngestionStats 数据类测试"""

    def test_default_values(self):
        """默认值正确"""
        stats = IngestionStats()
        assert stats.total_books == 0
        assert stats.total_pages == 0
        assert stats.total_chunks == 0
        assert stats.ocr_cache_hits == 0
        assert stats.ocr_calls == 0
        assert stats.errors == []
        assert stats.duration_seconds == 0.0

    def test_custom_values(self):
        """自定义值正确"""
        stats = IngestionStats(
            total_books=5,
            total_pages=1000,
            total_chunks=5000,
            ocr_cache_hits=800,
            ocr_calls=200,
            errors=["err1"],
            duration_seconds=120.5,
        )
        assert stats.total_books == 5
        assert stats.total_pages == 1000
        assert stats.total_chunks == 5000
        assert stats.ocr_cache_hits == 800
        assert stats.ocr_calls == 200
        assert stats.errors == ["err1"]
        assert stats.duration_seconds == 120.5


# ---------------------------------------------------------------------------
# 测试：_scan_pdfs
# ---------------------------------------------------------------------------


class TestScanPdfs:
    """PDF 扫描测试"""

    def test_scan_all_pdfs(
        self,
        mock_pdf_reader,
        mock_structure_parser,
        mock_chunker,
        mock_embedding_service,
        mock_vector_store,
        raw_dir,
    ):
        """扫描全部 PDF"""
        _create_pdf_file(raw_dir, "a.pdf")
        _create_pdf_file(raw_dir, "b.pdf")
        _create_pdf_file(raw_dir, "c.pdf")

        pipeline = _build_pipeline(
            mock_pdf_reader, mock_structure_parser, mock_chunker,
            mock_embedding_service, mock_vector_store, raw_dir,
        )
        pdfs = pipeline._scan_pdfs()

        assert len(pdfs) == 3

    def test_scan_specific_book(
        self,
        mock_pdf_reader,
        mock_structure_parser,
        mock_chunker,
        mock_embedding_service,
        mock_vector_store,
        raw_dir,
    ):
        """指定书名扫描"""
        _create_pdf_file(raw_dir, "必修第一册.pdf")
        _create_pdf_file(raw_dir, "必修第二册.pdf")

        pipeline = _build_pipeline(
            mock_pdf_reader, mock_structure_parser, mock_chunker,
            mock_embedding_service, mock_vector_store, raw_dir,
        )
        pdfs = pipeline._scan_pdfs(book_name="必修第一册")

        assert len(pdfs) == 1
        assert pdfs[0].endswith("必修第一册.pdf")

    def test_scan_nonexistent_book(
        self,
        mock_pdf_reader,
        mock_structure_parser,
        mock_chunker,
        mock_embedding_service,
        mock_vector_store,
        raw_dir,
    ):
        """指定不存在的书 → 返回空列表"""
        _create_pdf_file(raw_dir, "必修第一册.pdf")

        pipeline = _build_pipeline(
            mock_pdf_reader, mock_structure_parser, mock_chunker,
            mock_embedding_service, mock_vector_store, raw_dir,
        )
        pdfs = pipeline._scan_pdfs(book_name="不存在的书")

        assert len(pdfs) == 0

    def test_scan_ignores_non_pdf(
        self,
        mock_pdf_reader,
        mock_structure_parser,
        mock_chunker,
        mock_embedding_service,
        mock_vector_store,
        raw_dir,
    ):
        """扫描时忽略非 PDF 文件"""
        _create_pdf_file(raw_dir, "a.pdf")
        # 创建非 PDF 文件
        with open(os.path.join(raw_dir, "notes.txt"), "w") as f:
            f.write("notes")
        with open(os.path.join(raw_dir, "image.png"), "wb") as f:
            f.write(b"")

        pipeline = _build_pipeline(
            mock_pdf_reader, mock_structure_parser, mock_chunker,
            mock_embedding_service, mock_vector_store, raw_dir,
        )
        pdfs = pipeline._scan_pdfs()

        assert len(pdfs) == 1
