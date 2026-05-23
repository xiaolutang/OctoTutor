"""DashScopeEmbedding 单元测试

使用 mock 模拟 DashScope API 调用，验证：
- 正常调用返回 768 维向量
- 批量大小超过 6 时自动分批
- API 失败时指数退避重试 3 次
- 空 texts 抛出 ValueError
- 所有重试失败抛出 RuntimeError
- 维度不匹配抛出 ValueError
"""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import MagicMock, patch

import pytest

from app.rag.embeddings import DashScopeEmbedding


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _make_response(
    embeddings: list[list[float]],
    status_code: int = 200,
    code: str = "",
    message: str = "",
):
    """构造 mock DashScopeAPIResponse"""

    @dataclass
    class FakeResponse:
        status_code: int
        code: str
        message: str
        output: dict
        usage: dict
        request_id: str = "fake-req-id"

    output = {
        "embeddings": [
            {"embedding": emb, "text_index": i}
            for i, emb in enumerate(embeddings)
        ]
    }

    return FakeResponse(
        status_code=status_code,
        code=code,
        message=message,
        output=output,
        usage={"total_tokens": 10},
    )


def _make_embedding(dim: int = 768) -> list[float]:
    """生成指定维度的伪向量"""
    return [0.01 * (i % 100) for i in range(dim)]


@dataclass
class _FakeAPIResponse:
    """模拟非 200 状态码的 DashScope API 响应"""
    status_code: int = 500
    code: str = "InternalError"
    message: str = "服务内部错误"
    output: dict = field(default_factory=dict)
    usage: dict = field(default_factory=dict)
    request_id: str = "fake-req-id"


# ---------------------------------------------------------------------------
# 测试类
# ---------------------------------------------------------------------------


class TestDashScopeEmbeddingInit:
    """初始化相关测试"""

    def test_init_with_valid_params(self):
        emb = DashScopeEmbedding(api_key="test-key")
        assert emb._api_key == "test-key"
        assert emb._model == "text-embedding-v4"
        assert emb._dimension == 768
        assert emb._batch_size == 6
        assert emb._max_retries == 3

    def test_init_with_custom_params(self):
        emb = DashScopeEmbedding(
            api_key="test-key",
            model="tongyi-embedding-vision-flash",
            dimension=1024,
            batch_size=4,
            max_retries=5,
        )
        assert emb._model == "tongyi-embedding-vision-flash"
        assert emb._dimension == 1024
        assert emb._batch_size == 4
        assert emb._max_retries == 5

    def test_init_empty_api_key_raises(self):
        with pytest.raises(ValueError, match="dashscope_api_key"):
            DashScopeEmbedding(api_key="")


class TestEmbedBasic:
    """基本 embed 调用测试"""

    @patch("app.rag.embeddings.TextEmbedding")
    def test_embed_single_text(self, mock_te):
        """单条文本 → 返回 768 维向量"""
        vector = _make_embedding()
        mock_te.call.return_value = _make_response([vector])

        emb = DashScopeEmbedding(api_key="test-key")
        result = emb.embed(["测试文本"])

        assert len(result) == 1
        assert len(result[0]) == 768
        mock_te.call.assert_called_once()

    @patch("app.rag.embeddings.TextEmbedding")
    def test_embed_multiple_texts(self, mock_te):
        """多条文本 → 返回等长向量列表"""
        vectors = [_make_embedding() for _ in range(3)]
        mock_te.call.return_value = _make_response(vectors)

        emb = DashScopeEmbedding(api_key="test-key")
        result = emb.embed(["文本1", "文本2", "文本3"])

        assert len(result) == 3
        for v in result:
            assert len(v) == 768

    @patch("app.rag.embeddings.TextEmbedding")
    def test_embed_empty_texts_raises(self, mock_te):
        """空列表 → ValueError"""
        emb = DashScopeEmbedding(api_key="test-key")
        with pytest.raises(ValueError, match="texts"):
            emb.embed([])

    @patch("app.rag.embeddings.TextEmbedding")
    def test_embed_preserves_order(self, mock_te):
        """结果顺序与输入一致"""
        vectors = [_make_embedding() for _ in range(3)]
        # 模拟 API 返回乱序
        mock_te.call.return_value = _make_response(vectors)

        emb = DashScopeEmbedding(api_key="test-key")
        result = emb.embed(["A", "B", "C"])

        assert result[0] == vectors[0]
        assert result[1] == vectors[1]
        assert result[2] == vectors[2]

    @patch("app.rag.embeddings.TextEmbedding")
    def test_embed_passes_api_key(self, mock_te):
        """调用时传入正确的 api_key"""
        mock_te.call.return_value = _make_response([_make_embedding()])

        emb = DashScopeEmbedding(api_key="my-secret-key")
        emb.embed(["测试"])

        call_kwargs = mock_te.call.call_args
        assert call_kwargs.kwargs["api_key"] == "my-secret-key"


