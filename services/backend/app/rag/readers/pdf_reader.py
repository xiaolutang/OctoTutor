"""PDF 读取模块：全量 OCR + 缓存优先

实现 PDF 逐页处理流程：
1. 检查 data/parsed/{book}/page_{N}.md 是否存在
2. 有缓存 → 直接读取内容
3. 无缓存 → PyMuPDF 渲染 PNG → 调 DashScope 多模态 OCR → 存缓存到 parsed/
4. PNG 存入 data/images/{book}/page_{N}.png（仅无缓存时渲染）

数学教材全量 OCR，不做文本/图片通道判断。

Usage:
    from app.rag.readers.pdf_reader import PDFReader, PageResult

    reader = PDFReader(
        parsed_dir="data/parsed",
        images_dir="data/images",
        api_key="sk-xxx",
    )
    results = reader.read_pdf("data/raw/必修第一册.pdf")
    for page in results:
        print(f"Page {page.page_number}: cached={page.from_cache}")
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


@dataclass
class PageResult:
    """单页读取结果

    Attributes:
        page_number: 页码（1-based）
        content: OCR 后的 Markdown+LaTeX 内容
        from_cache: 是否来自缓存
        image_path: PNG 路径（仅无缓存时有值，有缓存时为 None）
    """

    page_number: int
    content: str
    from_cache: bool
    image_path: str | None = None


class PDFReader:
    """PDF 读取模块，支持全量 OCR + 缓存优先

    Args:
        parsed_dir: OCR 缓存根目录 (data/parsed)
        images_dir: 页面图片根目录 (data/images)
        api_key: DashScope API Key
        dpi: PNG 渲染 DPI，默认 150
        max_retries: OCR 失败重试次数，默认 2
    """

    def __init__(
        self,
        parsed_dir: str,
        images_dir: str,
        api_key: str,
        dpi: int = 150,
        max_retries: int = 2,
    ) -> None:
        self._parsed_dir = parsed_dir
        self._images_dir = images_dir
        self._api_key = api_key
        self._dpi = dpi
        self._max_retries = max_retries

    def read_pdf(self, pdf_path: str) -> list[PageResult]:
        """读取 PDF 全部页面

        Args:
            pdf_path: PDF 文件路径

        Returns:
            PageResult 列表，每页包含 page_number, content, from_cache

        Raises:
            FileNotFoundError: PDF 文件不存在
            RuntimeError: PDF 文件无法打开
        """
        pdf_path = str(pdf_path)
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF 文件不存在: {pdf_path}")

        book_name = self._extract_book_name(pdf_path)
        results: list[PageResult] = []

        try:
            doc = fitz.open(pdf_path)
        except Exception as e:
            raise RuntimeError(f"无法打开 PDF 文件: {pdf_path}, 错误: {e}") from e

        try:
            total_pages = len(doc)
            logger.info(
                "开始处理 PDF: %s, 共 %d 页", pdf_path, total_pages
            )

            for page_idx in range(total_pages):
                page_number = page_idx + 1  # 1-based
                result = self._process_page(doc, page_idx, page_number, book_name)
                results.append(result)

        finally:
            doc.close()

        logger.info(
            "PDF 处理完成: %s, %d 页, 缓存命中 %d 页",
            pdf_path,
            len(results),
            sum(1 for r in results if r.from_cache),
        )

        return results

    def read_page(self, pdf_path: str, page_number: int) -> PageResult:
        """读取单页

        Args:
            pdf_path: PDF 文件路径
            page_number: 页码（1-based）

        Returns:
            PageResult

        Raises:
            FileNotFoundError: PDF 文件不存在
            RuntimeError: PDF 文件无法打开
            ValueError: 页码超出范围
        """
        pdf_path = str(pdf_path)
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF 文件不存在: {pdf_path}")

        book_name = self._extract_book_name(pdf_path)

        try:
            doc = fitz.open(pdf_path)
        except Exception as e:
            raise RuntimeError(f"无法打开 PDF 文件: {pdf_path}, 错误: {e}") from e

        try:
            total_pages = len(doc)
            if page_number < 1 or page_number > total_pages:
                raise ValueError(
                    f"页码超出范围: {page_number}, 总页数: {total_pages}"
                )

            page_idx = page_number - 1  # 0-based
            return self._process_page(doc, page_idx, page_number, book_name)
        finally:
            doc.close()

    def _process_page(
        self,
        doc: fitz.Document,
        page_idx: int,
        page_number: int,
        book_name: str,
    ) -> PageResult:
        """处理单页：缓存优先，无缓存则渲染 PNG + OCR

        Args:
            doc: PyMuPDF Document 对象
            page_idx: 0-based 页面索引
            page_number: 1-based 页码
            book_name: 书名（用于缓存目录）

        Returns:
            PageResult
        """
        # 1. 检查缓存
        cached_content = self._check_cache(book_name, page_number)
        if cached_content is not None:
            logger.debug("页面 %d 有缓存，跳过 OCR", page_number)
            return PageResult(
                page_number=page_number,
                content=cached_content,
                from_cache=True,
                image_path=None,
            )

        # 2. 无缓存：渲染 PNG + OCR + 存缓存
        image_path: str | None = None
        content: str = ""

        # 2a. 渲染 PNG
        try:
            page = doc[page_idx]
            image_path = self._render_png(page, book_name, page_number)
        except Exception as e:
            logger.error(
                "页面 %d PNG 渲染失败，跳过该页: %s", page_number, str(e)
            )
            return PageResult(
                page_number=page_number,
                content="",
                from_cache=False,
                image_path=None,
            )

        # 2b. OCR
        try:
            content = self._ocr_with_retry(image_path)
        except Exception as e:
            logger.error(
                "页面 %d OCR 失败（已重试 %d 次），跳过该页: %s",
                page_number,
                self._max_retries,
                str(e),
            )
            return PageResult(
                page_number=page_number,
                content="",
                from_cache=False,
                image_path=image_path,
            )

        # 2c. 存缓存
        try:
            self._save_cache(book_name, page_number, content)
        except Exception as e:
            logger.warning(
                "页面 %d 缓存写入失败，不阻塞: %s", page_number, str(e)
            )

        return PageResult(
            page_number=page_number,
            content=content,
            from_cache=False,
            image_path=image_path,
        )

    def _check_cache(
        self, book_name: str, page_number: int
    ) -> str | None:
        """检查缓存文件是否存在

        Args:
            book_name: 书名
            page_number: 页码（1-based）

        Returns:
            缓存内容（str）或 None（无缓存）
        """
        cache_path = self._get_cache_path(book_name, page_number)
        if os.path.exists(cache_path):
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    content = f.read()
                if content.strip():
                    return content
            except Exception as e:
                logger.warning(
                    "读取缓存文件失败 %s: %s", cache_path, str(e)
                )
        return None

    def _render_png(
        self,
        page: fitz.Page,
        book_name: str,
        page_number: int,
    ) -> str:
        """PyMuPDF 渲染页面为 PNG

        Args:
            page: PyMuPDF Page 对象
            book_name: 书名
            page_number: 页码（1-based）

        Returns:
            PNG 文件路径
        """
        image_dir = os.path.join(self._images_dir, book_name)
        os.makedirs(image_dir, exist_ok=True)

        image_path = os.path.join(
            image_dir, f"page_{page_number}.png"
        )

        # 渲染参数
        zoom = self._dpi / 72.0  # 72 是 PDF 默认 DPI
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)

        pix.save(image_path)
        logger.debug("页面 %d PNG 渲染完成: %s", page_number, image_path)

        return image_path

    def _ocr_with_retry(self, image_path: str) -> str:
        """带重试的 OCR 调用

        Args:
            image_path: PNG 文件路径

        Returns:
            OCR 识别的文本内容

        Raises:
            RuntimeError: 所有重试均失败
        """
        last_error: Exception | None = None

        for attempt in range(self._max_retries + 1):
            try:
                return self._ocr_page(image_path)
            except Exception as e:
                last_error = e
                if attempt < self._max_retries:
                    wait_time = 2**attempt
                    logger.warning(
                        "OCR 调用失败 (attempt %d/%d), %ds 后重试: %s",
                        attempt + 1,
                        self._max_retries + 1,
                        wait_time,
                        str(e),
                    )
                    time.sleep(wait_time)
                else:
                    logger.error(
                        "OCR 调用失败, 已重试 %d 次: %s",
                        self._max_retries,
                        str(e),
                    )

        raise RuntimeError(
            f"OCR 调用失败, 已重试 {self._max_retries} 次: {last_error}"
        ) from last_error

    def _ocr_page(self, image_path: str) -> str:
        """调用 DashScope 多模态 OCR

        Args:
            image_path: PNG 文件路径

        Returns:
            OCR 识别的 Markdown+LaTeX 文本

        Raises:
            RuntimeError: API 调用失败
        """
        import base64

        from dashscope import MultiModalConversation

        # 读取图片并编码为 base64
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")

        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "image": f"data:image/png;base64,{image_data}"
                    },
                    {
                        "text": (
                            "请将这个数学教材页面完整识别为 Markdown 格式。"
                            "要求：\n"
                            "1. 所有数学公式用 LaTeX 格式表示，行内公式用 $...$，"
                            "独立公式用 $$...$$\n"
                            "2. 保持原始的标题层级结构\n"
                            "3. 保持段落结构\n"
                            "4. 表格用 Markdown 表格格式\n"
                            "5. 图片中的文字也要识别"
                        )
                    },
                ],
            }
        ]

        response = MultiModalConversation.call(
            model="qwen-vl-max",
            messages=messages,
            api_key=self._api_key,
        )

        if response.status_code != 200:
            raise RuntimeError(
                f"DashScope OCR API 错误: "
                f"status_code={response.status_code}, "
                f"code={response.code}, "
                f"message={response.message}"
            )

        # 提取 OCR 文本
        try:
            content = response.output["choices"][0]["message"]["content"]
            # 如果返回的是列表格式，取文本部分
            if isinstance(content, list):
                text_parts = []
                for item in content:
                    if isinstance(item, dict) and "text" in item:
                        text_parts.append(item["text"])
                content = "\n".join(text_parts)
            return content
        except (KeyError, IndexError) as e:
            raise RuntimeError(
                f"OCR 返回格式异常: {e}, response: {response.output}"
            ) from e

    def _save_cache(
        self, book_name: str, page_number: int, content: str
    ) -> None:
        """保存 OCR 结果到缓存文件

        Args:
            book_name: 书名
            page_number: 页码（1-based）
            content: OCR 内容
        """
        cache_path = self._get_cache_path(book_name, page_number)
        cache_dir = os.path.dirname(cache_path)
        os.makedirs(cache_dir, exist_ok=True)

        with open(cache_path, "w", encoding="utf-8") as f:
            f.write(content)

        logger.debug("页面 %d 缓存已保存: %s", page_number, cache_path)

    def _get_cache_path(self, book_name: str, page_number: int) -> str:
        """获取缓存文件路径

        Args:
            book_name: 书名
            page_number: 页码（1-based）

        Returns:
            缓存文件路径
        """
        return os.path.join(
            self._parsed_dir, book_name, f"page_{page_number}.md"
        )

    @staticmethod
    def _extract_book_name(pdf_path: str) -> str:
        """从 PDF 路径中提取书名（去除扩展名）

        Args:
            pdf_path: PDF 文件路径

        Returns:
            书名（不含 .pdf 后缀）
        """
        basename = os.path.basename(pdf_path)
        name, _ = os.path.splitext(basename)
        return name
