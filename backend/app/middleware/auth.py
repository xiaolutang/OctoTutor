"""JWT 鉴权中间件

使用 Depends(get_current_user) 按需注入鉴权。
与 auth-center 共享 HS256 密钥，本地解码验证。
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.config import settings

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

ALGORITHM = "HS256"

# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UserContext:
    """从 JWT 解码后的用户上下文"""

    user_id: str
    username: str


# ---------------------------------------------------------------------------
# Bearer token 提取器
# ---------------------------------------------------------------------------

_bearer_scheme = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Depends 注入入口
# ---------------------------------------------------------------------------


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> UserContext:
    """从 Authorization: Bearer {token} 提取并验证 JWT

    Raises:
        HTTPException 401: token 缺失、格式错误、签名无效、过期、类型不匹配
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    try:
        payload = jwt.decode(
            token,
            settings.auth_jwt_secret,
            algorithms=[ALGORITHM],
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    # 校验 token type
    token_type = payload.get("type")
    if token_type != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type, expected 'access'",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 提取 user_id（sub 字段）
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject (sub)",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 提取 username（client_id 字段作为显示名，缺失时回退到 sub）
    username = payload.get("client_id", user_id)

    return UserContext(user_id=str(user_id), username=str(username))
