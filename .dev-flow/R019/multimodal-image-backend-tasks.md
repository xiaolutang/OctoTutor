---
version: "1.0"
type: tasks
topic: multimodal-image-backend
requirement_cycle: R019
workflow:
  evaluate_provider: direct
  mode: auto
status: archived
---

# 多模态图片识别 — 后端任务清单

基于 [analysis](analysis/2026-06-05--multimodal-image.md) 和 [backend design](analysis/2026-06-05--multimodal-image-backend.md)。

全局约束：
- Graph 拓扑不变、AgentState 不变，blocked: `agent/graph.py`
- 不引入数据库表，图片管理纯文件系统
- HumanMessage content 始终为纯文本（识别在 stream_router 预处理）
- SSE 事件类型不变（`thinking` 是独立事件，不是 StatusPayload stage）
- python-multipart 需确认在 requirements.txt 中

---

## 执行顺序

1. ✅ R019-BF001 — config.py + requirements.txt 配置（无依赖）
2. ✅ R019-BF002 — schemas.py 数据模型扩展（无依赖）
3. ✅ R019-BF003 — image_manager.py 图片管理模块（依赖 BF001）
4. ✅ R019-BF004 — recognition.py + prompts.py 识别层（依赖 BF001）
5. ✅ R019-BF005 — upload_mtime.py 图片访问中间件（依赖 BF003）
6. ✅ R019-BB001 — upload_router.py 上传/删除 API（依赖 BF002, BF003）
7. ✅ R019-BB002 — stream_router.py 图片预处理（依赖 BF002, BF004）
8. ✅ R019-BB003 — conversation_utils.py + conversation_router.py 序列化+清理（依赖 BF002, BF003）
9. ✅ R019-BB004 — main.py 集成（依赖所有以上）

---

## R019-BF001：config.py + requirements.txt — 图片配置 `✅ 已完成`

- 文件：`backend/app/config.py`, `backend/requirements.txt`
- 改动类型：修改
- domain: infra
- task_layer: foundation
- depends_on: []
- priority: 5
- risk_tags: []
- smoke_required: false
- mode: direct
- status: completed
- acceptance_criteria:
  - Settings 类新增 vision_model / image_max_size_mb / image_max_storage_mb 字段
  - requirements.txt 包含 python-multipart
  - `python -c "from app.config import settings; print(settings.vision_model)"` 不报错
- test_tasks:
  - type: unit
    description: 验证新配置字段默认值正确
    scenarios: [默认值测试]
- contract_refs: []
- decision_refs: []
- blocked_files: []

### BF001.1 config.py 新增图片配置 `⬜`

在 `Settings` 类的 `data_images_dir` 之后新增：

```python
# R019: 图片识别配置
vision_model: str = "qwen3-vl-flash"
image_max_size_mb: int = 10           # 单张图片大小上限
image_max_storage_mb: int = 1000      # uploads 目录高水位（MB），低水位 = 80%
```

### BF001.2 requirements.txt 添加 python-multipart `⬜`

在 `fastapi>=0.115.0` 之后添加：

```
python-multipart>=0.0.9
```

---

## R019-BF002：schemas.py — 数据模型扩展 `✅ 已完成`

- 文件：`backend/app/chat/schemas.py`
- 改动类型：修改
- domain: backend
- task_layer: foundation
- depends_on: []
- priority: 5
- risk_tags: []
- smoke_required: false
- mode: direct
- status: completed
- acceptance_criteria:
  - ImageRef 模型定义存在且包含 url + image_id 字段
  - ChatRequest 新增 images 字段（default_factory=list, max_length=3）
  - ApiMessage 新增 images 字段（default_factory=list）
  - StatusPayload.stage 扩展为 `Literal["recognizing", "retrieving", "generating"]`
  - 现有测试不受影响（images 默认空列表）
- test_tasks:
  - type: unit
    description: 验证 ChatRequest images 字段默认值、max_length 校验
    scenarios: [默认空列表, 超过3张报错, 空question仍需min_length=1]
- contract_refs: []
- decision_refs: [DEC-rag-012]
- blocked_files: []

### BF002.1 新增 ImageRef 模型 `⬜`

在 `ChatRequest` 类之前新增：

```python
class ImageRef(BaseModel):
    """图片引用"""
    url: str
    image_id: str
```

### BF002.2 ChatRequest 扩展 images `⬜`

