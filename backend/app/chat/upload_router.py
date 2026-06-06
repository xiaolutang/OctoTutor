"""图片上传/删除 API"""
import os

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Request

from app.config import settings
from app.middleware.auth import UserContext, get_current_user

router = APIRouter(prefix="/api/chat", tags=["upload"])

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_SIZE_BYTES = settings.image_max_size_mb * 1024 * 1024


@router.post("/upload")
async def upload_image(
    file: UploadFile = File(...),
    user: UserContext = Depends(get_current_user),
    request: Request = None,
):
    # 1. 校验类型
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(400, f"不支持的文件类型: {file.content_type}，仅支持 jpg/png/webp")

    # 2. 校验大小
    content = await file.read()
    if len(content) > MAX_SIZE_BYTES:
        raise HTTPException(400, f"文件大小超过限制 ({settings.image_max_size_mb}MB)")

    # 3. 确定扩展名
    ext = (
        file.filename.rsplit(".", 1)[-1].lower()
        if file.filename and "." in file.filename
        else "png"
    )
    if ext == "jpeg":
        ext = "jpg"
    if ext not in {"jpg", "png", "webp"}:
        ext = "png"

    # 4. 保存
    image_manager = request.app.state.image_manager
    try:
        url = await image_manager.save(user.user_id, content, ext=ext)
    except Exception:
        raise HTTPException(500, "上传失败，请重试")

    # 5. 从 URL 提取 image_id（URL 格式: /api/uploads/{user_id}/{image_id}.{ext}）
    image_id = url.split("/")[-1].rsplit(".", 1)[0]

    return {"image_id": image_id, "url": url}


@router.delete("/upload/{image_id}")
async def delete_image(
    image_id: str,
    user: UserContext = Depends(get_current_user),
    request: Request = None,
):
    image_manager = request.app.state.image_manager
    deleted = await image_manager.delete(user.user_id, image_id)
    if not deleted:
        raise HTTPException(404, "图片不存在")
    return {"ok": True}
