---
version: "1.0"
type: tasks
topic: conversation-management
requirement_cycle: R009
workflow:
  evaluate_provider: local
  mode: auto
status: planned
---

# 多对话管理 — 后端 任务清单

基于 design.md 设计，列出需要创建/修改的具体细节。
全局约束：SQLAlchemy 2.0 async ORM，复用 psycopg 3 驱动，conversation_id 与 LangGraph thread_id 一致。

---

## 执行顺序

1. ⬜ 任务 1 — infra/database.py + domain/models.py — Conversation 模型 + DB 引擎（无依赖）
   - ⬜ 1.1 新建 infra/database.py
   - ⬜ 1.2 修改 domain/models.py
   - ⬜ 1.3 添加 sqlalchemy 依赖
2. ⬜ 任务 2 — infra/conversation_repo.py — Conversation CRUD 数据访问层（依赖任务 1）
   - ⬜ 2.1 新建 conversation_repo.py
3. ⬜ 任务 3 — infra/llm.py — 非流式异步方法（无依赖）
   - ⬜ 3.1 修改 llm.py 新增 generate_title 方法
4. ⬜ 任务 4 — chat/schemas.py + chat/errors.py — Schema + 错误码（依赖任务 1）
   - ⬜ 4.1 修改 schemas.py
   - ⬜ 4.2 修改 errors.py
5. ⬜ 任务 5 — chat/dependencies.py — get_db session 注入（依赖任务 1）
   - ⬜ 5.1 修改 dependencies.py
6. ⬜ 任务 6 — chat/conversation_router.py — CRUD API 端点（依赖任务 2, 4, 5）
   - ⬜ 6.1 新增 GET /api/conversations 对话列表
   - ⬜ 6.2 新增 PATCH /api/conversations/{id} 对话更新
   - ⬜ 6.3 新增 DELETE /api/conversations/{id} 对话删除
7. ⬜ 任务 7 — chat/stream_router.py — 自动创建 + 标题推送（依赖任务 2, 3, 5）
   - ⬜ 7.1 init 阶段创建 conversation 记录
   - ⬜ 7.2 done 后生成标题并推送 title 事件
   - ⬜ 7.3 更新 updated_at 和 message_count
8. ⬜ 任务 8 — main.py — Lifespan DB 初始化（依赖任务 1）
   - ⬜ 8.1 lifespan 中初始化 SQLAlchemy engine
   - ⬜ 8.2 自动建表
   - ⬜ 8.3 shutdown 时释放 engine
9. ⬜ 任务 9 — architecture.md — 文档更新（依赖任务 6, 7, 8）
   - ⬜ 9.1 更新系统拓扑
   - ⬜ 9.2 新增关键决策
   - ⬜ 9.3 更新权威边界
   - ⬜ 9.4 更新不变量
   - ⬜ 9.5 更新禁止模式
10. ⬜ 最后 — 编译验证 + 测试路径

---

## R009-BF001：infra/database.py + domain/models.py — Conversation 模型 + DB 引擎 `✅ 已完成`

- 文件：
  - `backend/app/infra/database.py`（新建）
  - `backend/app/domain/models.py`（修改）
  - `backend/requirements.txt`（修改）
- 改动类型：新建 / 修改 / 配置
- domain: backend
- task_layer: foundation
- depends_on: []
- priority: 5
- risk_tags: [first_use]
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - `from app.infra.database import get_db, engine` 不报错
  - `from app.domain.models import Conversation` 不报错
  - Conversation model 字段与设计文档一致
  - SQLAlchemy async engine 使用 `postgresql+psycopg://` 驱动
  - `get_db()` 返回 async generator，yield AsyncSession
- test_tasks:
  - type: unit
    description: Conversation model 可实例化并序列化
    scenarios: [字段默认值正确, id 为 VARCHAR(36)]
- contract_refs: [".dev-flow/R009/analysis/2026-05-24--R009-conversation-management-backend.md"]
- decision_refs: []
- blocked_files: []

### BF001.1 新建 infra/database.py `⬜`

新建 SQLAlchemy 2.0 async engine + session factory：

```python
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.config import settings

engine = create_async_engine(
    settings.database_url.replace("postgresql://", "postgresql+psycopg://"),
    pool_size=5,
)

async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db():
    async with async_session_factory() as session:
        yield session

async def create_tables():
    from app.domain.models import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

### BF001.2 修改 domain/models.py `⬜`

新增 Conversation SQLAlchemy model + DeclarativeBase：

```python
from sqlalchemy import String, Boolean, Integer, DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from datetime import datetime

class Base(DeclarativeBase):
    pass