在 `conversation_id` 字段后新增：

```python
images: list[ImageRef] = Field(default_factory=list, max_length=3, description="图片引用列表")
```

### BF002.3 ApiMessage 扩展 images `⬜`

在 `thinking_steps` 字段后新增：

```python
images: list[ImageRef] = Field(default_factory=list)
```

### BF002.4 StatusPayload.stage 扩展 `⬜`

将 `stage: Literal["retrieving", "generating"]` 改为：

```python
stage: Literal["recognizing", "retrieving", "generating"]
```

---

## R019-BF003：image_manager.py — 图片管理模块 `✅ 已完成`

- 文件：`backend/app/infra/image_manager.py`
- 改动类型：新建
- domain: infra
- task_layer: foundation
- depends_on: [R019-BF001]
- priority: 4
- risk_tags: [filesystem]
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - save() 写入文件到 data/uploads/{user_id}/{uuid}.{ext}，返回 URL 路径
  - delete() 遍历 user_id 目录查找并删除文件
  - resolve_filepath() 从 URL 解析磁盘路径，校验 user_id 匹配
  - cleanup_lru() 双水位线策略 + asyncio.Lock 并发安全
  - touch() 更新文件 mtime（os.utime）
  - 单元测试覆盖 save/delete/cleanup_lru/touch
- test_tasks:
  - type: unit
    description: ImageManager 核心方法测试
    scenarios: [save 创建文件, delete 删除文件, delete 不存在返回 false, resolve_filepath 校验, cleanup_lru 超限清理, touch 更新 mtime]
- contract_refs: []
- decision_refs: []
- blocked_files: []

### BF003.1 ImageManager 类骨架 `⬜`

```python
import asyncio
import os
import uuid
from pathlib import Path

class ImageManager:
    _total_size: int = 0
    _lock: asyncio.Lock

    def __init__(self, upload_dir: str, max_storage_mb: int): ...
    async def save(self, user_id: str, image_id: str, ext: str, content: bytes) -> str: ...
    async def delete(self, user_id: str, image_id: str) -> bool: ...
    def resolve_filepath(self, url: str, user_id: str) -> str: ...
    async def cleanup_lru(self) -> int: ...
    def touch(self, filepath: str) -> None: ...
```

save 逻辑：
1. 构造路径 `data/uploads/{user_id}/{image_id}.{ext}`，os.makedirs 确保目录
2. 写入 bytes 到文件
3. 持锁更新 _total_size += len(content)，超高水位则触发 cleanup_lru
4. 返回 URL `/api/uploads/{user_id}/{image_id}.{ext}`

delete 逻辑：
1. 遍历 `data/uploads/{user_id}/` 目录，glob `{image_id}.*`
2. 找到则 os.remove + 持锁更新 _total_size -= file_size
3. 返回 bool

resolve_filepath 逻辑：
1. 从 URL 解析出 user_id 和 filename
2. 校验路径中 user_id == 传入 user_id
3. 返回磁盘绝对路径

cleanup_lru 逻辑：
1. 持锁检查 _total_size > max_storage_mb * 1024 * 1024
2. 收集所有文件，按 mtime 排序（旧→新）
3. 逐个删除最旧的，_total_size 递减，低于低水位（80%）停止
4. 返回删除数量

touch 逻辑：
```python
def touch(self, filepath: str) -> None:
    if os.path.exists(filepath):
        os.utime(filepath)
```

---

## R019-BF004：recognition.py + prompts.py — 识别层 `✅ 已完成`

- 文件：`backend/app/infra/recognition.py`（新建）, `backend/app/agent/prompts.py`（修改）
- 改动类型：新建 + 修改
- domain: infra
- task_layer: foundation
- depends_on: [R019-BF001]
- priority: 4
- risk_tags: [network]
- smoke_required: false
- mode: direct
- status: pending
- acceptance_criteria:
  - RecognitionProvider Protocol 定义 recognize(image_urls, question) -> str
  - VLMRecognitionProvider 实现类可调用 Vision LLM API
  - recognize() 从磁盘读文件转 base64，构造 OpenAI Vision 格式
  - 30s 超时设置
  - RECOGNITION_SYSTEM_PROMPT 常量定义
  - 单元测试覆盖 recognize 正常/超时/失败降级
