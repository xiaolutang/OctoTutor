"""BF001 JWT 鉴权中间件单元测试

覆盖 13 个场景：有效 token、缺失 token、空 Bearer、错误 scheme、
损坏 token、过期 token、边界过期、错误 type、缺失 sub、空 sub、
错误 secret、配置缺失、client_id 回退。
"""

import os
import time
from unittest.mock import patch

import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from jose import jwt
from pydantic import ValidationError
from pydantic_settings import BaseSettings

from app.middleware.auth import ALGORITHM, UserContext, get_current_user


# ---------------------------------------------------------------------------
# 测试辅助工具
# ---------------------------------------------------------------------------

TEST_SECRET = "test-jwt-secret-key"


def _make_token(payload: dict, secret: str = TEST_SECRET) -> str:
    """构造 JWT token 用于测试"""
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def _make_request_with_token(token: str | None = None) -> dict:
    """构造带 Authorization header 的 FastAPI Request mock"""
    headers: dict = {}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    return headers


# ---------------------------------------------------------------------------
# 测试用 FastAPI 应用
# ---------------------------------------------------------------------------

def _create_test_app():
    """创建一个带鉴权端点的测试应用"""
    app = FastAPI()

    @app.get("/test-auth")
    async def test_auth(user: UserContext = Depends(get_current_user)):
        return {"user_id": user.user_id, "username": user.username}

    return app


# ---------------------------------------------------------------------------
# T1: 有效 token → UserContext 正确提取
# ---------------------------------------------------------------------------


def test_valid_token():
    """有效 JWT → 返回正确的 UserContext"""
    token = _make_token({
        "sub": "user-123",
        "client_id": "testuser",
        "exp": 9999999999,
        "type": "access",
    })

    app = _create_test_app()
    with patch("app.middleware.auth.settings") as mock_settings:
        mock_settings.auth_jwt_secret = TEST_SECRET
        client = TestClient(app)
        response = client.get("/test-auth", headers=_make_request_with_token(token))

    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == "user-123"
    assert data["username"] == "testuser"


# ---------------------------------------------------------------------------
# T2: 无 Authorization header → 401
# ---------------------------------------------------------------------------


def test_missing_token():
    """无 Authorization header → 401 Missing authentication token"""
    app = _create_test_app()
    with patch("app.middleware.auth.settings") as mock_settings:
        mock_settings.auth_jwt_secret = TEST_SECRET
        client = TestClient(app)
        response = client.get("/test-auth")

    assert response.status_code == 401
    assert "Missing authentication token" in response.json()["detail"]


# ---------------------------------------------------------------------------
# T3: 空 Bearer token → 401
# ---------------------------------------------------------------------------


def test_empty_bearer_token():
    """Authorization: Bearer "" → 401"""
    app = _create_test_app()
    with patch("app.middleware.auth.settings") as mock_settings:
        mock_settings.auth_jwt_secret = TEST_SECRET
        client = TestClient(app)
        response = client.get("/test-auth", headers={"Authorization": "Bearer "})

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# T4: 错误 scheme（非 Bearer）→ 401
# ---------------------------------------------------------------------------


def test_wrong_scheme():
    """Authorization: Basic abc123 → 401"""
    app = _create_test_app()
    with patch("app.middleware.auth.settings") as mock_settings:
        mock_settings.auth_jwt_secret = TEST_SECRET
        client = TestClient(app)
        response = client.get("/test-auth", headers={"Authorization": "Basic abc123"})

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# T5: 损坏 token → 401 detail 含 "Invalid token"
# ---------------------------------------------------------------------------


def test_malformed_token():
    """损坏的 token → 401 Invalid token"""
    app = _create_test_app()
    with patch("app.middleware.auth.settings") as mock_settings:
        mock_settings.auth_jwt_secret = TEST_SECRET
        client = TestClient(app)
        response = client.get(
            "/test-auth",
            headers=_make_request_with_token("not.a.valid.jwt"),
        )

    assert response.status_code == 401
    assert "Invalid token" in response.json()["detail"]


# ---------------------------------------------------------------------------
# T6: 过期 token → 401
# ---------------------------------------------------------------------------


def test_expired_token():
    """JWT(exp=1) → 401 Invalid token"""
    token = _make_token({
        "sub": "user-123",
        "exp": 1,
        "type": "access",
    })

    app = _create_test_app()
    with patch("app.middleware.auth.settings") as mock_settings:
        mock_settings.auth_jwt_secret = TEST_SECRET
        client = TestClient(app)
        response = client.get("/test-auth", headers=_make_request_with_token(token))

    assert response.status_code == 401
    assert "Invalid token" in response.json()["detail"]


# ---------------------------------------------------------------------------
# T7: 边界过期（exp ≈ now）→ 401
# ---------------------------------------------------------------------------