class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="新对话")
    pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    pinned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
```

保留现有 `SourceReference` 不变。

### BF001.3 添加 sqlalchemy 依赖 `⬜`

在 `backend/requirements.txt` 末尾添加：

```
# 对话管理 ORM (R009)
sqlalchemy>=2.0
```

---

## R009-BF002：infra/conversation_repo.py — Conversation CRUD 数据访问层 `✅ 已完成`

- 文件：`backend/app/infra/conversation_repo.py`（新建）
- 改动类型：新建
- domain: backend
- task_layer: foundation
- depends_on: [R009-BF001]
- priority: 5
- risk_tags: []
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - `create()` 插入一条 conversation 记录
  - `get_by_id()` 根据 id + user_id 查询，返回 Conversation 或 None
  - `list_by_user()` 支持游标分页 + 置顶排序
  - `update()` 更新 title/pinned/pinned_at 字段
  - `delete()` 删除指定记录
  - `count_pinned()` 返回用户置顶数
  - 所有方法使用 async session 参数
- test_tasks:
  - type: unit
    description: ConversationRepo CRUD 操作测试
    scenarios: [创建对话, 按ID查询存在/不存在, 列表分页, 更新标题, 更新置顶, 删除, 置顶计数]
- contract_refs: [".dev-flow/R009/analysis/2026-05-24--R009-conversation-management-backend.md"]
- decision_refs: []
- blocked_files: []

### BF002.1 新建 conversation_repo.py `⬜`

纯数据访问层，不包含业务逻辑。所有方法接收 `AsyncSession` 参数：

```python
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.models import Conversation

class ConversationRepo:
    @staticmethod
    async def create(session: AsyncSession, conversation: Conversation) -> Conversation: ...

    @staticmethod
    async def get_by_id(session: AsyncSession, conv_id: str, user_id: str) -> Conversation | None: ...

    @staticmethod
    async def list_by_user(session: AsyncSession, user_id: str, cursor: str | None = None, limit: int = 20) -> tuple[list[Conversation], bool]: ...
    # 首页：查全部置顶 + 前 (limit+1) 条普通对话（多查 1 条判断 has_more）
    # 翻页：解 cursor（base64 -> updated_at|id），查普通对话 WHERE updated_at < cursor_time

    @staticmethod
    async def update(session: AsyncSession, conv_id: str, user_id: str, **fields) -> Conversation | None: ...

    @staticmethod
    async def delete_by_id(session: AsyncSession, conv_id: str, user_id: str) -> bool: ...

    @staticmethod
    async def count_pinned(session: AsyncSession, user_id: str) -> int: ...

    @staticmethod
    async def update_message_stats(session: AsyncSession, conv_id: str, message_count_delta: int = 2) -> None: ...
```

游标格式：`{updated_at_iso}|{conversation_id}` 的 base64 编码。

---

## R009-BF003：infra/llm.py — 非流式异步方法 `✅ 已完成`

- 文件：`backend/app/infra/llm.py`（修改）
- 改动类型：修改
- domain: backend
- task_layer: foundation
- depends_on: []
- priority: 4
- risk_tags: [network]
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - 新增 `async generate_title(self, user_message: str) -> str | None` 方法
  - 使用 `AsyncOpenAI.chat.completions.create`（非流式，stream=False）
  - timeout=5s，失败返回 None
  - 不影响现有 `generate()` 和 `generate_stream()` 方法
- test_tasks:
  - type: unit
    description: generate_title 方法测试
    scenarios: [正常返回标题, 超时返回None, 异常返回None, 标题去引号]
- contract_refs: [".dev-flow/R009/analysis/2026-05-24--R009-conversation-management-backend.md"]
- decision_refs: []
- blocked_files: []

### BF003.1 修改 llm.py 新增 generate_title 方法 `⬜`

在 `LLMGenerator` 类中新增方法：

```python
async def generate_title(self, user_message: str) -> str | None:
    """根据首条用户消息生成对话标题（非流式，5s timeout）"""
    try:
        response = await self.async_client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "请用不超过20个字概括以下问题的核心主题，直接输出标题，不要加引号。"},
                {"role": "user", "content": user_message},
            ],
            max_tokens=50,
            timeout=5.0,
        )
        title = response.choices[0].message.content.strip().strip('"').strip("'")
        return title if title else None
    except Exception as e:
        logger.warning(f"[llm] title generation failed: {e}")
        return None