- test_tasks:
  - type: unit
    description: RecognitionProvider 测试
    scenarios: [mock VLM 成功返回文本, mock VLM 超时抛异常, 多图片单次调用]
- contract_refs: []
- decision_refs: []
- blocked_files: []

### BF004.1 RecognitionProvider Protocol `⬜`

```python
from typing import Protocol

class RecognitionProvider(Protocol):
    async def recognize(self, image_urls: list[str], question: str) -> str: ...
```

### BF004.2 VLMRecognitionProvider 实现 `⬜`

```python
from openai import AsyncOpenAI

class VLMRecognitionProvider:
    def __init__(self, api_key: str, base_url: str, model: str, upload_dir: str): ...

    async def recognize(self, image_urls: list[str], question: str) -> str:
        # 1. 根据 URL 路径定位磁盘文件
        # 2. 读文件 → base64 编码
        # 3. 构造 OpenAI Vision 格式 messages（多图单次调用）
        # 4. AsyncOpenAI.chat.completions.create（timeout=30s）
        # 5. 返回识别文本
```

### BF004.3 prompts.py 新增 RECOGNITION_SYSTEM_PROMPT `⬜`

在 `prompts.py` 末尾新增识别专用系统提示词常量。要求 LLM 将图片中的数学题目、公式、文字内容完整转录为纯文本。

---

## R019-BF005：upload_mtime.py — 图片访问中间件 `🔧 进行中`

- 文件：`backend/app/middleware/upload_mtime.py`
- 改动类型：新建
- domain: infra
- task_layer: foundation
- depends_on: [R019-BF003]
- priority: 3
- risk_tags: []
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - 中间件拦截 GET /api/uploads/ 请求
  - call_next() 放行后调 image_manager.touch(filepath)
  - 非 /api/uploads/ 请求直接放行
  - touch 失败不阻断图片访问（try/except）
- test_tasks:
  - type: unit
    description: 中间件拦截逻辑测试
    scenarios: [匹配路径调 touch, 非匹配路径放行, touch 异常不阻断]
- contract_refs: []
- decision_refs: []
- blocked_files: []

### BF005.1 upload_mtime_middleware 函数 `⬜`

```python
from starlette.middleware.base import BaseHTTPMiddleware
# 或使用 @app.middleware("http") 函数式

async def upload_mtime_middleware(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/uploads/"):
        try:
            filepath = ...  # 从 request.url.path 解析磁盘路径
            request.app.state.image_manager.touch(filepath)
        except Exception:
            pass
    return response
```

---

## R019-BB001：upload_router.py — 上传/删除 API `✅ 已完成`

- 文件：`backend/app/chat/upload_router.py`
- 改动类型：新建
- domain: backend
- task_layer: business
- depends_on: [R019-BF002, R019-BF003]
- priority: 3
- risk_tags: [auth]
- smoke_required: true
- mode: direct
- status: completed
- acceptance_criteria:
  - POST /api/chat/upload 接受 multipart/form-data，返回 {image_id, url}
  - DELETE /api/chat/upload/{image_id} 删除文件，返回 200 {ok: true}
  - JWT 校验 user_id，归属校验通过路径匹配
  - 文件类型限制 jpg/jpeg/png/webp，大小限制 10MB
  - 上传异常时即时清理部分文件（try/except → os.remove）
  - DELETE 越权返回 404
- test_tasks:
  - type: integration
    description: 上传/删除 API 集成测试
    scenarios: [上传 jpg 成功, 上传非图片拒绝, 超大文件拒绝, 删除成功, 删除不存在的图片 404, 其他用户 token 删除 404]
- contract_refs: []
- decision_refs: []
- blocked_files: []

### BB001.1 POST /api/chat/upload 端点 `⬜`

```python
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Request
from app.middleware.auth import get_current_user

router = APIRouter(prefix="/api/chat", tags=["upload"])

@router.post("/upload")
async def upload_image(
    file: UploadFile = File(...),
    user: UserContext = Depends(get_current_user),
    request: Request = None,
):
    # 1. 校验类型（jpg/jpeg/png/webp）
    # 2. 校验大小（≤ image_max_size_mb）
    # 3. 生成 UUID + ext
    # 4. image_manager.save(user_id, uuid, ext, content)
    # 5. return {"image_id": uuid, "url": url}
    # 异常: catch → if os.path.exists(filepath): os.remove(filepath); raise
```

### BB001.2 DELETE /api/chat/upload/{image_id} 端点 `⬜`

