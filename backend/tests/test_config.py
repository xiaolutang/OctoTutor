import os

import pytest
from pydantic import ValidationError
from pydantic_settings import BaseSettings

from app.config import Settings


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


def test_database_url_from_env():
    """设置 DATABASE_URL 环境变量后，settings.database_url 正确读取"""

    custom_url = "postgresql://user:pass@dbhost:5432/testdb"
    key = "DATABASE_URL"
    original = os.environ.get(key)
    try:
        os.environ[key] = custom_url
        s = Settings(
            dashscope_api_key="test-key",
            auth_jwt_secret="test-secret",
        )
        assert s.database_url == custom_url
    finally:
        if original is not None:
            os.environ[key] = original
        else:
            os.environ.pop(key, None)