```

---

## R009-BF004：chat/schemas.py + chat/errors.py — Schema + 错误码 `✅ 已完成`

- 文件：
  - `backend/app/chat/schemas.py`（修改）
  - `backend/app/chat/errors.py`（修改）
- 改动类型：修改
- domain: backend
- task_layer: foundation
- depends_on: [R009-BF001]
- priority: 4
- risk_tags: []
- smoke_required: false
- mode: direct
- status: pending
- acceptance_criteria:
  - ConversationItemResponse schema 包含 id/title/pinned/pinned_at/message_count/created_at/updated_at
  - ConversationListResponse schema 包含 items/cursor/has_more
  - ConversationUpdateRequest schema 包含可选 title 和 pinned
  - ConversationErrorCode 枚举包含 03901-03904
  - ERROR_REGISTRY 包含对应错误定义
  - 现有 schemas 和 errors 不受影响
- test_tasks:
  - type: unit
    description: Schema 序列化和错误码测试
    scenarios: [ConversationListResponse 空列表, ConversationUpdateRequest 仅title, 错误码03901-03904存在]
- contract_refs: [".dev-flow/R009/analysis/2026-05-24--R009-conversation-management-backend.md"]
- decision_refs: []
- blocked_files: []

### BF004.1 修改 schemas.py `⬜`

新增 Conversation 相关 Pydantic schema：

```python
from datetime import datetime

class ConversationItemResponse(BaseModel):
    id: str
    title: str
    pinned: bool
    pinned_at: datetime | None = None
    message_count: int
    created_at: datetime
    updated_at: datetime

class ConversationListResponse(BaseModel):
    items: list[ConversationItemResponse]
    cursor: str | None = None
    has_more: bool = False

class ConversationUpdateRequest(BaseModel):
    title: str | None = None
    pinned: bool | None = None
```

### BF004.2 修改 errors.py `⬜`

新增对话管理模块错误码（03xxx）：

```python
class ConversationErrorCode(Enum):
    NOT_FOUND = "03901"        # 对话不存在
    PIN_LIMIT = "03902"        # 置顶超限
    TITLE_INVALID = "03903"    # 标题校验失败
    CREATE_FAILED = "03904"    # 对话创建失败

CONVERSATION_ERROR_REGISTRY: dict[ConversationErrorCode, ErrorDef] = {
    ConversationErrorCode.NOT_FOUND: ErrorDef("03901", "对话不存在", "refresh"),
    ConversationErrorCode.PIN_LIMIT: ErrorDef("03902", "最多置顶 5 条对话", "unpin_first"),
    ConversationErrorCode.TITLE_INVALID: ErrorDef("03903", "标题不能为空且不超过200字", "retry"),
    ConversationErrorCode.CREATE_FAILED: ErrorDef("03904", "对话创建失败", "retry"),
}

def make_conversation_error(code: ConversationErrorCode) -> dict: ...
```

与现有 `ChatErrorCode` / `ERROR_REGISTRY` / `make_error` 并列，不修改现有定义。

---

## R009-BF005：chat/dependencies.py — get_db session 注入 `✅ 已完成`

- 文件：`backend/app/chat/dependencies.py`（修改）
- 改动类型：修改
- domain: backend
- task_layer: foundation
- depends_on: [R009-BF001]
- priority: 4
- risk_tags: []
- smoke_required: false
- mode: direct
- status: pending
- acceptance_criteria:
  - 新增 `get_db()` 函数，返回 `AsyncGenerator[AsyncSession, None]`
  - 通过 `Request.app.state.db_session_factory` 获取 session factory
  - 现有依赖注入函数不受影响
- test_tasks:
  - type: unit
    description: get_db 依赖注入测试
    scenarios: [正常yield session, session关闭]
- contract_refs: []
- decision_refs: []
- blocked_files: []

### BF005.1 修改 dependencies.py `⬜`

新增 `get_db` 依赖注入函数：

```python
from sqlalchemy.ext.asyncio import AsyncSession

async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """注入 SQLAlchemy async session（conversation CRUD 使用）"""
    factory = request.app.state.db_session_factory
    async with factory() as session:
        yield session
