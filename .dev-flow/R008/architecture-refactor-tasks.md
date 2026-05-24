---
version: "1.0"
type: tasks
topic: architecture-refactor
requirement_cycle: R008
workflow:
  evaluate_provider: local
  mode: auto
status: completed
---

# architecture-refactor — 后端 任务清单

基于 `.dev-flow/R008/analysis/2026-05-24--R008-architecture-refactor-design.md` 设计，拆解为可执行任务。

全局约束：
- 只改文件位置和 import 路径，不改函数签名和业务逻辑
- 每个子任务完成后立即验证对应测试通过
- 参考依赖图：`docs/module-dependency.puml`

---

## 执行顺序

1. ✅ 任务 1 — 移动 question_classifier 到 domain（无依赖）
   - ✅ 1.1 创建 `domain/classifier.py`
   - ✅ 1.2 更新源码 import（agent/nodes, chat/service）
   - ✅ 1.3 更新测试 import（test_question_classifier）
   - ✅ 1.4 删除旧文件
   - ✅ 1.5 验证
2. ✅ 任务 2 — 移动 context_builder 到 infra（无依赖）
   - ✅ 2.1 创建 `infra/context_builder.py`
   - ✅ 2.2 更新源码 import（infra/llm, agent/graph）
   - ✅ 2.3 更新测试 import（test_llm_generator）
   - ✅ 2.4 删除旧文件
   - ✅ 2.5 验证
3. ✅ 任务 3 — 全局验证 + 依赖图更新（依赖任务 1、2）

---

## R008-BB01：domain/classifier.py — 意图分类模块迁移 `✅ 已完成`

- 文件：`backend/app/domain/classifier.py`
- 改动类型：新建（从 `chat/question_classifier.py` 复制）
- domain: backend
- task_layer: foundation
- depends_on: []
- priority: 5
- risk_tags: []
- smoke_required: true
- mode: direct
- status: completed
  - `grep -rn "from app.chat.question_classifier" backend/` 返回 0 结果
  - `grep -rn "from app.domain.classifier" backend/app/ tests/` 返回 3 个文件
  - `python -m pytest tests/test_question_classifier.py` 通过
  - `python -m pytest tests/test_agent_nodes.py` 通过
- test_tasks:
  - type: unit
    description: 验证分类器功能不变
    scenarios: [test_question_classifier 全部用例]
- contract_refs: []
- decision_refs: []
- blocked_files: []

### BB01.1 创建 domain/classifier.py `⬜`

将 `backend/app/chat/question_classifier.py` 原样复制到 `backend/app/domain/classifier.py`。

文件内容不变，只需确认文件存在且可导入：

```python
# backend/app/domain/classifier.py
# 内容与 chat/question_classifier.py 完全一致
import re

def classify_question(question: str) -> str:
    ...  # 原函数不动
```

### BB01.2 更新 agent/nodes.py import `⬜`

```python
# 改前
from app.chat.question_classifier import classify_question
# 改后
from app.domain.classifier import classify_question
```

### BB01.3 更新 chat/service.py import `⬜`

```python
# 改前
from app.chat.question_classifier import classify_question
# 改后
from app.domain.classifier import classify_question
```

### BB01.4 更新 tests/test_question_classifier.py import `⬜`

```python
# 改前
from app.chat.question_classifier import classify_question
# 改后
from app.domain.classifier import classify_question
```

### BB01.5 删除 chat/question_classifier.py `⬜`

确认 BB01.2~BB01.4 全部完成后，删除 `backend/app/chat/question_classifier.py`。

### BB01.6 验证 `⬜`

```bash
cd backend
python -m pytest tests/test_question_classifier.py tests/test_agent_nodes.py -v
```

---

## R008-BB02：infra/context_builder.py — 上下文构建模块迁移 `✅ 已完成`

- 文件：`backend/app/infra/context_builder.py`
- 改动类型：新建（从 `rag/context_builder.py` 复制）
- domain: backend
- task_layer: foundation
- depends_on: []
- priority: 5
- risk_tags: []
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - `infra/context_builder.py` 存在，`build_numbered_context` 和 `chunks_to_sources` 可用
  - `grep -rn "from app.rag.context_builder" backend/` 返回 0 结果
  - `grep -rn "from app.infra.context_builder" backend/app/ tests/` 返回 3 个文件
  - `python -m pytest tests/test_llm_generator.py` 通过
  - `python -m pytest tests/test_graph_integration.py` 通过
- test_tasks:
  - type: unit
    description: 验证 context builder 功能不变
    scenarios: [test_llm_generator 中 context 相关用例]
- contract_refs: []
- decision_refs: []
- blocked_files: []

### BB02.1 创建 infra/context_builder.py `⬜`

将 `backend/app/rag/context_builder.py` 原样复制到 `backend/app/infra/context_builder.py`。

文件内容不变，import 也不变（仍依赖 `app.rag.models` 和 `app.domain.models`）：

```python
# backend/app/infra/context_builder.py
# 内容与 rag/context_builder.py 完全一致
from app.rag.models import QueryResult
from app.domain.models import SourceReference
...
```

### BB02.2 更新 infra/llm.py import `⬜`

```python
# 改前
from app.rag.context_builder import chunks_to_sources
from app.rag.context_builder import build_numbered_context
# 改后
from app.infra.context_builder import chunks_to_sources
from app.infra.context_builder import build_numbered_context
```

### BB02.3 更新 agent/graph.py import `⬜`

```python
# 改前
from app.rag.context_builder import chunks_to_sources
from app.rag.context_builder import build_numbered_context
# 改后
from app.infra.context_builder import chunks_to_sources
from app.infra.context_builder import build_numbered_context
```

### BB02.4 更新 tests/test_llm_generator.py import（4 处） `⬜`

```python
# 改前（第 190、203、220、298 行）
from app.rag.context_builder import build_numbered_context
# 改后
from app.infra.context_builder import build_numbered_context
```

### BB02.5 删除 rag/context_builder.py `⬜`

确认 BB02.2~BB02.4 全部完成后，删除 `backend/app/rag/context_builder.py`。

### BB02.6 验证 `⬜`

```bash
cd backend
python -m pytest tests/test_llm_generator.py tests/test_graph_integration.py -v
```

---

## R008-BB03：全局验证 + 依赖图更新 `✅ 已完成`

- 文件：`docs/module-dependency.puml`、`docs/module-dependency.md`
- 改动类型：修改
- domain: docs
- task_layer: foundation
- depends_on: [R008-BB01, R008-BB02]
- priority: 3
- risk_tags: []
- smoke_required: false
- mode: direct
- status: pending
- acceptance_criteria:
  - `python -c "from app.main import app"` 不报错
  - `python -m pytest` 全部通过
  - `grep -rn "from app.chat.question_classifier\|from app.rag.context_builder" backend/` 返回 0 结果
  - 依赖图已更新
- test_tasks: []
- contract_refs: []
- decision_refs: []
- blocked_files: []

### BB03.1 全量导入验证 `⬜`

```bash
cd backend
python -c "from app.main import app; print('OK')"
python -m pytest -v
```

### BB03.2 残留引用检查 `⬜`

```bash
grep -rn "from app.chat.question_classifier" backend/
grep -rn "from app.rag.context_builder" backend/
# 两个命令都必须返回 0 结果
```

### BB03.3 更新依赖图 `⬜`

更新 `docs/module-dependency.puml` 和 `docs/module-dependency.md`，反映：
- agent 不再依赖 chat
- infra 不再依赖 rag（context_builder 方面）
- domain 新增 classifier
- infra 新增 context_builder
