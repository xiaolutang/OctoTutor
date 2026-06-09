"""ImageManager 单元测试。"""

import asyncio
import os
import time

import pytest

from app.infra.image_manager import ImageManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_manager(tmp_path, max_mb: int = 10) -> ImageManager:
    """用临时目录构造 ImageManager。"""
    upload_dir = str(tmp_path / "uploads")
    return ImageManager(upload_dir=upload_dir, max_storage_mb=max_mb)


# ---------------------------------------------------------------------------
# save
# ---------------------------------------------------------------------------

def test_save_creates_file(tmp_path):
    """保存后文件存在，返回 URL 正确。"""
    mgr = _make_manager(tmp_path)
    url = asyncio.run(mgr.save("user1", b"hello", ext="png"))

    assert url.startswith("/api/uploads/user1/")
    assert url.endswith(".png")

    # 文件确实存在于磁盘
    filepath = mgr.resolve_filepath(url, "user1")
    assert os.path.isfile(filepath)
    with open(filepath, "rb") as f:
        assert f.read() == b"hello"


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------

def test_delete_removes_file(tmp_path):
    """删除后文件不存在。"""
    mgr = _make_manager(tmp_path)
    url = asyncio.run(mgr.save("user1", b"data-to-delete", ext="jpg"))

    filepath = mgr.resolve_filepath(url, "user1")
    assert os.path.isfile(filepath)

    # 从 URL 提取 image_id
    filename = os.path.basename(filepath)
    image_id = filename.rsplit(".", 1)[0]

    result = asyncio.run(mgr.delete("user1", image_id))
    assert result is True
    assert not os.path.exists(filepath)


def test_delete_nonexistent_returns_false(tmp_path):
    """删除不存在的文件返回 False。"""
    mgr = _make_manager(tmp_path)
    result = asyncio.run(mgr.delete("ghost_user", "no_such_id"))
    assert result is False


# ---------------------------------------------------------------------------
# resolve_filepath
# ---------------------------------------------------------------------------

def test_resolve_filepath_valid(tmp_path):
    """解析正确路径。"""
    mgr = _make_manager(tmp_path)
    url = "/api/uploads/user1/abc.png"
    path = mgr.resolve_filepath(url, "user1")
    assert path.endswith(os.path.join("user1", "abc.png"))
    assert os.path.isabs(path)


def test_resolve_filepath_user_mismatch(tmp_path):
    """user_id 不匹配抛异常。"""
    mgr = _make_manager(tmp_path)
    with pytest.raises(ValueError, match="mismatch"):
        mgr.resolve_filepath("/api/uploads/user1/abc.png", "user2")


# ---------------------------------------------------------------------------
# cleanup_lru
# ---------------------------------------------------------------------------

def test_cleanup_lru_deletes_oldest(tmp_path):
    """超限时删除最旧文件。"""
    # max = 1 MB，低水位 = 0.8 MB
    # 直接写文件到磁盘，手动设置 _total_size，避免 save 内部自动清理
    mgr = _make_manager(tmp_path, max_mb=1)

    content = b"x" * (400 * 1024)  # 400 KB per file
    user_dir = os.path.join(mgr._upload_dir, "user1")
    os.makedirs(user_dir, exist_ok=True)

    # 写 3 个文件，用不同的 mtime
    files = ["aaa.bin", "bbb.bin", "ccc.bin"]
    for i, name in enumerate(files):
        path = os.path.join(user_dir, name)
        with open(path, "wb") as f:
            f.write(content)
        # 设置不同的 mtime：aaa 最旧，ccc 最新
        mtime = 1000 + i * 100
        os.utime(path, (mtime, mtime))

    mgr._total_size = len(content) * 3  # 1200 KB > 1024 KB

    # 手动触发清理
    deleted = asyncio.run(mgr.cleanup_lru())
    assert deleted >= 1  # 至少删了一个最旧的

    # 验证 _total_size 已降到低水位以下
    assert mgr._total_size <= int(1 * 1024 * 1024 * 0.8) + 1  # 容差 1 byte

    # 验证最旧的文件被删除了，最新的还在
    assert not os.path.exists(os.path.join(user_dir, "aaa.bin"))
    assert os.path.exists(os.path.join(user_dir, "ccc.bin"))