class TestEmbedBatching:
    """批量分片逻辑测试"""

    @patch("app.rag.embeddings.TextEmbedding")
    def test_batch_exactly_6(self, mock_te):
        """恰好 6 条 → 1 次 API 调用"""
        vectors = [_make_embedding() for _ in range(6)]
        mock_te.call.return_value = _make_response(vectors)

        emb = DashScopeEmbedding(api_key="test-key", batch_size=6)
        result = emb.embed([f"文本{i}" for i in range(6)])

        assert len(result) == 6
        assert mock_te.call.call_count == 1

    @patch("app.rag.embeddings.TextEmbedding")
    def test_batch_7_texts_split_into_2(self, mock_te):
        """7 条文本 → 2 次 API 调用（6+1）"""
        vectors6 = [_make_embedding() for _ in range(6)]
        vectors1 = [_make_embedding()]

        mock_te.call.side_effect = [
            _make_response(vectors6),
            _make_response(vectors1),
        ]

        emb = DashScopeEmbedding(api_key="test-key", batch_size=6)
        result = emb.embed([f"文本{i}" for i in range(7)])

        assert len(result) == 7
        assert mock_te.call.call_count == 2

        # 验证第一次调用传入 6 条，第二次传入 1 条
        calls = mock_te.call.call_args_list
        assert len(calls[0].kwargs["input"]) == 6
        assert len(calls[1].kwargs["input"]) == 1

    @patch("app.rag.embeddings.TextEmbedding")
    def test_batch_13_texts_split_into_3(self, mock_te):
        """13 条文本 → 3 次 API 调用（6+6+1）"""
        vectors6a = [_make_embedding() for _ in range(6)]
        vectors6b = [_make_embedding() for _ in range(6)]
        vectors1 = [_make_embedding()]

        mock_te.call.side_effect = [
            _make_response(vectors6a),
            _make_response(vectors6b),
            _make_response(vectors1),
        ]

        emb = DashScopeEmbedding(api_key="test-key", batch_size=6)
        result = emb.embed([f"文本{i}" for i in range(13)])

        assert len(result) == 13
        assert mock_te.call.call_count == 3

    @patch("app.rag.embeddings.TextEmbedding")
    def test_custom_batch_size(self, mock_te):
        """自定义 batch_size=3, 5 条 → 2 次调用（3+2）"""
        vectors3 = [_make_embedding() for _ in range(3)]
        vectors2 = [_make_embedding() for _ in range(2)]

        mock_te.call.side_effect = [
            _make_response(vectors3),
            _make_response(vectors2),
        ]

        emb = DashScopeEmbedding(
            api_key="test-key", batch_size=3
        )
        result = emb.embed([f"文本{i}" for i in range(5)])

        assert len(result) == 5
        assert mock_te.call.call_count == 2

        calls = mock_te.call.call_args_list
        assert len(calls[0].kwargs["input"]) == 3
        assert len(calls[1].kwargs["input"]) == 2

    @patch("app.rag.embeddings.TextEmbedding")
    def test_batch_results_in_correct_positions(self, mock_te):
        """分批后结果放到正确的索引位置"""
        # 第一批 0-5
        batch1_vectors = [[float(i)] * 768 for i in range(6)]
        # 第二批 6
        batch2_vectors = [[99.0] * 768]

        mock_te.call.side_effect = [
            _make_response(batch1_vectors),
            _make_response(batch2_vectors),
        ]

        emb = DashScopeEmbedding(api_key="test-key", batch_size=6)
        result = emb.embed([f"文本{i}" for i in range(7)])

        # 第一批结果
        for i in range(6):
            assert result[i][0] == float(i)
        # 第二批结果
        assert result[6][0] == 99.0


