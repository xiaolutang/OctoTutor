---
requirement_cycle: R007-PATCH02
patch_for: R007
date: 2026-05-24
type: brainstorm
status: concluded
---

# 补丁：修复两个架构反向依赖问题

## 背景

在 R007-PATCH01（architecture-cleanup）归档后，review 后端模块依赖关系时发现两处架构反向依赖未修复：

1. `api/routes/health.py` 和 `api/routes/retrieve.py` 反向依赖 `main.py`（`from app.main import app`），而 chat 层已使用更干净的 `request.app.state` 模式
2. `domain/models.py` 向上依赖 `rag/models.py`（`QueryResult`），domain 层不应了解 RAG 层数据结构

## 补丁描述

### 问题 1：api/routes 反向依赖 main.py

- `health.py` 和 `retrieve.py` 在函数内 `from app.main import app` 获取 app 实例
- chat 层的 `dependencies.py` 已使用 `request.app.state` 方式访问单例
- 应统一使用 `request.app.state` 模式，消除反向依赖

### 问题 2：domain/models.py 向上依赖 rag/models.py

- `chunks_to_sources()` 函数接收 `list[QueryResult]` 参数，导致 domain 层导入 rag 层
- 该函数是 rag → domain 的转换逻辑，应移到 rag 层或 infra 层
- 移动后 `domain/models.py` 不再导入任何 rag 模块

## 影响范围

- 原始 RC：R007
- 补丁 RC：R007-PATCH02
- 受影响文件：
  - `app/api/routes/health.py` — 消除 main.py 反向依赖
  - `app/api/routes/retrieve.py` — 消除 main.py 反向依赖
  - `app/domain/models.py` — 移出 chunks_to_sources，消除 rag 反向依赖
  - `app/rag/context_builder.py` 或新位置 — 接收 chunks_to_sources
  - 所有导入 chunks_to_sources 的文件 — 更新 import 路径
