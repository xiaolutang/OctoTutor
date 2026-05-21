"""入库脚本 CLI 入口

Usage:
    python -m ingestion                        # 全量入库
    python -m ingestion --book 必修第一册        # 指定书籍入库
"""

from __future__ import annotations

import argparse
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def main() -> None:
    parser = argparse.ArgumentParser(description="OctoTutor 入库管线")
    parser.add_argument(
        "--book",
        type=str,
        default=None,
        help="指定书名（不含 .pdf 后缀），不指定则全量入库",
    )
    args = parser.parse_args()

    # 延迟导入，避免模块级副作用
    from app.config import settings
    from app.ingestion.pipeline import IngestionPipeline
    from app.rag.chunkers.math_chunker import MathChunker, StructureParser
    from app.rag.embeddings import DashScopeEmbedding
    from app.rag.readers.pdf_reader import PDFReader
    from app.rag.vector_store import ChromaDBStore

    # 构建依赖
    pdf_reader = PDFReader(
        parsed_dir=settings.data_parsed_dir,
        images_dir=settings.data_images_dir,
        api_key=settings.dashscope_api_key,
    )
    structure_parser = StructureParser()
    chunker = MathChunker()
    embedding_service = DashScopeEmbedding(
        api_key=settings.dashscope_api_key,
        model=settings.dashscope_embedding_model,
        dimension=settings.dashscope_embedding_dimension,
    )
    vector_store = ChromaDBStore(
        persist_directory=settings.chroma_persist_dir,
    )

    # Block type classifier（可选，需要 NewAPI Key）
    block_type_classifier = None
    if settings.newapi_api_key:
        from app.rag.classifiers.block_type_classifier import BlockTypeClassifier

        block_type_classifier = BlockTypeClassifier(
            api_key=settings.newapi_api_key,
            base_url=settings.newapi_base_url,
            model=settings.llm_model,
        )

    # 执行入库
    pipeline = IngestionPipeline(
        pdf_reader=pdf_reader,
        structure_parser=structure_parser,
        chunker=chunker,
        embedding_service=embedding_service,
        vector_store=vector_store,
        raw_dir=settings.data_raw_dir,
        block_type_classifier=block_type_classifier,
    )

    stats = pipeline.run(book_name=args.book)

    # 输出统计
    print("\n" + "=" * 50)
    print("入库统计")
    print("=" * 50)
    print(f"  书籍数量:   {stats.total_books}")
    print(f"  总页数:     {stats.total_pages}")
    print(f"  总 chunks:  {stats.total_chunks}")
    print(f"  OCR 缓存:   {stats.ocr_cache_hits}")
    print(f"  OCR 调用:   {stats.ocr_calls}")
    print(f"  耗时:       {stats.duration_seconds:.1f}s")
    if stats.errors:
        print(f"  错误:       {len(stats.errors)}")
        for err in stats.errors:
            print(f"    - {err}")
    print("=" * 50)

    if stats.errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