class TestEmbedRetry:
    """指数退避重试测试"""

    @patch("app.rag.embeddings.time.sleep")
    @patch("app.rag.embeddings.TextEmbedding")
    def test_retry_succeeds_on_second_attempt(self, mock_te, mock_sleep):
        """第一次失败 → 第二次成功"""
        vector = _make_embedding()
        mock_te.call.side_effect = [
            RuntimeError("网络错误"),
            _make_response([vector]),
        ]

        emb = DashScopeEmbedding(
            api_key="test-key", max_retries=3
        )
        result = emb.embed(["测试"])

        assert len(result) == 1
        assert mock_te.call.call_count == 2
        # 第一次重试等待 2^0 = 1 秒
        mock_sleep.assert_called_once_with(1)

    @patch("app.rag.embeddings.time.sleep")
    @patch("app.rag.embeddings.TextEmbedding")
    def test_retry_exponential_backoff(self, mock_te, mock_sleep):
        """验证指数退避等待时间：1s, 2s"""
        vector = _make_embedding()
        mock_te.call.side_effect = [
            RuntimeError("错误1"),
            RuntimeError("错误2"),
            _make_response([vector]),
        ]

        emb = DashScopeEmbedding(
            api_key="test-key", max_retries=3
        )
        result = emb.embed(["测试"])

        assert len(result) == 1
        assert mock_te.call.call_count == 3
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(1)  # 2^0
        mock_sleep.assert_any_call(2)  # 2^1

    @patch("app.rag.embeddings.time.sleep")
    @patch("app.rag.embeddings.TextEmbedding")
    def test_retry_all_failed_raises_runtime_error(
        self, mock_te, mock_sleep
    ):
        """3 次重试全部失败 → RuntimeError"""
        mock_te.call.side_effect = RuntimeError("API 挂了")

        emb = DashScopeEmbedding(
            api_key="test-key", max_retries=3
        )
        with pytest.raises(RuntimeError, match="重试"):
            emb.embed(["测试"])

        # 初始调用 + 3 次重试 = 4 次
        assert mock_te.call.call_count == 4
        # 重试等待 1s, 2s, 4s
        assert mock_sleep.call_count == 3
        mock_sleep.assert_any_call(1)
        mock_sleep.assert_any_call(2)
        mock_sleep.assert_any_call(4)

    @patch("app.rag.embeddings.time.sleep")
    @patch("app.rag.embeddings.TextEmbedding")
    def test_retry_on_api_status_error(self, mock_te, mock_sleep):
        """API 返回非 200 状态码 → 重试"""
        vector = _make_embedding()
        mock_te.call.side_effect = [
            _FakeAPIResponse(),
            _make_response([vector]),
        ]

        emb = DashScopeEmbedding(
            api_key="test-key", max_retries=3
        )
        result = emb.embed(["测试"])

        assert len(result) == 1
        assert mock_te.call.call_count == 2

    @patch("app.rag.embeddings.time.sleep")
    @patch("app.rag.embeddings.TextEmbedding")
    def test_retry_with_zero_max_retries(self, mock_te, mock_sleep):
        """max_retries=0 → 不重试，直接抛异常"""
        mock_te.call.side_effect = RuntimeError("API 错误")

        emb = DashScopeEmbedding(
            api_key="test-key", max_retries=0
        )
        with pytest.raises(RuntimeError):
            emb.embed(["测试"])

        assert mock_te.call.call_count == 1
        mock_sleep.assert_not_called()


