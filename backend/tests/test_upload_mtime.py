"""R019-BF005 upload_mtime 中间件单元测试"""
import os

import pytest
from starlette.testclient import TestClient

from app.middleware.upload_mtime import upload_mtime_middleware


class FakeApp:
    """最小化 ASGI app 模拟，用于测试中间件逻辑。"""

    class State:
        def __init__(self, touched_paths):
            self._touched_paths = touched_paths
            self._upload_dir = "data/images"

        @property
        def image_manager(self):
            return self

        def touch(self, filepath):
            self._touched_paths.append(filepath)

    def __init__(self):
        self.touched_paths = []
        self.state = self.State(self.touched_paths)


class _FakeResponse:
    def __init__(self):
        self.status_code = 200


async def _call_next_ok(request):
    return _FakeResponse()


@pytest.mark.asyncio
async def test_upload_path_triggers_touch():
    """匹配 /api/uploads/ 路径时调用 touch。"""
    fake_app = FakeApp()

    from starlette.requests import Request
    from starlette.datastructures import URL

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/uploads/user1/abc.png",
        "query_string": b"",
        "headers": [],
        "app": fake_app,
    }
    request = Request(scope)

    response = await upload_mtime_middleware(request, _call_next_ok)

    assert response.status_code == 200
    assert len(fake_app.touched_paths) == 1
    assert fake_app.touched_paths[0] == os.path.join("data/images", "user1/abc.png")


@pytest.mark.asyncio
async def test_non_upload_path_skips_touch():
    """非 /api/uploads/ 路径直接放行，不调 touch。"""
    fake_app = FakeApp()

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/chat/stream",
        "query_string": b"",
        "headers": [],
        "app": fake_app,
    }
    from starlette.requests import Request
    request = Request(scope)

    response = await upload_mtime_middleware(request, _call_next_ok)

    assert response.status_code == 200
    assert len(fake_app.touched_paths) == 0


@pytest.mark.asyncio
async def test_touch_exception_does_not_block():
    """touch 抛异常时不阻断响应。"""
    fake_app = FakeApp()
    # 让 touch 抛异常
    fake_app.state._touched_paths = None  # type: ignore

    class BrokenTouch:
        _upload_dir = "data/images"

        @property
        def image_manager(self):
            return self

        def touch(self, filepath):
            raise RuntimeError("disk error")

    fake_app.state = BrokenTouch()  # type: ignore

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/uploads/user1/abc.png",
        "query_string": b"",
        "headers": [],
        "app": fake_app,
    }
    from starlette.requests import Request
    request = Request(scope)

    response = await upload_mtime_middleware(request, _call_next_ok)
    assert response.status_code == 200  # 不阻断
