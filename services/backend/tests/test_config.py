import os

import pytest
from pydantic import ValidationError
from pydantic_settings import BaseSettings


def test_config_missing_dashscope_key_raises():
    """缺少 DASHSCOPE_API_KEY 时启动报错"""

    class TestSettings(BaseSettings):
        dashscope_api_key: str

        model_config = {"extra": "ignore"}

    key = "DASHSCOPE_API_KEY"
    original = os.environ.pop(key, None)
    try:
        with pytest.raises(ValidationError):
            TestSettings()
    finally:
        if original is not None:
            os.environ[key] = original
