---
version: "1.0"
type: tasks
topic: reverse-dependency-fix
requirement_cycle: R007-PATCH02
workflow:
  evaluate_provider: local
  mode: auto
status: archived
---

# 架构反向依赖修复 — 任务清单

基于 design.md 设计，修复两处架构反向依赖。
全局约束：纯 import 路径和函数签名调整，无逻辑变更。参考 `chat/dependencies.py` 的 DI 模式。

---

## 执行顺序

1. ⬜ R007-PATCH02-BF001 — api/routes DI 模式统一（无依赖）
   - ⬜ BF001.1 health.py DI 函数改用 request.app.state
   - ⬜ BF001.2 retrieve.py DI 函数改用 request.app.state
2. ⬜ R007-PATCH02-BF002 — chunks_to_sources 层级迁移（无依赖）
   - ⬜ BF002.1 domain/models.py 删除 chunks_to_sources + QueryResult import
   - ⬜ BF002.2 rag/context_builder.py 新增 chunks_to_sources 函数
   - ⬜ BF002.3 infra/llm.py 更新 import 路径
   - ⬜ BF002.4 agent/graph.py 更新 import 路径
3. ⬜ R007-PATCH02-BF003 — 编译验证 + 测试

---

## R007-PATCH02-BF001：api/routes DI 模式统一 `✅ 已完成`

- 文件：`backend/app/api/routes/health.py` + `backend/app/api/routes/retrieve.py`
- 改动类型：修改
- domain: backend
- task_layer: foundation
- depends_on: []
- priority: 4
- risk_tags: []
- smoke_required: false
- mode: direct
- status: pending
- acceptance_criteria:
  - health.py 和 retrieve.py 中无 `from app.main` 导入
  - 所有 DI 函数签名为 `(request: Request) -> Xxx`
  - GET /api/health 和 POST /api/retrieve 端点功能不变
- test_tasks:
  - type: unit
    description: 验证 DI 函数通过 request.app.state 获取单例
    scenarios: [正常获取单例]
- contract_refs: []
- decision_refs: []
- blocked_files: []

### BF001.1 health.py DI 函数改用 request.app.state `⬜`

参考 `chat/dependencies.py:12-17` 的模式。

将 `get_vector_store()` 和 `get_embedding_service()` 从无参延迟导入改为接收 `request: Request` 参数：

```python
from fastapi import Request

def get_vector_store(request: Request) -> ChromaDBStore:
    return request.app.state.vector_store

def get_embedding_service(request: Request) -> DashScopeEmbedding:
    return request.app.state.embedding_service
```

删除两个函数内的 `from app.main import app`。

### BF001.2 retrieve.py DI 函数改用 request.app.state `⬜`

同 BF001.1 模式，对 retrieve.py 的 `get_vector_store()` 和 `get_embedding_service()` 做相同修改。

---

## R007-PATCH02-BF002：chunks_to_sources 层级迁移 `✅ 已完成`

- 文件：`backend/app/domain/models.py` + `backend/app/rag/context_builder.py` + `backend/app/infra/llm.py` + `backend/app/agent/graph.py`
- 改动类型：修改
- domain: backend
- task_layer: foundation
- depends_on: []
- priority: 4
- risk_tags: []
- smoke_required: false
- mode: direct
- status: pending
- acceptance_criteria:
  - domain/models.py 无 `from app.rag` 导入
  - chunks_to_sources 在 rag/context_builder.py 中定义
  - infra/llm.py 和 agent/graph.py 从新路径导入
  - 后端全量测试通过
- test_tasks:
  - type: unit
    description: 验证 chunks_to_sources 从新路径正常工作
    scenarios: [正常转换, 空 chunks]
- contract_refs: []
- decision_refs: []
- blocked_files: []

### BF002.1 domain/models.py 删除 chunks_to_sources + QueryResult import `⬜`

删除以下内容：
- `from app.rag.models import QueryResult`
- `chunks_to_sources` 函数定义

保留 `SourceReference` 类（被 domain/protocols.py 和其他模块依赖）。

修改后 domain/models.py 只剩 `SourceReference` 一个纯数据类，零内部依赖。

### BF002.2 rag/context_builder.py 新增 chunks_to_sources 函数 `⬜`

在已有 `build_numbered_context` 下方添加 `chunks_to_sources`：

```python
from app.domain.models import SourceReference

def chunks_to_sources(chunks: list[QueryResult]) -> list[SourceReference]:
    """从检索结果构建引用来源列表"""
    # 逻辑从 domain/models.py 原样搬入
```

### BF002.3 infra/llm.py 更新 import 路径 `⬜`

```python
# 改前
from app.domain.models import SourceReference, chunks_to_sources
# 改后
from app.domain.models import SourceReference
from app.rag.context_builder import chunks_to_sources
```

### BF002.4 agent/graph.py 更新 import 路径 `⬜`

```python
# 改前
from app.domain.models import SourceReference, chunks_to_sources
# 改后
from app.domain.models import SourceReference
from app.rag.context_builder import chunks_to_sources
```

---

## R007-PATCH02-BF003：编译验证 + 测试 `✅ 已完成`

- 文件：无（验证任务）
- 改动类型：配置
- domain: backend
- task_layer: foundation
- depends_on: [R007-PATCH02-BF001, R007-PATCH02-BF002]
- priority: 5
- risk_tags: []
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - `cd backend && python -m pytest` 全量通过
  - `grep -r "from app.main import app" backend/app/api/` 无结果
  - `grep -r "from app.rag" backend/app/domain/models.py` 无结果
- test_tasks:
  - type: integration
    description: 全量后端测试
    scenarios: [570+ 测试全通过]
- contract_refs: []
- decision_refs: []
- blocked_files: []
