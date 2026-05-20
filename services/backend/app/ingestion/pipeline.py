"""入库管线编排模块

编排 PDF → OCR → 分块 → Embedding → ChromaDB 全流程。
支持指定书籍或全量入库，幂等（先删旧数据再入库），输出 IngestionStats。

Usage:
    from app.ingestion.pipeline import IngestionPipeline, IngestionStats

    pipeline = IngestionPipeline(
        pdf_reader=reader,
        structure_parser=parser,
        chunker=chunker,
        embedding_service=embedding_svc,
        vector_store=store,
        raw_dir="data/raw",
    )
    stats = pipeline.run()          # 全量入库
    stats = pipeline.run("必修第一册")  # 指定书籍
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

from app.rag.chunkers.math_chunker import MathChunker, StructureParser
from app.rag.embeddings import DashScopeEmbedding
from app.rag.models import Chunk
from app.rag.readers.pdf_reader import PDFReader
from app.rag.vector_store import ChromaDBStore

logger = logging.getLogger(__name__)


@dataclass
class IngestionStats:
    """入库统计

    Attributes:
        total_books: 成功入库的书籍数量
        total_pages: 处理的总页数
        total_chunks: 入库的总 chunk 数量
        ocr_cache_hits: OCR 缓存命中次数
        ocr_calls: OCR 实际调用次数（非缓存）
        errors: 错误信息列表
        duration_seconds: 总耗时（秒）
    """

    total_books: int = 0
    total_pages: int = 0
    total_chunks: int = 0
    ocr_cache_hits: int = 0
    ocr_calls: int = 0
    errors: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0


@dataclass
class _BookIngestionResult:
    """单本书入库结果（内部使用）"""

    book_name: str
    pages: int = 0
    chunks: int = 0
    ocr_cache_hits: int = 0
    ocr_calls: int = 0
    error: str | None = None


class IngestionPipeline:
    """入库管线编排

    编排 PDFReader → StructureParser → MathChunker → EmbeddingService → ChromaDBStore 全流程。

    Args:
        pdf_reader: PDF 读取器
        structure_parser: 章节结构解析器
        chunker: 数学教材分块器
        embedding_service: Embedding 向量化服务
        vector_store: ChromaDB 向量存储
        raw_dir: PDF 原始文件目录，默认 "data/raw"
    """

    def __init__(
        self,
        pdf_reader: PDFReader,
        structure_parser: StructureParser,
        chunker: MathChunker,
        embedding_service: DashScopeEmbedding,
        vector_store: ChromaDBStore,
        raw_dir: str = "data/raw",
    ) -> None:
        self._pdf_reader = pdf_reader
        self._structure_parser = structure_parser
        self._chunker = chunker
        self._embedding_service = embedding_service
        self._vector_store = vector_store
        self._raw_dir = raw_dir

    def run(self, book_name: str | None = None) -> IngestionStats:
        """执行入库流程

        Args:
            book_name: 指定书名（不含 .pdf 后缀），None 表示全量入库

        Returns:
            IngestionStats 入库统计
        """
        start_time = time.time()

        # 1. 扫描 PDF 文件
        pdf_paths = self._scan_pdfs(book_name)

        if not pdf_paths:
            elapsed = time.time() - start_time
            stats = IngestionStats(duration_seconds=elapsed)
            if book_name is not None:
                msg = f"未找到书籍: {book_name}"
                logger.error(msg)
                stats.errors.append(msg)
            else:
                logger.info("raw_dir 下无 PDF 文件，跳过入库")
            return stats

        logger.info("开始入库，共 %d 本书", len(pdf_paths))

        # 2. 逐本处理
        stats = IngestionStats()
        for pdf_path in pdf_paths:
            result = self._ingest_book(pdf_path)
            if result.error is not None:
                stats.errors.append(result.error)
            else:
                stats.total_books += 1
            stats.total_pages += result.pages
            stats.total_chunks += result.chunks
            stats.ocr_cache_hits += result.ocr_cache_hits
            stats.ocr_calls += result.ocr_calls

        stats.duration_seconds = time.time() - start_time

        logger.info(
            "入库完成: %d 本书, %d 页, %d chunks, "
            "OCR 缓存命中 %d, OCR 调用 %d, 耗时 %.1fs",
            stats.total_books,
            stats.total_pages,
            stats.total_chunks,
            stats.ocr_cache_hits,
            stats.ocr_calls,
            stats.duration_seconds,
        )

        if stats.errors:
            logger.warning("入库错误: %s", stats.errors)

        return stats

    def _ingest_book(self, pdf_path: str) -> _BookIngestionResult:
        """处理单本书籍的入库

        Args:
            pdf_path: PDF 文件路径

        Returns:
            _BookIngestionResult
        """
        book_name = Path(pdf_path).stem
        result = _BookIngestionResult(book_name=book_name)
        logger.info("开始处理: %s", book_name)

        try:
            # 1. 幂等：删除旧数据
            self._vector_store.delete(where={"book": book_name})
            logger.debug("已删除旧数据: %s", book_name)

            # 2. PDFReader 读取全部页面
            page_results = self._pdf_reader.read_pdf(pdf_path)

            result.pages = len(page_results)
            for pr in page_results:
                if pr.from_cache:
                    result.ocr_cache_hits += 1
                else:
                    result.ocr_calls += 1

            # 3. 汇总所有页面 Markdown，同时构建页码偏移映射
            full_text = ""
            page_offsets: list[tuple[int, int, int]] = []  # (start, end, page_number)
            for pr in page_results:
                if not pr.content:
                    continue
                start = len(full_text)
                full_text += pr.content + "\n\n"
                end = len(full_text)
                page_offsets.append((start, end, pr.page_number))

            if not full_text.strip():
                logger.warning("书籍 %s 内容为空，跳过", book_name)
                return result

            # 4. StructureParser 识别章节
            boundaries = self._structure_parser.parse(full_text)

            # 5. MathChunker 分块
            chunks: list[Chunk] = self._chunker.chunk(
                full_text, boundaries, book=book_name,
                page_offsets=page_offsets,
            )

            if not chunks:
                logger.warning("书籍 %s 分块结果为空", book_name)
                return result

            result.chunks = len(chunks)

            # 6. EmbeddingService 批量 embed
            texts = [chunk.text for chunk in chunks]
            embeddings = self._embedding_service.embed(texts)

            # 7. ChromaDBStore.upsert
            self._vector_store.upsert(chunks, embeddings)

            logger.info(
                "完成: %s, %d 页, %d chunks",
                book_name,
                result.pages,
                result.chunks,
            )

        except FileNotFoundError as e:
            msg = f"PDF 文件不存在: {pdf_path} — {e}"
            logger.error(msg)
            result.error = msg
        except Exception as e:
            msg = f"入库失败: {book_name} — {e}"
            logger.error(msg, exc_info=True)
            result.error = msg

        return result

    def _scan_pdfs(self, book_name: str | None = None) -> list[str]:
        """扫描 PDF 文件

        Args:
            book_name: 指定书名（不含 .pdf），None 表示扫描全部

        Returns:
            PDF 文件路径列表
        """
        raw_dir = self._raw_dir

        if not os.path.isdir(raw_dir):
            logger.warning("raw_dir 不存在: %s", raw_dir)
            return []

        if book_name is not None:
            # 指定书籍
            pdf_path = os.path.join(raw_dir, f"{book_name}.pdf")
            if os.path.exists(pdf_path):
                return [pdf_path]
            return []

        # 全量扫描
        pdf_files: list[str] = []
        for entry in sorted(os.listdir(raw_dir)):
            if entry.lower().endswith(".pdf"):
                pdf_files.append(os.path.join(raw_dir, entry))
        return pdf_files