```python
@router.delete("/upload/{image_id}")
async def delete_image(
    image_id: str,
    user: UserContext = Depends(get_current_user),
    request: Request = None,
):
    # 1. image_manager.delete(user_id, image_id)
    # 2. 成功 → {"ok": True}
    # 3. 不存在 → 404
```

---

## R019-BB002：stream_router.py — 图片预处理 `✅ 已完成`

- 文件：`backend/app/chat/stream_router.py`
- 改动类型：修改
- domain: backend
- task_layer: business
- depends_on: [R019-BF002, R019-BF004]
- priority: 3
- risk_tags: [streaming, network]
- smoke_required: true
- mode: direct
- status: completed
- acceptance_criteria:
  - body.images 非空时，校验图片文件存在
  - SSE 立即建立，后台任务发 recognizing → VLM 识别 → Graph
  - VLM 失败降级为纯文字消息（recognized_text=""，用 question 继续）
  - HumanMessage content 为纯文本，additional_kwargs 存 images 引用（含 url + image_id）
  - body.images 为空时行为与现有一致（零影响）
  - 现有测试全部通过
- test_tasks:
  - type: integration
    description: stream 图片预处理集成测试
    scenarios: [含图片→VLM调用→Graph正常运行, 无图片→零影响, VLM失败→降级纯文字, 图片不存在→400]
- contract_refs: []
- decision_refs: [DEC-rag-012-rev1]
- blocked_files: [backend/app/agent/graph.py]

### BB002.1 stream_chat 新增图片校验 `⬜`

在 `input_state` 构造之前（约 line 181），新增图片校验逻辑：

```python
# 校验 images
if body.images:
    image_manager = http_request.app.state.image_manager
    for img in body.images:
        filepath = image_manager.resolve_filepath(img.url, user.user_id)
        if not os.path.exists(filepath):
            raise HTTPException(400, "图片不存在，请重新上传")
```

### BB002.2 替换 input_state 构造为后台任务 `⬜`

将现有的直接构造 input_state + 启动 _run_graph 改为先启动后台任务（含 VLM 识别），再启动 Graph：

```python
# 替换现有 input_state 构造 + _run_graph 启动
# 改为:
if body.images:
    # 启动含识别的后台任务
    task = asyncio.create_task(
        _run_with_recognition(graph, body, user, config, queue, cancel_event, db, ...)
    )
else:
    # 现有逻辑不变
    task = asyncio.create_task(
        _run_graph(graph, input_state, config, queue, ...)
    )
```

### BB002.3 _run_with_recognition 后台任务 `⬜`

新增函数：

```python
async def _run_with_recognition(graph, body, user, config, queue, cancel_event, db, ...):
    recognized_text = ""
    image_refs_kwargs = []

    # 1. SSE status: recognizing
    await queue.put(StreamEvent(type="status", data=StatusPayload(stage="recognizing", message="正在识别图片...")))

    # 2. 调 VLM（30s 超时）
    try:
        recognized_text = await app_state.recognition_provider.recognize(
            [img.url for img in body.images], body.question
        )
        image_refs_kwargs = [{"url": img.url, "image_id": img.image_id} for img in body.images]
    except Exception:
        logger.warning("Vision LLM failed, degrading to text-only")
        recognized_text = ""

    # 3. 构造 HumanMessage
    combined = f"{recognized_text}\n\n{body.question}" if recognized_text else body.question
    human_msg = HumanMessage(
        content=combined,
        additional_kwargs={"images": image_refs_kwargs} if image_refs_kwargs else {}
    )
    input_state = {"messages": [human_msg], "question": combined}

    # 4. 启动 Graph（复用现有 _run_graph）
    await _run_graph(graph, input_state, config, queue, cancel_event, db, ...)
```

---

## R019-BB003：conversation_utils.py + conversation_router.py — 序列化+清理 `✅ 已完成`

- 文件：`backend/app/chat/conversation_utils.py`, `backend/app/chat/conversation_router.py`
- 改动类型：修改
- domain: backend
- task_layer: business
- depends_on: [R019-BF002, R019-BF003]
- priority: 3
- risk_tags: []
- smoke_required: true
- mode: direct
- status: completed
- acceptance_criteria:
  - to_api_message 从 additional_kwargs 提取 images → ApiMessage.images
  - delete_conversation 新增图片文件清理（失败只 warning 不阻断）
  - 现有测试全部通过
