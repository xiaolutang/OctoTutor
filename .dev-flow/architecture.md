# OctoTutor 架构宪法

> version: 5.1 | updated: 2026-05-23 | R007 persistence-agent-upgrade

## 系统拓扑

```
User → Traefik → Frontend (Next.js) → Browser
                → Backend (FastAPI) → ChromaDB (embedded)
                                   → DashScope API (Embedding + OCR + Reranker)
                                   → LLM (OpenAI 兼容协议)
                                   → BM25 (内存索引)
                                   → SQLite (metadata)

SSE 流式连接：Browser → Traefik → Backend SSE Endpoint (/api/chat/stream)

认证链路：
  Browser → auth-center (OAuth 2.0 + PKCE) → TokenManager (localStorage)
  apiClient (Bearer token) → Backend JWT 验证 (HS256 共享密钥)
  auth-center ← 共享 JWT_SECRET_KEY → Backend
```

## 关键决策与理由

- **前后端分离**: Next.js SPA + FastAPI 独立后端，各自容器化部署
- **Python 后端**: RAG 生态（ChromaDB/jieba/LlamaIndex）是 Python 原生，Node.js 重写无必要
- **ChromaDB 嵌入式**: 4GB 服务器约束下，嵌入式方案优于独立向量服务
- **DashScope Embedding**: tongyi-embedding-vision-flash 768 维，中文数学效果好
- **全量 OCR**: 数学教材图文混排多，PyMuPDF 无法识别图表公式图片，每页都 OCR
- **Monorepo**: 1 人团队，前后端在同一仓库（frontend/ + backend/）
- **SQLite 先行**: 嵌入式零运维，SQLAlchemy ORM 抽象层可后期迁移 PostgreSQL
- **DashScope gte-rerank**: 中文 Reranker 效果好，TextReRank API 稳定（DEC-rag-001）
- **BM25+RRF 混合检索**: rank_bm25 + jieba 分词，RRF(k=60) 融合向量与关键词结果（DEC-rag-013）
- **OpenAI 兼容 LLM 对话**: 通过 OpenAI 协议接入 glm-5.1，解耦模型供应商（DEC-rag-003）
- **domain/infra/chat/api 分层**: Protocol 定义在 domain/，实现在 infra/，业务在 chat/，HTTP 在 api/（DEC-rag-012）
- **SSE over WebSocket**: SSE 基于标准 HTTP，无需额外协议升级，天然支持断线检测，适合单向流式推送（DEC-rag-006-rev1）
- **AsyncOpenAI 双客户端**: 非流式用 OpenAI()，流式用 AsyncOpenAI()，按场景选择同步/异步调用方式
- **MMPPN 错误码体系**: 五位数字编码 MM=模块 PP=阶段 N=序号，结构化错误码替代字符串匹配
- **JWT 共享密钥鉴权**: auth-center 签发 HS256 JWT，后端本地解码验证，不查 Redis 黑名单（DEC-auth-001）
- **apiClient 统一网络层**: 前端所有 API 请求经 apiClient，自动附加 Bearer token + 刷新锁 + 401 重试（DEC-auth-003）

## 权威边界

- Frontend 不直接访问 ChromaDB，必须通过 Backend API
- Backend API 是检索和对话的唯一入口（/api/retrieve + /api/chat + /api/chat/stream）
- SSE 端点 /api/chat/stream 是唯一的流式对话入口，前端不缓存 LLM 回答用于复用
- DashScope API 调用统一在 Backend 内（Embedding + OCR + Reranker），Frontend 不持有 DashScope Key
- LLM 调用统一在 Backend 内（infra/llm.py），Frontend 不持有 LLM Key
- OCR 缓存是唯一权威数据源（parsed/ 目录），入库脚本按缓存状态决定是否调 OCR

## 不变量

- Monorepo 结构不变：frontend/ + backend/ + deploy/
- ChromaDB 嵌入式运行（不独立部署为服务）
- 入库管线幂等：先删旧数据再入库
- OCR 缓存优先：有缓存跳过，无缓存才调 DashScope
- Reranker 失败降级：ChatService 返回 degraded=true + degradation_reason，不阻断回答生成
- BM25 静态索引：启动时从 ChromaDB 全量加载构建，运行期间不更新
- API 兼容：/api/retrieve 接口不变（R003 契约），/api/chat 非流式不变，新功能走 /api/chat/stream
- SSE 事件格式固定：每帧为 `event: {type}\ndata: {json}\n\n`，type 为 init/thinking/status/sources/token/done/error
- 检索不流式（一次返回全部 chunks），LLM 生成逐 token 流式
- API 鉴权：/api/retrieve、/api/chat、/api/chat/stream 需要 Bearer token，/api/health 不需要鉴权

## 禁止模式

- Frontend 不直接调 DashScope API
- 不在主分支直接开发功能（使用 feat/ 分支）
- R006 不做消息持久化（留给 R007）
- R004 不做多轮对话状态管理（DEC-rag-007，留给 R005+ 跟 UI 一起做）
- R004 不做前端 Chat UI（留给 R005）
- 不做 WebSocket：SSE 已满足单向流式推送需求，WebSocket 的双向能力不需要
- 不做前端 LLM 回答缓存：每次对话都是独立请求，避免缓存一致性难题（R007-PATCH01 已移除 localStorage 消息缓存）