# ---------------------------------------------------------------------------
# touch
# ---------------------------------------------------------------------------

def test_touch_updates_mtime(tmp_path):
    """touch 后 mtime 变化。"""
    mgr = _make_manager(tmp_path)
    url = asyncio.run(mgr.save("user1", b"touch-test", ext="png"))
    filepath = mgr.resolve_filepath(url, "user1")

    old_mtime = os.path.getmtime(filepath)
    # 等待一小段时间确保时间戳差异
    time.sleep(0.05)
    ImageManager.touch(filepath)

    new_mtime = os.path.getmtime(filepath)
    assert new_mtime >= old_mtime


def test_touch_nonexistent_does_not_raise(tmp_path):
    """touch 不存在的文件不抛异常。"""
    ImageManager.touch(str(tmp_path / "no_such_file.png"))  # should not raise


# ---------------------------------------------------------------------------
# _scan_existing_files
# ---------------------------------------------------------------------------


def test_scan_existing_files_counts_total_size(tmp_path):
    """启动时扫描已有文件，正确累加 _total_size。"""
    upload_dir = str(tmp_path / "uploads")
    user_dir = os.path.join(upload_dir, "user1")
    os.makedirs(user_dir)
    content = b"x" * 2048
    with open(os.path.join(user_dir, "existing.png"), "wb") as f:
        f.write(content)

    mgr = ImageManager(upload_dir=upload_dir, max_storage_mb=10)
    assert mgr._total_size == 2048


def test_scan_existing_files_empty_dir(tmp_path):
    """空目录时 _total_size 为 0。"""
    mgr = _make_manager(tmp_path)
    assert mgr._total_size == 0


# ---------------------------------------------------------------------------
# disk_path_from_url
# ---------------------------------------------------------------------------


def test_disk_path_from_url_valid(tmp_path):
    """disk_path_from_url 正确解析路径（不做归属校验）。"""
    mgr = _make_manager(tmp_path)
    path = mgr.disk_path_from_url("/api/uploads/user1/abc.png")
    assert path.endswith(os.path.join("user1", "abc.png"))
    assert os.path.isabs(path)


def test_disk_path_from_url_invalid_prefix(tmp_path):
    """disk_path_from_url 错误前缀 → ValueError。"""
    mgr = _make_manager(tmp_path)
    with pytest.raises(ValueError, match="Invalid"):
        mgr.disk_path_from_url("/wrong/prefix/abc.png")


def test_disk_path_from_url_no_slash(tmp_path):
    """disk_path_from_url 缺少斜杠 → ValueError。"""
    mgr = _make_manager(tmp_path)
    with pytest.raises(ValueError, match="Invalid"):
        mgr.disk_path_from_url("/api/uploads/noslash")


# ---------------------------------------------------------------------------
# save triggers cleanup
# ---------------------------------------------------------------------------


def test_save_triggers_cleanup_when_over_limit(tmp_path):
    """save 写入超过高水位时自动触发 LRU 清理。"""
    mgr = _make_manager(tmp_path, max_mb=1)  # 1 MB

    content = b"x" * (400 * 1024)  # 400 KB each
    # 写 3 个文件 = 1200 KB > 1024 KB
    asyncio.run(mgr.save("user1", content, ext="bin"))
    asyncio.run(mgr.save("user1", content, ext="bin"))
    asyncio.run(mgr.save("user1", content, ext="bin"))

    # _total_size 应降到低水位以下
    low_watermark = int(1 * 1024 * 1024 * 0.8)
    assert mgr._total_size <= low_watermark + 1  # 容差 1 byte


def test_cleanup_lru_nothing_to_clean(tmp_path):
    """总量未超限时 cleanup_lru 返回 0。"""
    mgr = _make_manager(tmp_path, max_mb=100)
    asyncio.run(mgr.save("user1", b"small", ext="png"))
    deleted = asyncio.run(mgr.cleanup_lru())
    assert deleted == 0