- test_tasks:
  - type: unit
    description: to_api_message images 提取测试
    scenarios: [有 images 提取成功, 无 images 返回空列表, images 格式异常静默跳过]
  - type: integration
    description: delete_conversation 图片清理测试
    scenarios: [删除含图片对话→文件被删除, 删除无图片对话→无报错, 文件删除失败→不阻断对话删除]
- contract_refs: []
- decision_refs: []
- blocked_files: []

### BB003.1 to_api_message 提取 images `⬜`

在 `conversation_utils.py` 的 `to_api_message` 函数中，在 sources 处理之后、return 之前新增：

```python
# 提取 images
images = []
raw_images = additional_kwargs.get("images", [])
if raw_images:
    for img in raw_images:
        if isinstance(img, dict):
            try:
                images.append(ImageRef(**img))
            except Exception:
                pass
```

在 return ApiMessage(...) 中新增 `images=images`。

### BB003.2 delete_conversation 新增图片清理 `⬜`

在 `conversation_router.py` 的 `delete_conversation` 函数中，在 checkpoint 清理之后、return 之前新增：

```python
# 清理关联图片文件（失败不阻断）
try:
    image_manager = request.app.state.image_manager
    # 从 checkpoint 消息中提取图片 URL → 逐个删除
    # 参考 analysis 场景 7: 从 messages additional_kwargs 提取 images → 解析路径 → delete
except Exception as e:
    logger.warning(f"[conversation] image cleanup failed for {conversation_id}: {e}")
```

---

## R019-BB004：main.py — 集成 `✅ 已完成`

- 文件：`backend/app/main.py`
- 改动类型：修改
- domain: backend
- task_layer: business
- depends_on: [R019-BF003, R019-BF004, R019-BF005, R019-BB001, R019-BB002, R019-BB003]
- priority: 5
- risk_tags: []
- smoke_required: true
- mode: direct
- status: completed
- acceptance_criteria:
  - StaticFiles 挂载 /api/uploads
  - upload_mtime 中间件注册
  - upload_router 注册
  - lifespan 中 ImageManager + VLMRecognitionProvider 初始化
  - lifespan 中 ImageManager.cleanup_lru() 启动清理
  - 启动后 curl /api/health 返回 200
  - 图片上传→访问→删除完整流程可运行
- test_tasks:
  - type: integration
    description: 启动冒烟测试
    scenarios: [应用启动不报错, StaticFiles 可访问, upload API 可调用]
- contract_refs: []
- decision_refs: []
- blocked_files: []

### BB004.1 imports 新增 `⬜`

```python
from fastapi.staticfiles import StaticFiles
from app.chat.upload_router import router as upload_router
from app.infra.image_manager import ImageManager
from app.infra.recognition import VLMRecognitionProvider
from app.middleware.upload_mtime import upload_mtime_middleware
```

### BB004.2 lifespan 新增初始化 `⬜`

在 `create_graph()` 之前，新增：

```python
# R019: 初始化 VLMRecognitionProvider
recognition_provider = VLMRecognitionProvider(
    api_key=settings.newapi_api_key,
    base_url=settings.newapi_base_url,
    model=settings.vision_model,
    upload_dir="data/uploads",
)
application.state.recognition_provider = recognition_provider
print(f"[startup] RecognitionProvider initialized (model={settings.vision_model})")

# R019: 初始化 ImageManager
image_manager = ImageManager(
    upload_dir="data/uploads",
    max_storage_mb=settings.image_max_storage_mb,
)
application.state.image_manager = image_manager

# R019: 启动时 LRU 清理
await image_manager.cleanup_lru()
print("[startup] ImageManager initialized + LRU cleanup done")
```

### BB004.3 中间件 + StaticFiles + Router 注册 `⬜`

在 `app = FastAPI(...)` 之后，router 注册之前：

```python
# R019: 图片访问 mtime 更新中间件
app.middleware("http")(upload_mtime_middleware)

# R019: StaticFiles 挂载
app.mount("/api/uploads", StaticFiles(directory="data/uploads"), name="uploads")

# R019: upload router
app.include_router(upload_router)
```

### BB004.4 确保 data/uploads 目录存在 `⬜`

在 lifespan 初始化 ImageManager 之前：

```python
os.makedirs("data/uploads", exist_ok=True)
```
