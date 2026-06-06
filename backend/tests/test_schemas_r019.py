"""R019-BF002 schemas.py 数据模型扩展单元测试"""
import pytest
from pydantic import ValidationError

from app.chat.schemas import ApiMessage, ChatRequest, ImageRef


# ---------------------------------------------------------------------------
# ImageRef
# ---------------------------------------------------------------------------


class TestImageRef:
    def test_valid_image_ref(self):
        ref = ImageRef(url="https://example.com/img.png", image_id="abc123")
        assert ref.url == "https://example.com/img.png"
        assert ref.image_id == "abc123"

    def test_missing_url_raises(self):
        with pytest.raises(ValidationError):
            ImageRef(image_id="abc123")

    def test_missing_image_id_raises(self):
        with pytest.raises(ValidationError):
            ImageRef(url="https://example.com/img.png")


# ---------------------------------------------------------------------------
# ChatRequest images 字段
# ---------------------------------------------------------------------------


class TestChatRequestImages:
    def test_default_images_is_empty_list(self):
        req = ChatRequest(question="hello")
        assert req.images == []

    def test_images_within_limit(self):
        images = [
            ImageRef(url=f"https://ex.com/{i}.png", image_id=str(i))
            for i in range(3)
        ]
        req = ChatRequest(question="hello", images=images)
        assert len(req.images) == 3

    def test_images_exceeds_max_length_raises(self):
        images = [
            ImageRef(url=f"https://ex.com/{i}.png", image_id=str(i))
            for i in range(4)
        ]
        with pytest.raises(ValidationError):
            ChatRequest(question="hello", images=images)

    def test_empty_question_still_requires_min_length(self):
        with pytest.raises(ValidationError):
            ChatRequest(question="")

    def test_whitespace_only_question_raises(self):
        with pytest.raises(ValidationError):
            ChatRequest(question="   ")


# ---------------------------------------------------------------------------
# ApiMessage images 字段
# ---------------------------------------------------------------------------


class TestApiMessageImages:
    def test_default_images_is_empty_list(self):
        msg = ApiMessage(id="1", role="user", content="hi")
        assert msg.images == []

    def test_with_images(self):
        images = [ImageRef(url="https://ex.com/a.png", image_id="a1")]
        msg = ApiMessage(id="1", role="user", content="hi", images=images)
        assert len(msg.images) == 1
        assert msg.images[0].image_id == "a1"
