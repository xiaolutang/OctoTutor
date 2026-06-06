"""图片管理模块 — 负责上传文件的存储、删除、LRU 清理和路径解析。"""

import asyncio
import os
import uuid
from pathlib import Path


class ImageManager:
    """管理用户上传的图片文件。

    磁盘布局::

        {upload_dir}/{user_id}/{image_id}.{ext}

    URL 格式::

        /api/uploads/{user_id}/{image_id}.{ext}
    """

    _upload_dir: str
    _max_bytes: int
    _total_size: int
    _lock: asyncio.Lock

    def __init__(self, upload_dir: str, max_storage_mb: int) -> None:
        self._upload_dir = upload_dir
        self._max_bytes = max_storage_mb * 1024 * 1024
        self._lock = asyncio.Lock()
        self._total_size = 0
        # 启动时扫描已有文件计算 _total_size
        os.makedirs(upload_dir, exist_ok=True)
        self._scan_existing_files()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def save(self, user_id: str, content: bytes, ext: str = "png") -> str:
        """保存图片文件并返回 URL 路径。

        Args:
            user_id: 用户 ID，用于隔离目录。
            content: 图片二进制内容。
            ext: 文件扩展名（不含点），默认 ``png``。

        Returns:
            URL 路径，格式 ``/api/uploads/{user_id}/{image_id}.{ext}``。
        """
        image_id = uuid.uuid4().hex
        filename = f"{image_id}.{ext}"
        user_dir = os.path.join(self._upload_dir, user_id)
        os.makedirs(user_dir, exist_ok=True)

        filepath = os.path.join(user_dir, filename)
        with open(filepath, "wb") as f:
            f.write(content)

        async with self._lock:
            self._total_size += len(content)
            if self._total_size > self._max_bytes:
                await self._cleanup_lru_locked()

        return f"/api/uploads/{user_id}/{filename}"

    async def delete(self, user_id: str, image_id: str) -> bool:
        """删除指定用户目录下的图片文件。

        Args:
            user_id: 用户 ID。
            image_id: 图片 ID（文件名前缀，不含扩展名）。

        Returns:
            是否成功删除。
        """
        user_dir = os.path.join(self._upload_dir, user_id)
        if not os.path.isdir(user_dir):
            return False

        # glob {image_id}.*
        pattern = f"{image_id}.*"
        for path in Path(user_dir).glob(pattern):
            file_size = os.path.getsize(path)
            os.remove(path)
            async with self._lock:
                self._total_size = max(0, self._total_size - file_size)
            return True

        return False

    def disk_path_from_url(self, url: str) -> str:
        """从 URL 解析磁盘绝对路径（不做归属校验）。

        供内部模块（recognition、middleware）使用。外部请求的归属校验
        由 resolve_filepath 或路由层负责。

        Args:
            url: URL 路径，格式 ``/api/uploads/{user_id}/{filename}``。

        Returns:
            磁盘绝对路径。

        Raises:
            ValueError: URL 格式无效。
        """
        prefix = "/api/uploads/"
        if not url.startswith(prefix):
            raise ValueError(f"Invalid upload URL: {url}")
        relative = url[len(prefix):]
        parts = relative.split("/", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid upload URL: {url}")
        return os.path.abspath(os.path.join(self._upload_dir, parts[0], parts[1]))

    def resolve_filepath(self, url: str, user_id: str) -> str:
        """从 URL 解析磁盘路径，校验 user_id 匹配。

        Args:
            url: URL 路径，格式 ``/api/uploads/{user_id}/{filename}``。
            user_id: 期望的 user_id，用于安全校验。

        Returns:
            磁盘绝对路径。

        Raises:
            ValueError: URL 格式无效或 user_id 不匹配。
        """
        # 去掉前缀 /api/uploads/
        prefix = "/api/uploads/"
        if not url.startswith(prefix):
            raise ValueError(f"Invalid upload URL: {url}")

        relative = url[len(prefix) :]  # e.g. "user123/abc.png"
        parts = relative.split("/", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid upload URL: {url}")

        url_user_id, filename = parts
        if url_user_id != user_id:
            raise ValueError(
                f"user_id mismatch: URL has '{url_user_id}', expected '{user_id}'"
            )

        return os.path.abspath(os.path.join(self._upload_dir, url_user_id, filename))

    async def cleanup_lru(self) -> int:
        """双水位线 LRU 清理：超过 _max_bytes 时删除最旧文件，直到低于 80%。

        Returns:
            删除的文件数量。
        """
        async with self._lock:
            return await self._cleanup_lru_locked()

    async def _cleanup_lru_locked(self) -> int:
        """内部清理逻辑，调用前必须已持有 _lock。"""
        low_watermark = int(self._max_bytes * 0.8)
        deleted = 0

        if self._total_size <= self._max_bytes:
            return 0

        # 收集所有文件
        all_files: list[tuple[float, str, int]] = []  # (mtime, path, size)
        for dirpath, _dirnames, filenames in os.walk(self._upload_dir):
            for fname in filenames:
                fpath = os.path.join(dirpath, fname)
                stat = os.stat(fpath)
                all_files.append((stat.st_mtime, fpath, stat.st_size))

        # 按 mtime 排序：旧 → 新
        all_files.sort(key=lambda x: x[0])

        for _mtime, fpath, fsize in all_files:
            if self._total_size <= low_watermark:
                break
            os.remove(fpath)
            self._total_size = max(0, self._total_size - fsize)
            deleted += 1

        return deleted

    @staticmethod
    def touch(filepath: str) -> None:
        """更新文件的 mtime 到当前时间。

        Args:
            filepath: 文件绝对路径。
        """
        if os.path.exists(filepath):
            os.utime(filepath)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _scan_existing_files(self) -> None:
        """启动时扫描已有文件，累加 _total_size。"""
        total = 0
        for dirpath, _dirnames, filenames in os.walk(self._upload_dir):
            for fname in filenames:
                fpath = os.path.join(dirpath, fname)
                total += os.path.getsize(fpath)
        self._total_size = total