class TestEmbedQuery:
    """embed_query 测试"""

    @patch("app.rag.embeddings.TextEmbedding")
    def test_embed_query_returns_vector(self, mock_te):
        """单条查询 → 返回 768 维向量"""
        vector = _make_embedding()
        mock_te.call.return_value = _make_response([vector])

        emb = DashScopeEmbedding(api_key="test-key")
        result = emb.embed_query("什么是集合？")

        assert len(result) == 768
        assert result == vector

    @patch("app.rag.embeddings.TextEmbedding")
    def test_embed_query_passes_text_type(self, mock_te):
        """embed_query 传入 text_type=query"""
        mock_te.call.return_value = _make_response([_make_embedding()])

        emb = DashScopeEmbedding(api_key="test-key")
        emb.embed_query("测试查询")

        call_kwargs = mock_te.call.call_args
        assert call_kwargs.kwargs.get("text_type") == "query"

    @patch("app.rag.embeddings.TextEmbedding")
    def test_embed_query_empty_text_raises(self, mock_te):
        """空查询文本 → ValueError"""
        emb = DashScopeEmbedding(api_key="test-key")
        with pytest.raises(ValueError, match="查询文本"):
            emb.embed_query("")


class TestDimensionValidation:
    """维度验证测试"""

    @patch("app.rag.embeddings.TextEmbedding")
    def test_dimension_mismatch_raises(self, mock_te):
        """返回维度与预期不符 → ValueError"""
        wrong_dim_vector = [0.1] * 512
        mock_te.call.return_value = _make_response([wrong_dim_vector])

        emb = DashScopeEmbedding(
            api_key="test-key", dimension=768
        )
        with pytest.raises(ValueError, match="维度不匹配"):
            emb.embed(["测试"])

    @patch("app.rag.embeddings.TextEmbedding")
    def test_correct_dimension_passes(self, mock_te):
        """返回维度正确 → 正常通过"""
        vector = _make_embedding(768)
        mock_te.call.return_value = _make_response([vector])

        emb = DashScopeEmbedding(
            api_key="test-key", dimension=768
        )
        result = emb.embed(["测试"])

        assert len(result[0]) == 768


class TestSplitBatches:
    """_split_batches 私有方法测试"""

    def test_split_empty(self):
        """空列表 → 空批次"""
        emb = DashScopeEmbedding(api_key="test-key")
        batches = emb._split_batches([])
        assert batches == []

    def test_split_less_than_batch_size(self):
        """少于 batch_size → 1 个批次"""
        emb = DashScopeEmbedding(api_key="test-key", batch_size=6)
        batches = emb._split_batches(["a", "b", "c"])
        assert len(batches) == 1
        assert batches[0] == (0, ["a", "b", "c"])

    def test_split_exact_batch_size(self):
        """恰好 batch_size → 1 个批次"""
        emb = DashScopeEmbedding(api_key="test-key", batch_size=3)
        batches = emb._split_batches(["a", "b", "c"])
        assert len(batches) == 1
        assert batches[0] == (0, ["a", "b", "c"])

    def test_split_multiple_batches(self):
        """多个批次 → 正确分片"""
        emb = DashScopeEmbedding(api_key="test-key", batch_size=3)
        batches = emb._split_batches(["a", "b", "c", "d", "e"])
        assert len(batches) == 2
        assert batches[0] == (0, ["a", "b", "c"])
        assert batches[1] == (3, ["d", "e"])

    def test_split_preserves_indices(self):
        """分片索引正确"""
        emb = DashScopeEmbedding(api_key="test-key", batch_size=2)
        batches = emb._split_batches(["a", "b", "c", "d", "e"])
        assert batches[0] == (0, ["a", "b"])
        assert batches[1] == (2, ["c", "d"])
        assert batches[2] == (4, ["e"])
