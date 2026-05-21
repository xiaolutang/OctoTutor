# OctoTutor 架构宪法

> version: 3.0 | updated: 2026-05-21 | R004 rag-dialogue

## 系统拓扑

```
User → Traefik → Frontend (Next.js) → Browser
                → Backend (FastAPI) → ChromaDB (embedded)
                                   → DashScope API (Embedding + OCR + Reranker)
                                   → LLM (OpenAI 兼容协议)
                                   → BM25 (内存索引)
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
- **DashScope gte-rerank**: 中文 Reranker 效果好，TextReRank API 稳定（DEC-rag-001）
- **BM25+RRF 混合检索**: rank_bm25 + jieba 分词，RRF(k=60) 融合向量与关键词结果（DEC-rag-013）
- **OpenAI 兼容 LLM 对话**: 通过 OpenAI 协议接入 glm-5.1，解耦模型供应商（DEC-rag-003）
- **domain/infra/chat/api 分层**: Protocol 定义在 domain/，实现在 infra/，业务在 chat/，HTTP 在 api/（DEC-rag-012）

## 权威边界

- Frontend 不直接访问 ChromaDB，必须通过 Backend API
- Backend API 是检索和对话的唯一入口（/api/retrieve + /api/chat）
- DashScope API 调用统一在 Backend 内（Embedding + OCR + Reranker），Frontend 不持有 DashScope Key
- LLM 调用统一在 Backend 内（infra/llm.py），Frontend 不持有 LLM Key
- OCR 缓存是唯一权威数据源（parsed/ 目录），入库脚本按缓存状态决定是否调 OCR

## 不变量

- Monorepo 结构不变：services/frontend/ + services/backend/ + deploy/
- ChromaDB 嵌入式运行（不独立部署为服务）
- 入库管线幂等：先删旧数据再入库
- OCR 缓存优先：有缓存跳过，无缓存才调 DashScope
- Reranker 失败降级：ChatService 返回 degraded=true + degradation_reason，不阻断回答生成
- BM25 静态索引：启动时从 ChromaDB 全量加载构建，运行期间不更新
- API 兼容：/api/retrieve 接口不变（R003 契约），新功能走 /api/chat

## 禁止模式

- Frontend 不直接调 DashScope API
- 不在主分支直接开发功能（使用 feat/ 分支）
- R004 不做用户认证打通（留给 R005+）
- R004 不做 SSE 流式输出（DEC-rag-006，留给 R005+ 跟 UI 一起做）
- R004 不做多轮对话状态管理（DEC-rag-007，留给 R005+ 跟 UI 一起做）
- R004 不做前端 Chat UI（留给 R005）
