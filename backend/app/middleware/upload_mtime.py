"""图片访问中间件 — 访问 /api/uploads/ 时更新文件 mtime（LRU 热度标记）。"""

import os

from starlette.requests import Request
from starlette.responses import Response


async def upload_mtime_middleware(request: Request, call_next) -> Response:
    """在 /api/uploads/ 请求完成后 touch 文件，更新最近访问时间。

    touch 失败不阻断图片访问。
    """
    response = await call_next(request)

    if request.url.path.startswith("/api/uploads/"):
        try:
            image_manager = request.app.state.image_manager
            # URL 格式: /api/uploads/{user_id}/{filename}
            # 磁盘路径: data/uploads/{user_id}/{filename}
            relative = request.url.path[len("/api/uploads/"):]
            filepath = os.path.join("data/uploads", relative)
            image_manager.touch(filepath)
        except Exception:
            pass

    return response
