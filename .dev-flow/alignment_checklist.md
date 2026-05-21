# 对齐清单 — R003

> updated: 2026-05-20

## 模块间对齐

| 模块 A | 模块 B | 对齐点 | 状态 | 负责任务 |
|--------|--------|--------|------|---------|
| backend-scaffold | pdf-reader | config.py 提供 DashScope 配置 | 待实现 | R003-BF-002 → R003-BF-003 |
| backend-scaffold | embedding | config.py 提供 DashScope 配置 | 待实现 | R003-BF-002 → R003-BF-005 |
| backend-scaffold | vector-store | data/chroma_db/ 路径约定 | 待实现 | R003-BF-002 → R003-BF-006 |
| pdf-reader | chunker | OCR 输出 Markdown → 分块输入 | 待实现 | R003-BF-003 → R003-BF-004 |
| chunker | embedding | Chunk.text → 向量化输入 | 待实现 | R003-BF-004 → R003-BF-005 |
| embedding | vector-store | 向量 + metadata → upsert | 待实现 | R003-BF-005 → R003-BF-006 |
| ingestion | api | ChromaDB 数据 → 检索 | 待实现 | R003-BB-007 → R003-BB-008 |
| api | spot-check | 检索 API → 验证入口 | 待实现 | R003-BB-008 → R003-BB-009 |
| spot-check | evaluation-set | 抽检通过 → 构建评估集 | 待实现 | R003-BB-009 → R003-BB-010 |
| evaluation-set | evaluation | 评估集 → 评估输入 | 待实现 | R003-BB-010 → R003-BB-011 |
| docker-integration | api | Docker 网络配置 → API 可访问 | 待实现 | R003-BF-012 → R003-BB-008 |

## 前后端对齐

| 对齐点 | 前端 | 后端 | 状态 |
|--------|------|------|------|
| API 基础路径 | - | /api/ | R003 不涉及前端调用 |

## 外部服务对齐

| 服务 | 调用方 | 配置 | 状态 |
|------|--------|------|------|
| DashScope Embedding | embedding 模块 | DASHSCOPE_API_KEY | 待配置 |
| DashScope OCR | pdf-reader 模块 | DASHSCOPE_API_KEY | 待配置 |
| ChromaDB | vector-store 模块 | 嵌入式，无需外部配置 | 待实现 |
