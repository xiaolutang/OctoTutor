"""PDF 读取模块

提供 PDF 全量 OCR + 缓存优先的读取能力。
"""

from app.rag.readers.pdf_reader import PDFReader, PageResult

__all__ = ["PDFReader", "PageResult"]