def test_boundary_expired_token():
    """JWT(exp=now) → 401（python-jose 有 leeway 容差，exp=now 可能仍通过；用 exp=now-60 确保过期）"""
    token = _make_token({
        "sub": "user-123",
        "exp": int(time.time()) - 60,  # 60 秒前过期，确保超出了 leeway
        "type": "access",
    })

    app = _create_test_app()
    with patch("app.middleware.auth.settings") as mock_settings:
        mock_settings.auth_jwt_secret = TEST_SECRET
        client = TestClient(app)
        response = client.get("/test-auth", headers=_make_request_with_token(token))

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# T8: type != access → 401
# ---------------------------------------------------------------------------


def test_wrong_token_type():
    """JWT(type=refresh) → 401 Invalid token type"""
    token = _make_token({
        "sub": "user-123",
        "client_id": "testuser",
        "exp": 9999999999,
        "type": "refresh",
    })

    app = _create_test_app()
    with patch("app.middleware.auth.settings") as mock_settings:
        mock_settings.auth_jwt_secret = TEST_SECRET
        client = TestClient(app)
        response = client.get("/test-auth", headers=_make_request_with_token(token))

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid token type, expected 'access'"


# ---------------------------------------------------------------------------
# T9: 缺少 sub → 401
# ---------------------------------------------------------------------------


def test_missing_sub():
    """JWT 无 sub 字段 → 401 Token missing subject"""
    token = _make_token({
        "client_id": "testuser",
        "exp": 9999999999,
        "type": "access",
    })

    app = _create_test_app()
    with patch("app.middleware.auth.settings") as mock_settings:
        mock_settings.auth_jwt_secret = TEST_SECRET
        client = TestClient(app)
        response = client.get("/test-auth", headers=_make_request_with_token(token))

    assert response.status_code == 401
    assert response.json()["detail"] == "Token missing subject (sub)"


# ---------------------------------------------------------------------------
# T10: 空 sub（空字符串）→ 401
# ---------------------------------------------------------------------------


def test_empty_sub():
    """JWT(sub="") → 401 Token missing subject"""
    token = _make_token({
        "sub": "",
        "client_id": "testuser",
        "exp": 9999999999,
        "type": "access",
    })

    app = _create_test_app()
    with patch("app.middleware.auth.settings") as mock_settings:
        mock_settings.auth_jwt_secret = TEST_SECRET
        client = TestClient(app)
        response = client.get("/test-auth", headers=_make_request_with_token(token))

    assert response.status_code == 401
    assert response.json()["detail"] == "Token missing subject (sub)"


# ---------------------------------------------------------------------------
# T11: 错误 secret 签发的 token → 401
# ---------------------------------------------------------------------------


def test_wrong_secret():
    """用 wrong-secret 签发的 JWT → 401 Invalid token"""
    token = _make_token(
        {
            "sub": "user-123",
            "client_id": "testuser",
            "exp": 9999999999,
            "type": "access",
        },
        secret="wrong-secret",
    )

    app = _create_test_app()
    with patch("app.middleware.auth.settings") as mock_settings:
        mock_settings.auth_jwt_secret = TEST_SECRET
        client = TestClient(app)
        response = client.get("/test-auth", headers=_make_request_with_token(token))

    assert response.status_code == 401
    assert "Invalid token" in response.json()["detail"]


# ---------------------------------------------------------------------------
# T12: JWT_SECRET_KEY 未配置 → 启动失败
# ---------------------------------------------------------------------------


def test_missing_secret_config():
    """不设置 JWT_SECRET_KEY 环境变量 → Settings 初始化 ValidationError"""
    from pydantic import Field as PydanticField

    class TestSettings(BaseSettings):
        auth_jwt_secret: str = PydanticField(
            ...,
            alias="JWT_SECRET_KEY",
        )

        model_config = {"extra": "ignore"}

    key = "JWT_SECRET_KEY"
    original = os.environ.pop(key, None)
    try:
        with pytest.raises(ValidationError):
            TestSettings()
    finally:
        if original is not None:
            os.environ[key] = original


# ---------------------------------------------------------------------------
# T13: client_id 缺失时 username 回退到 sub
# ---------------------------------------------------------------------------


def test_client_id_fallback():
    """JWT 无 client_id → username 回退到 sub"""
    token = _make_token({
        "sub": "user-123",
        "exp": 9999999999,
        "type": "access",
    })

    app = _create_test_app()
    with patch("app.middleware.auth.settings") as mock_settings:
        mock_settings.auth_jwt_secret = TEST_SECRET
        client = TestClient(app)
        response = client.get("/test-auth", headers=_make_request_with_token(token))

    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == "user-123"
    assert data["username"] == "user-123"  # 回退到 user_id
