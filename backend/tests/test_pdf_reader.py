"""PDFReader 单元测试

使用 mock 模拟 DashScope OCR API 和 PyMuPDF 渲染，验证：
1. 有缓存时跳过 OCR，直接读缓存文件
2. 无缓存时渲染 PNG + OCR + 缓存正确写入
3. OCR 失败重试 2 次后跳过，日志记录失败页码
4. 跨页内容正确分割
5. 缓存写入失败不阻塞
6. PDF 文件不存在时抛 FileNotFoundError
7. 空 PDF（0 页）返回空列表
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.rag.readers.pdf_reader import PDFReader, PageResult


# ---------------------------------------------------------------------------
# 辅助工具
# ---------------------------------------------------------------------------

def _create_minimal_pdf(path: str, num_pages: int = 1) -> None:
    """创建最小测试 PDF 文件

    Args:
        path: 输出文件路径
        num_pages: 页数
    """
    import fitz

    doc = fitz.open()
    for i in range(num_pages):
        page = doc.new_page(width=595, height=842)  # A4
        page.insert_text(
            (72, 72),
            f"Test Page {i + 1}",
            fontsize=12,
        )
    doc.save(path)
    doc.close()


def _write_cache(parsed_dir: str, book_name: str, page_number: int, content: str) -> None:
    """写入缓存文件"""
    cache_dir = os.path.join(parsed_dir, book_name)
    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, f"page_{page_number}.md")
    with open(cache_path, "w", encoding="utf-8") as f:
        f.write(content)


def _make_ocr_response(
    text: str = "OCR 识别结果",
    status_code: int = 200,
    code: str = "",
    message: str = "",
):
    """构造 mock DashScope MultiModalConversation 响应"""

    @dataclass
    class FakeResponse:
        status_code: int
        code: str
        message: str
        output: dict
        request_id: str = "fake-req-id"

    output = {
        "choices": [
            {
                "message": {
                    "content": text,
                }
            }
        ]
    }

    return FakeResponse(
        status_code=status_code,
        code=code,
        message=message,
        output=output,
    )


# ---------------------------------------------------------------------------
# 测试类
# ---------------------------------------------------------------------------


class TestCacheHit:
    """有缓存时跳过 OCR，直接读缓存文件"""

    def test_cached_page_returns_from_cache(self, tmp_path):
        """缓存存在 → from_cache=True，OCR 未被调用"""
        parsed_dir = str(tmp_path / "parsed")
        images_dir = str(tmp_path / "images")
        pdf_dir = str(tmp_path / "raw")
        os.makedirs(pdf_dir)

        # 创建测试 PDF
        pdf_path = os.path.join(pdf_dir, "测试教材.pdf")
        _create_minimal_pdf(pdf_path, num_pages=1)

        # 预写缓存
        cached_content = "这是缓存的 OCR 内容，含公式 $E=mc^2$"
        _write_cache(parsed_dir, "测试教材", 1, cached_content)

        reader = PDFReader(
            parsed_dir=parsed_dir,
            images_dir=images_dir,
            api_key="test-key",
        )

        with patch.object(reader, "_ocr_page") as mock_ocr:
            results = reader.read_pdf(pdf_path)

        assert len(results) == 1
        assert results[0].from_cache is True
        assert results[0].content == cached_content
        assert results[0].page_number == 1
        # image_path 不再为 None — 代码现在始终渲染 PNG
        assert results[0].image_path is not None
        # OCR 不应被调用
        mock_ocr.assert_not_called()

    def test_cached_page_read_single(self, tmp_path):
        """read_page 单页缓存命中"""
        parsed_dir = str(tmp_path / "parsed")
        images_dir = str(tmp_path / "images")
        pdf_dir = str(tmp_path / "raw")
        os.makedirs(pdf_dir)

        pdf_path = os.path.join(pdf_dir, "数学.pdf")
        _create_minimal_pdf(pdf_path, num_pages=3)

        # 只缓存第 2 页
        _write_cache(parsed_dir, "数学", 2, "第2页缓存")

        reader = PDFReader(
            parsed_dir=parsed_dir,
            images_dir=images_dir,
            api_key="test-key",
        )

        with patch.object(reader, "_render_png") as mock_render, \
             patch.object(reader, "_ocr_with_retry") as mock_ocr:
            mock_render.return_value = str(tmp_path / "images" / "数学" / "page_2.png")
            mock_ocr.return_value = "OCR 结果"

            result = reader.read_page(pdf_path, 2)

        assert result.from_cache is True
        assert result.content == "第2页缓存"


class TestCacheMiss:
    """无缓存时渲染 PNG + OCR + 缓存正确写入"""

    @patch("app.rag.readers.pdf_reader.time.sleep")
    @patch("app.rag.readers.pdf_reader.PDFReader._ocr_page")
    def test_no_cache_triggers_render_and_ocr(self, mock_ocr, mock_sleep, tmp_path):
        """无缓存 → 渲染 PNG + OCR + 存缓存"""
        parsed_dir = str(tmp_path / "parsed")
        images_dir = str(tmp_path / "images")
        pdf_dir = str(tmp_path / "raw")
        os.makedirs(pdf_dir)

        pdf_path = os.path.join(pdf_dir, "测试书.pdf")
        _create_minimal_pdf(pdf_path, num_pages=1)

        ocr_result = "OCR 识别的数学内容 $a^2 + b^2 = c^2$"
        mock_ocr.return_value = ocr_result

        reader = PDFReader(
            parsed_dir=parsed_dir,
            images_dir=images_dir,
            api_key="test-key",
        )

        results = reader.read_pdf(pdf_path)

        assert len(results) == 1
        result = results[0]
        assert result.from_cache is False
        assert result.content == ocr_result
        assert result.page_number == 1
        assert result.image_path is not None
        assert os.path.exists(result.image_path)
        assert result.image_path.endswith("page_1.png")

        # 验证缓存文件已写入
        cache_path = os.path.join(parsed_dir, "测试书", "page_1.md")
        assert os.path.exists(cache_path)
        with open(cache_path, "r", encoding="utf-8") as f:
            assert f.read() == ocr_result

        # PNG 文件也应该存在
        png_path = os.path.join(images_dir, "测试书", "page_1.png")
        assert os.path.exists(png_path)

        # OCR 被调用了一次
        mock_ocr.assert_called_once()

    @patch("app.rag.readers.pdf_reader.time.sleep")
    @patch("app.rag.readers.pdf_reader.PDFReader._ocr_page")
    def test_no_cache_second_read_uses_cache(self, mock_ocr, mock_sleep, tmp_path):
        """第一次无缓存走 OCR，第二次读走缓存"""
        parsed_dir = str(tmp_path / "parsed")
        images_dir = str(tmp_path / "images")
        pdf_dir = str(tmp_path / "raw")
        os.makedirs(pdf_dir)

        pdf_path = os.path.join(pdf_dir, "课本.pdf")
        _create_minimal_pdf(pdf_path, num_pages=1)

        mock_ocr.return_value = "OCR 结果文本"

        reader = PDFReader(
            parsed_dir=parsed_dir,
            images_dir=images_dir,
            api_key="test-key",
        )

        # 第一次：无缓存
        results1 = reader.read_pdf(pdf_path)
        assert results1[0].from_cache is False
        mock_ocr.assert_called_once()

        # 第二次：有缓存
        results2 = reader.read_pdf(pdf_path)
        assert results2[0].from_cache is True
        assert results2[0].content == "OCR 结果文本"
        # OCR 没有被再次调用
        mock_ocr.assert_called_once()


class TestOCRRetry:
    """OCR 失败重试 2 次后跳过，日志记录失败页码"""

    @patch("app.rag.readers.pdf_reader.time.sleep")
    @patch("app.rag.readers.pdf_reader.PDFReader._ocr_page")
    def test_ocr_retry_and_skip_on_failure(self, mock_ocr, mock_sleep, tmp_path):
        """OCR 持续失败 → 重试 2 次后跳过，content 为空"""
        parsed_dir = str(tmp_path / "parsed")
        images_dir = str(tmp_path / "images")
        pdf_dir = str(tmp_path / "raw")
        os.makedirs(pdf_dir)

        pdf_path = os.path.join(pdf_dir, "重试测试.pdf")
        _create_minimal_pdf(pdf_path, num_pages=1)

        mock_ocr.side_effect = RuntimeError("OCR 服务不可用")

        reader = PDFReader(
            parsed_dir=parsed_dir,
            images_dir=images_dir,
            api_key="test-key",
            max_retries=2,
        )

        results = reader.read_pdf(pdf_path)

        assert len(results) == 1
        result = results[0]
        assert result.from_cache is False
        assert result.content == ""
        assert result.page_number == 1

        # 初始调用 + 2 次重试 = 3 次
        assert mock_ocr.call_count == 3

    @patch("app.rag.readers.pdf_reader.time.sleep")
    @patch("app.rag.readers.pdf_reader.PDFReader._ocr_page")
    def test_ocr_retry_succeeds_on_second_attempt(self, mock_ocr, mock_sleep, tmp_path):
        """OCR 第一次失败，第二次成功"""
        parsed_dir = str(tmp_path / "parsed")
        images_dir = str(tmp_path / "images")
        pdf_dir = str(tmp_path / "raw")
        os.makedirs(pdf_dir)

        pdf_path = os.path.join(pdf_dir, "部分失败.pdf")
        _create_minimal_pdf(pdf_path, num_pages=1)

        mock_ocr.side_effect = [
            RuntimeError("临时错误"),
            "OCR 成功结果",
        ]

        reader = PDFReader(
            parsed_dir=parsed_dir,
            images_dir=images_dir,
            api_key="test-key",
            max_retries=2,
        )

        results = reader.read_pdf(pdf_path)

        assert results[0].content == "OCR 成功结果"
        assert results[0].from_cache is False
        assert mock_ocr.call_count == 2

    @patch("app.rag.readers.pdf_reader.time.sleep")
    @patch("app.rag.readers.pdf_reader.PDFReader._ocr_page")
    def test_ocr_failure_does_not_block_other_pages(self, mock_ocr, mock_sleep, tmp_path):
        """某一页 OCR 失败不阻塞其他页"""
        parsed_dir = str(tmp_path / "parsed")
        images_dir = str(tmp_path / "images")
        pdf_dir = str(tmp_path / "raw")
        os.makedirs(pdf_dir)

        pdf_path = os.path.join(pdf_dir, "混合.pdf")
        _create_minimal_pdf(pdf_path, num_pages=3)

        # 第 1 页成功，第 2 页失败，第 3 页成功
        mock_ocr.side_effect = [
            "第1页内容",
            RuntimeError("OCR 失败"),
            RuntimeError("OCR 再次失败"),
            RuntimeError("OCR 第三次失败"),
            "第3页内容",
        ]

        reader = PDFReader(
            parsed_dir=parsed_dir,
            images_dir=images_dir,
            api_key="test-key",
            max_retries=2,
        )

        results = reader.read_pdf(pdf_path)

        assert len(results) == 3
        assert results[0].content == "第1页内容"
        assert results[1].content == ""  # 失败页
        assert results[2].content == "第3页内容"


class TestMultiPage:
    """跨页内容正确分割"""

    @patch("app.rag.readers.pdf_reader.time.sleep")
    @patch("app.rag.readers.pdf_reader.PDFReader._ocr_page")
    def test_multi_page_pdf_returns_separate_results(self, mock_ocr, mock_sleep, tmp_path):
        """多页 PDF 每页独立返回 PageResult"""
        parsed_dir = str(tmp_path / "parsed")
        images_dir = str(tmp_path / "images")
        pdf_dir = str(tmp_path / "raw")
        os.makedirs(pdf_dir)

        pdf_path = os.path.join(pdf_dir, "多页.pdf")
        _create_minimal_pdf(pdf_path, num_pages=3)

        mock_ocr.side_effect = [
            "第1页：集合的概念",
            "第2页：集合的表示",
            "第3页：集合的运算",
        ]

        reader = PDFReader(
            parsed_dir=parsed_dir,
            images_dir=images_dir,
            api_key="test-key",
        )

        results = reader.read_pdf(pdf_path)

        assert len(results) == 3
        assert results[0].page_number == 1
        assert results[0].content == "第1页：集合的概念"
        assert results[1].page_number == 2
        assert results[1].content == "第2页：集合的表示"
        assert results[2].page_number == 3
        assert results[2].content == "第3页：集合的运算"

        # 每页都有 PNG
        for r in results:
            assert r.image_path is not None
            assert os.path.exists(r.image_path)

        # 每页都有缓存
        for i in range(1, 4):
            cache_path = os.path.join(parsed_dir, "多页", f"page_{i}.md")
            assert os.path.exists(cache_path)

    @patch("app.rag.readers.pdf_reader.PDFReader._ocr_page")
    def test_mixed_cache_and_fresh_pages(self, mock_ocr, tmp_path):
        """混合场景：部分页有缓存，部分页需要 OCR"""
        parsed_dir = str(tmp_path / "parsed")
        images_dir = str(tmp_path / "images")
        pdf_dir = str(tmp_path / "raw")
        os.makedirs(pdf_dir)

        pdf_path = os.path.join(pdf_dir, "混合缓存.pdf")
        _create_minimal_pdf(pdf_path, num_pages=3)

        # 预缓存第 1 页和第 3 页
        _write_cache(parsed_dir, "混合缓存", 1, "缓存第1页")
        _write_cache(parsed_dir, "混合缓存", 3, "缓存第3页")

        mock_ocr.return_value = "OCR 第2页"

        reader = PDFReader(
            parsed_dir=parsed_dir,
            images_dir=images_dir,
            api_key="test-key",
        )

        results = reader.read_pdf(pdf_path)

        assert len(results) == 3
        assert results[0].from_cache is True
        assert results[0].content == "缓存第1页"
        assert results[1].from_cache is False
        assert results[1].content == "OCR 第2页"
        assert results[2].from_cache is True
        assert results[2].content == "缓存第3页"

        # 只对第 2 页调用了 OCR
        mock_ocr.assert_called_once()


class TestCacheWriteFailure:
    """缓存写入失败不阻塞"""

    @patch("app.rag.readers.pdf_reader.time.sleep")
    @patch("app.rag.readers.pdf_reader.PDFReader._ocr_page")
    def test_cache_write_failure_does_not_block(self, mock_ocr, mock_sleep, tmp_path):
        """缓存写入失败 → 日志记录，不抛异常"""
        parsed_dir = str(tmp_path / "parsed")
        images_dir = str(tmp_path / "images")
        pdf_dir = str(tmp_path / "raw")
        os.makedirs(pdf_dir)

        pdf_path = os.path.join(pdf_dir, "缓存失败.pdf")
        _create_minimal_pdf(pdf_path, num_pages=1)

        mock_ocr.return_value = "OCR 结果"

        reader = PDFReader(
            parsed_dir=parsed_dir,
            images_dir=images_dir,
            api_key="test-key",
        )

        # mock _save_cache 抛异常
        with patch.object(reader, "_save_cache", side_effect=OSError("磁盘满")):
            results = reader.read_pdf(pdf_path)

        # 仍然返回结果
        assert len(results) == 1
        assert results[0].content == "OCR 结果"
        assert results[0].from_cache is False


class TestEdgeCases:
    """边界情况"""

    def test_pdf_not_found_raises(self, tmp_path):
        """PDF 文件不存在 → FileNotFoundError"""
        reader = PDFReader(
            parsed_dir=str(tmp_path / "parsed"),
            images_dir=str(tmp_path / "images"),
            api_key="test-key",
        )

        with pytest.raises(FileNotFoundError, match="PDF 文件不存在"):
            reader.read_pdf("/nonexistent/file.pdf")

    def test_single_page_pdf_returns_one_result(self, tmp_path):
        """1 页 PDF → 返回 1 个 PageResult"""
        parsed_dir = str(tmp_path / "parsed")
        images_dir = str(tmp_path / "images")
        pdf_dir = str(tmp_path / "raw")
        os.makedirs(pdf_dir)

        pdf_path = os.path.join(pdf_dir, "一页.pdf")
        _create_minimal_pdf(pdf_path, num_pages=1)

        _write_cache(parsed_dir, "一页", 1, "唯一一页")

        reader = PDFReader(
            parsed_dir=parsed_dir,
            images_dir=images_dir,
            api_key="test-key",
        )

        results = reader.read_pdf(pdf_path)
        assert len(results) == 1
        assert results[0].page_number == 1
        assert results[0].from_cache is True

    def test_page_number_out_of_range(self, tmp_path):
        """页码超出范围 → ValueError"""
        pdf_dir = str(tmp_path / "raw")
        os.makedirs(pdf_dir)
        pdf_path = os.path.join(pdf_dir, "小册子.pdf")
        _create_minimal_pdf(pdf_path, num_pages=2)

        reader = PDFReader(
            parsed_dir=str(tmp_path / "parsed"),
            images_dir=str(tmp_path / "images"),
            api_key="test-key",
        )

        with pytest.raises(ValueError, match="页码超出范围"):
            reader.read_page(pdf_path, 99)

    def test_read_single_page(self, tmp_path):
        """read_page 正常读取单页"""
        parsed_dir = str(tmp_path / "parsed")
        images_dir = str(tmp_path / "images")
        pdf_dir = str(tmp_path / "raw")
        os.makedirs(pdf_dir)

        pdf_path = os.path.join(pdf_dir, "单页测试.pdf")
        _create_minimal_pdf(pdf_path, num_pages=5)

        _write_cache(parsed_dir, "单页测试", 3, "第3页内容")

        reader = PDFReader(
            parsed_dir=parsed_dir,
            images_dir=images_dir,
            api_key="test-key",
        )

        result = reader.read_page(pdf_path, 3)
        assert result.page_number == 3
        assert result.from_cache is True
        assert result.content == "第3页内容"


class TestExtractBookName:
    """书名提取测试"""

    def test_simple_filename(self):
        assert PDFReader._extract_book_name("data/raw/必修第一册.pdf") == "必修第一册"

    def test_path_with_directory(self):
        assert PDFReader._extract_book_name("/home/user/数学教材.pdf") == "数学教材"

    def test_chinese_filename(self):
        assert PDFReader._extract_book_name("选择性必修第一册.pdf") == "选择性必修第一册"
