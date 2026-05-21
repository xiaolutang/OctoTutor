# OctoTutor 架构宪法

> version: 2.0 | updated: 2026-05-20 | R003 knowledge-base

## 系统拓扑

```
User → Traefik → Frontend (Next.js) → Browser
                → Backend (FastAPI) → ChromaDB (embedded)
                                   → DashScope API (Embedding + OCR)
                                   → SQLite (metadata)
```

## 关键决策与理由

- **前后端分离**: Next.js SPA + FastAPI 独立后端，各自容器化部署
- **Python 后端**: RAG 生态（ChromaDB/jieba/LlamaIndex）是 Python 原生，Node.js 重写无必要
- **ChromaDB 嵌入式**: 4GB 服务器约束下，嵌入式方案优于独立向量服务
- **DashScope Embedding**: tongyi-embedding-vision-flash 768 维，中文数学效果好
- **全量 OCR**: 数学教材图文混排多，PyMuPDF 无法识别图表公式图片，每页都 OCR
- **Monorepo**: 1 人团队，前后端在同一仓库（services/frontend/ + services/backend/）
- **SQLite 先行**: 嵌入式零运维，SQLAlchemy ORM 抽象层可后期迁移 PostgreSQL

## 权威边界

- Frontend 不直接访问 ChromaDB，必须通过 Backend API
- Backend API 是检索能力的唯一入口
- DashScope API 调用统一在 Backend 内，Frontend 不持有 DashScope Key
- OCR 缓存是唯一权威数据源（parsed/ 目录），入库脚本按缓存状态决定是否调 OCR

## 不变量

- Monorepo 结构不变：services/frontend/ + services/backend/ + deploy/
- ChromaDB 嵌入式运行（不独立部署为服务）
- 入库管线幂等：先删旧数据再入库
- OCR 缓存优先：有缓存跳过，无缓存才调 DashScope

## 禁止模式

- Frontend 不直接调 DashScope API
- 不在主分支直接开发功能（使用 feat/ 分支）
- R003 不做 BM25/Hybrid/Reranker/Parent Promote（留给后续迭代）
- R003 不做用户认证打通（留给 R004）
