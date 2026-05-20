# 测试覆盖清单 — R003

> updated: 2026-05-20

## 任务测试覆盖

| 任务 | risk_tags | 测试层级 | 覆盖状态 |
|------|-----------|---------|---------|
| R003-BF-001 Monorepo 结构重组 | startup | L3 | 待测试 |
| R003-BF-002 后端脚手架 | startup, config | L3 | 待测试 |
| R003-BF-003 PDF Reader | network | L2 | 待测试 |
| R003-BF-004 Chunker | - | L1 | 待测试 |
| R003-BF-005 Embedding | network | L2 | 待测试 |
| R003-BF-006 ChromaDB VectorStore | - | L1 | 待测试 |
| R003-BB-007 入库管线 | network, startup | L2 | 待测试 |
| R003-BB-008 检索 API | - | L2 | 待测试 |
| R003-BB-009 入库抽检 | - | L1 | 待测试 |
| R003-BB-010 构建评估集 | - | L1 | 待测试 |
| R003-BB-011 检索质量评估 | - | L1 | 30/30 通过 |
| R003-BF-012 Docker Compose | config | L3 | 待测试 |

## 高风险任务 smoke test 要求

| 任务 | smoke 场景 | 优先级 |
|------|-----------|--------|
| R003-BF-001 | npm run build 成功 | P0 |
| R003-BF-002 | FastAPI /api/health 返回 200 | P0 |
| R003-BF-003 | 单页 OCR 缓存读写正确 | P0 |
| R003-BF-005 | 单条文本 embedding 返回 768 维 | P0 |
| R003-BB-007 | 1 本教材入库成功 | P0 |
| R003-BF-012 | docker compose up 前后端可访问 | P0 |

## 测试环境

- 单元测试：pytest + mock DashScope API
- 集成测试：本地 Python venv + 真实 DashScope API Key
- Docker 测试：docker compose up 验证双容器部署
- 前端迁移验证：Playwright 测试