```

---

## R009-BB001：chat/conversation_router.py — CRUD API 端点 `✅ 已完成`

- 文件：`backend/app/chat/conversation_router.py`（修改）
- 改动类型：修改
- domain: backend
- task_layer: business
- depends_on: [R009-BF002, R009-BF004, R009-BF005]
- priority: 5
- risk_tags: [auth]
- smoke_required: true
- mode: negotiated
- status: pending
- acceptance_criteria:
  - `GET /api/conversations` 返回分页列表（items + cursor + has_more）
  - `PATCH /api/conversations/{id}` 重命名成功返回 200 + 更新后的对话数据
  - `PATCH /api/conversations/{id}` 置顶成功，pinned=true + pinned_at 有值
  - `PATCH /api/conversations/{id}` 置顶超限返回 400 + 错误码 03902
  - `PATCH /api/conversations/{id}` 标题为空或超长返回 400 + 错误码 03903
  - `DELETE /api/conversations/{id}` 删除成功返回 204
  - `DELETE /api/conversations/{id}` 不存在返回 404
  - 所有端点验证 user_id 归属
  - 现有 GET /api/conversations/current 不受影响
- test_tasks:
  - type: integration
    description: 对话 CRUD API 端到端测试
    scenarios: [列表首页, 列表翻页, 重命名成功, 重命名空标题拒绝, 置顶成功, 置顶超限拒绝, 取消置顶, 删除成功, 删除不存在, 非本人对话拒绝]
- contract_refs: [".dev-flow/R009/analysis/2026-05-24--R009-conversation-management-backend.md"]
- decision_refs: []
- blocked_files: []

### BB001.1 新增 GET /api/conversations 对话列表 `⬜`

在 conversation_router.py 新增端点：

```python
@router.get("/conversations")
async def list_conversations(
    cursor: str | None = None,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    limit = min(limit, 50)
    items, has_more = await ConversationRepo.list_by_user(db, user.user_id, cursor, limit)
    # has_more 时截断最后一条，用最后一条的 updated_at|id 生成 cursor
    ...
```

### BB001.2 新增 PATCH /api/conversations/{id} 对话更新 `⬜`

```python
@router.patch("/conversations/{conversation_id}")
async def update_conversation(
    conversation_id: str,
    body: ConversationUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    # 1. 查询对话是否存在且属于该用户
    # 2. 如果 body.pinned == True → 检查置顶上限
    # 3. 如果 body.title → 校验非空 + 长度 <= 200
    # 4. 执行更新
    ...
```

### BB001.3 新增 DELETE /api/conversations/{id} 对话删除 `⬜`

```python
@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    checkpointer=Depends(get_checkpointer),
    user: UserContext = Depends(get_current_user),
):
    # 1. 验证存在 + user_id 归属
    # 2. 删除 conversation 记录
    # 3. 调用 checkpointer.adelete_thread(thread_id)（失败不阻断）
    ...
```

---

## R009-BB002：chat/stream_router.py — 自动创建 + 标题推送 `✅ 已完成`

- 文件：`backend/app/chat/stream_router.py`（修改）
- 改动类型：修改
- domain: backend
- task_layer: business
- depends_on: [R009-BF002, R009-BF003, R009-BF005]
- priority: 5
- risk_tags: [network, first_use]
- smoke_required: true
- mode: negotiated
- status: pending
- acceptance_criteria:
  - 新对话（无 conversation_id）时在 init 阶段创建 conversation 记录
  - SSE init 帧在 conversation 记录创建后发送
  - 已有 conversation 的多轮对话不重复创建记录
  - done 帧后继续执行标题生成，不立即结束生成器
  - 标题生成成功时推送 SSE title 事件
  - 标题生成失败时静默跳过，不推送 title 事件
  - done 后更新 updated_at 和 message_count (+2)
  - SSE 流事件顺序：init → (thinking/status/sources/token) → done → title → 流结束
  - 现有 SSE 流逻辑不回归
- test_tasks:
  - type: integration
    description: 流式对话自动创建 + 标题推送测试
    scenarios: [新对话自动创建记录, 多轮对话不重复创建, 标题生成成功推送title, 标题生成失败静默跳过, message_count正确更新, SSE事件顺序正确]
- contract_refs: [".dev-flow/R009/analysis/2026-05-24--R009-conversation-management-backend.md"]
- decision_refs: []
- blocked_files: []

### BB002.1 init 阶段创建 conversation 记录 `⬜`

修改 `stream_chat` 端点和 `event_generator`：

```python
async def stream_chat(..., db=Depends(get_db)):
    conversation_id = body.conversation_id or str(uuid.uuid4())
    is_new_conversation = not body.conversation_id

    # 新对话：init 阶段前创建 conversation 记录
    if is_new_conversation:
        from app.infra.conversation_repo import ConversationRepo
        from app.domain.models import Conversation
        conv = Conversation(id=conversation_id, user_id=user.user_id)
        await ConversationRepo.create(db, conv)
        await db.commit()

    async def event_generator():
        # init 帧保持不变
        yield _sse_frame("init", {"conversation_id": conversation_id})
        # ... 现有流式逻辑 ...
```

### BB002.2 done 后生成标题并推送 title 事件 `⬜`

修改 `event_generator`，在 yield done 后继续执行：

```python
    async def event_generator():
        try:
            yield _sse_frame("init", ...)

            async for event in graph.astream(...):
                ...

            # done 后不立即返回，继续更新统计
            await ConversationRepo.update_message_stats(db, conversation_id)

            yield "event: done\ndata: null\n\n"

            # 新对话：尝试生成标题
            if is_new_conversation:
                title = await generator.generate_title(body.question)
                if title:
                    await ConversationRepo.update(db, conversation_id, user.user_id, title=title)
                    yield _sse_frame("title", {"conversation_id": conversation_id, "title": title})

        except Exception as e:
            ...
```

### BB002.3 更新 updated_at 和 message_count `⬜`

在 done 帧之前调用 `ConversationRepo.update_message_stats`，更新 `updated_at = now()` 和 `message_count += 2`。

---

## R009-BB003：main.py — Lifespan DB 初始化 `✅ 已完成`

- 文件：`backend/app/main.py`（修改）
- 改动类型：修改
- domain: backend
- task_layer: business
- depends_on: [R009-BF001]
- priority: 4
- risk_tags: [first_use]
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - lifespan 启动时初始化 SQLAlchemy async engine 并挂载到 app.state
  - 自动执行 create_tables()（在 PostgresSaver setup 之后）
  - shutdown 时释放 engine
  - 现有 lifespan 初始化链路不受影响
  - `db_session_factory` 挂载到 app.state 供 dependencies.get_db 使用
- test_tasks:
  - type: integration
    description: lifespan 启动/关闭测试
    scenarios: [engine初始化成功, conversations表自动创建, shutdown释放engine]
- contract_refs: []
- decision_refs: []
- blocked_files: []

### BB003.1 lifespan 中初始化 SQLAlchemy engine `⬜`

在 PostgresSaver setup 之后，添加 SQLAlchemy engine 初始化：

```python
from app.infra.database import engine, async_session_factory, create_tables

# 在 PostgresSaver setup 之后：
await create_tables()
application.state.db_session_factory = async_session_factory
print("[startup] SQLAlchemy engine + conversations table initialized")
```

### BB003.2 shutdown 时释放 engine `⬜`

在 shutdown 段添加：

```python
await engine.dispose()
print("[shutdown] SQLAlchemy engine disposed")
```

---

## R009-BB004：architecture.md — 文档更新 `✅ 已完成`

- 文件：`.dev-flow/architecture.md`（修改）
- 改动类型：修改
- domain: docs
- task_layer: business
- depends_on: [R009-BB001, R009-BB002, R009-BB003]
- priority: 3
- risk_tags: []
- smoke_required: false
- mode: direct
- status: pending
- acceptance_criteria:
  - 系统拓扑中 SQLite 替换为 PostgreSQL
  - 关键决策新增 SQLAlchemy 2.0 async ORM 条目
  - 权威边界补充 /api/conversations
  - 不变量 SSE 事件 type 列表新增 title
  - 禁止模式移除 R006 遗留条目
  - 版本号更新
- test_tasks:
  - type: unit
    description: architecture.md 内容完整性检查
    scenarios: [拓扑无SQLite, 关键决策含SQLAlchemy, 权威边界含conversations, 不变量含title事件, 禁止模式无R006条目]
- contract_refs: []
- decision_refs: []
- blocked_files: []

### BB004.1 更新系统拓扑 `⬜`

将 `SQLite (metadata)` 更新为 `PostgreSQL (checkpoints + conversations)`。

### BB004.2 新增/更新关键决策 `⬜`

1. 将第 31 行 `SQLite 先行: 嵌入式零运维，SQLAlchemy ORM 抽象层可后期迁移 PostgreSQL` 更新为 `PostgreSQL + SQLAlchemy async：对话管理 CRUD 使用 SQLAlchemy 2.0 async ORM，复用 psycopg 3 驱动（R009）。SQLite 阶段已完成。`
2. 新增条目：`SQLAlchemy 2.0 async ORM：对话管理 CRUD 使用 SQLAlchemy async，与 psycopg 连接池共存（R009）`

### BB004.3 更新权威边界 `⬜`

补充：`Backend API 是对话管理的唯一入口（/api/conversations 列表/更新/删除）`。

### BB004.4 更新不变量 `⬜`

SSE 事件格式 type 列表从 `init/thinking/status/sources/token/done/error` 更新为 `init/thinking/status/sources/token/done/title/error`。

### BB004.5 更新禁止模式 `⬜`

移除 `R006 不做消息持久化（留给 R007）`（R007 已完成）。更新版本号为 5.2 + R009。
