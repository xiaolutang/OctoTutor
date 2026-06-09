"""R019 集成测试 fixture — 对真实 Docker 服务发 HTTP 请求。

运行前提：
  1. bash deploy/deploy.sh local
  2. export JWT_SECRET_KEY=xxx（从 deploy/.env 获取）

运行命令：
  pytest tests/integration/ -v

注意：macOS 上 Python 的 DNS 解析器会将 octotutor.localhost 解析到
198.18.x.x 而非 127.0.0.1，导致 Traefik 返回 502。因此使用 127.0.0.1
直连并通过 Host header 路由到正确的 Traefik backend。
"""

from __future__ import annotations

import os
import time

import httpx
import pytest
import pytest_asyncio
from jose import jwt

# 让 pytest-asyncio 自动识别 async 测试函数
pytest_plugins = ["pytest_asyncio"]


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: Docker 集成测试")
    config.addinivalue_line("markers", "vlm: 需要 VLM 服务（DashScope API）")
    config.addinivalue_line("markers", "lru: 需要 IMAGE_MAX_STORAGE_MB=1 小配额环境")


# 强制 asyncio_mode = auto（覆盖 strict）
asyncio_mode = "auto"

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# macOS Python DNS 解析 octotutor.localhost → 198.18.x.x → 502
# 直连 127.0.0.1 + Host header 绕过
DEFAULT_BASE_URL = "http://127.0.0.1"
HOST_HEADER = "octotutor.localhost"
TEST_USER_ID = "9527"
OTHER_USER_ID = "other-user"
FAKE_JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 100
FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
FAKE_WEBP = b"RIFF" + b"\x00" * 100 + b"WEBP"
# LRU 测试用：~200KB 图片，1MB 配额下 6 张即可触发清理
BIG_JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * (200 * 1024)


# ---------------------------------------------------------------------------
# session 级 fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def docker_services_ready():
    """检查 Docker 全栈是否可用，不可达则 skip 全部集成测试。"""
    import urllib.request
    import urllib.error

    base = os.environ.get("OCTOTUTOR_BASE_URL", DEFAULT_BASE_URL)
    host = os.environ.get("OCTOTUTOR_HOST_HEADER", HOST_HEADER)
    try:
        req = urllib.request.Request(f"{base}/api/health")
        req.add_header("Host", host)
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            if resp.status == 200:
                return True
    except (urllib.error.URLError, OSError):
        pass
    pytest.skip("Docker services not available. Run: bash deploy/deploy.sh local")


@pytest.fixture(scope="session")
def base_url(docker_services_ready) -> str:
    return os.environ.get("OCTOTUTOR_BASE_URL", DEFAULT_BASE_URL)


@pytest.fixture(scope="session")
def host_header() -> str:
    return os.environ.get("OCTOTUTOR_HOST_HEADER", HOST_HEADER)


def _make_token(sub: str) -> str:
    """从 JWT_SECRET_KEY 环境变量本地签发 access token。"""
    secret = os.environ.get("JWT_SECRET_KEY")
    if not secret:
        pytest.skip("JWT_SECRET_KEY env var required for integration tests")
    now = int(time.time())
    payload = {
        "sub": sub,
        "client_id": "integration-test",
        "type": "access",
        "iat": now,
        "exp": now + 3600,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


@pytest.fixture(scope="session")
def auth_token(docker_services_ready) -> str:
    return _make_token(TEST_USER_ID)


@pytest.fixture(scope="session")
def auth_headers(auth_token) -> dict:
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture(scope="session")
def other_token(docker_services_ready) -> str:
    return _make_token(OTHER_USER_ID)


@pytest.fixture(scope="session")
def other_headers(other_token) -> dict:
    return {"Authorization": f"Bearer {other_token}"}


@pytest.fixture(scope="session")
def user_id() -> str:
    return TEST_USER_ID


# ---------------------------------------------------------------------------
# function 级 fixture
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def async_client(base_url, host_header) -> httpx.AsyncClient:
    headers = {
        "host": host_header,
    }
    transport = httpx.AsyncHTTPTransport()
    async with httpx.AsyncClient(
        transport=transport,
        base_url=base_url,
        headers=headers,
        timeout=60.0,
    ) as client:
        yield client


@pytest_asyncio.fixture
async def uploaded_image(async_client: httpx.AsyncClient, auth_headers: dict):
    """上传一张 PNG，yield {image_id, url}，teardown 时 DELETE 清理。"""
    resp = await async_client.post(
        "/api/chat/upload",
        files={"file": ("test.png", FAKE_PNG, "image/png")},
        headers=auth_headers,
    )
    assert resp.status_code == 200, f"upload failed: {resp.status_code} {resp.text}"
    data = resp.json()
    yield data
    # 清理
    try:
        await async_client.delete(
            f"/api/chat/upload/{data['image_id']}", headers=auth_headers
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


async def read_sse_stream(
    client: httpx.AsyncClient,
    url: str,
    json_body: dict,
    headers: dict,
    timeout: float = 120.0,
) -> list[dict]:
    """读取完整 SSE 流，返回 [{type, data}] 列表，收到 done 即停。"""
    import json as json_mod

    frames = []
    async with client.stream(
        "POST", url, json=json_body, headers=headers, timeout=timeout
    ) as resp:
        assert resp.status_code == 200
        event_type = ""
        data_str = ""
        async for line in resp.aiter_lines():
            if line.startswith("event: "):
                event_type = line[7:]
            elif line.startswith("data: "):
                data_str = line[6:]
            elif line == "":
                # SSE 帧结束
                if event_type:
                    data = (
                        json_mod.loads(data_str)
                        if data_str and data_str != "null"
                        else None
                    )
                    frames.append({"type": event_type, "data": data})
                    if event_type == "done":
                        break
                event_type = ""
                data_str = ""
    return frames


async def cleanup_conversation(
    client: httpx.AsyncClient, conv_id: str, headers: dict
):
    """清理对话，忽略 404。"""
    try:
        await client.delete(f"/api/conversations/{conv_id}", headers=headers)
    except Exception:
        pass
