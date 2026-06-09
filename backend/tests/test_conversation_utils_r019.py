"""R019-BB003 to_api_message images 提取单元测试

覆盖 tasks.md 定义的 3 个 scenario：
1. 有 images 提取成功
2. 无 images 返回空列表
3. images 格式异常静默跳过
"""

from unittest.mock import MagicMock

from app.chat.conversation_utils import to_api_message
from app.chat.schemas import ImageRef
from tests._helpers import make_mock_msg


class TestToApiMessageImages:
    """R019-BB003: to_api_message images 提取"""

    def test_extracts_images_from_additional_kwargs(self):
        """有 images 提取成功"""
        msg = make_mock_msg(additional_kwargs={
            "images": [
                {"url": "/api/uploads/user1/abc.png", "image_id": "abc"},
                {"url": "/api/uploads/user1/def.jpg", "image_id": "def"},
            ]
        })

        result = to_api_message(msg, 0)
        assert len(result.images) == 2
        assert isinstance(result.images[0], ImageRef)
        assert result.images[0].image_id == "abc"
        assert result.images[1].url == "/api/uploads/user1/def.jpg"

    def test_no_images_returns_empty_list(self):
        """无 images 返回空列表"""
        msg = make_mock_msg(additional_kwargs={})
        result = to_api_message(msg, 0)
        assert result.images == []

    def test_none_additional_kwargs_returns_empty_list(self):
        """additional_kwargs 为 None 时返回空列表"""
        msg = make_mock_msg(additional_kwargs=None)
        result = to_api_message(msg, 0)
        assert result.images == []

    def test_malformed_images_silently_skipped(self):
        """images 格式异常静默跳过"""
        msg = make_mock_msg(additional_kwargs={
            "images": [
                {"url": "/api/uploads/user1/abc.png", "image_id": "abc"},  # valid
                "not a dict",  # invalid: string
                {"url": "missing_image_id"},  # invalid: missing required field
            ]
        })

        result = to_api_message(msg, 0)
        assert len(result.images) == 1
        assert result.images[0].image_id == "abc"

    def test_empty_images_list_returns_empty(self):
        """images 为空列表时返回空列表"""
        msg = make_mock_msg(additional_kwargs={"images": []})
        result = to_api_message(msg, 0)
        assert result.images == []
