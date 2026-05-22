# OctoTutor Development Summary

最后更新: 2026-05-22

## 需求包索引

| RC | 名称 | 任务数 | 状态 | 完成日期 |
|----|------|--------|------|----------|
| R001 | 项目初始化 | 6 | archived | 2026-05-20 |
| R002 | dev-sandbox-enhancement | 2 | archived | 2026-05-20 |
| R003 | knowledge-base | 17 | archived | 2026-05-21 |
| R004 | rag-dialogue | 12 | archived | 2026-05-22 |

## 模块清单

| Module | 描述 |
|--------|------|
| monorepo | Monorepo 结构（backend/ + frontend/ 根目录平铺） |
| backend-scaffold | FastAPI + pydantic-settings 后端脚手架 |
| pdf-reader | PyMuPDF + DashScope OCR + 缓存 |
| chunker | StructureParser + MathChunker（4 级章节 + 512 token 切分） |
| embeddings | DashScope text-embedding-v4 批量 embed |
| vector-store | ChromaDB PersistentClient + where 过滤 |
| ingestion | IngestionPipeline + CLI + 幂等 + 错误隔离 |
| retrieve | POST /api/retrieve + GET /api/health |
| spot-check | 入库抽检（页码 + 内容 + 结构 + 元数据） |
| evaluation | EvalRunner + EvalSetLoader + 分层评估指标 |
| chat | ChatService 对话管线（混合检索 + Rerank + LLM 生成） |
| infra | LLM Generator + Reranker + BM25Retriever 基础设施层 |
| docker-deploy | Docker Compose 双容器 + Traefik 路由 |
| classifiers | BlockType LLM 分类（NewAPI glm-5.1） |

## 能力清单

| Capability | 描述 |
|------------|------|
| CAP-eval-001 | 评估集构建与加载 |
| CAP-eval-002 | 检索质量评估（Hit Rate@K + MRR） |
| CAP-eval-003 | 分层评估指标（Section Hit / Keyword Coverage / Negative Pass Rate） |
| CAP-eval-004 | 入库抽检验证 |
| CAP-eval-005 | 评估基线建立与对比 |
| CAP-rag-001 | PDF OCR + 结构化解析 |
| CAP-rag-002 | 父子索引 Chunk + 元数据扩展 |
| CAP-rag-003 | BlockType LLM 分类 |
| CAP-rag-004 | 向量检索 API |
| CAP-dialogue-001 | Context Precision 评估 |
| CAP-dialogue-002 | BM25+RRF 混合检索 |
| CAP-dialogue-003 | Reranker 精炼 + 降级 |
| CAP-dialogue-004 | LLM 对话生成 + Token 截断 |
| CAP-dialogue-007 | Faithfulness + Coverage + Relevance 三角评估 |
| CAP-eval-001 | Relevance 相关性评估（BB010 补齐） |

## 变更记录

### R004 rag-dialogue (2026-05-22)

- ChatService 对话管线：向量检索 + BM25 RRF 混合检索 + Reranker 精炼（失败降级）+ LLM 生成
- 完整评估管线扩展：Context Precision + Faithfulness + Coverage + Relevance 四维评估，200 条评估集
- 基础设施层：LLMGenerator + DashScopeReranker + BM25Retriever（jieba + rank_bm25）
- Architecture v3.0：domain/protocols → infra → chat 分层，Protocol 驱动依赖反转
- 评估基线：HR@5=97.5%, Faithfulness=0.84, Relevance=0.85, Coverage=0.62

### R003 knowledge-base (2026-05-21)

- Monorepo 结构搭建：backend/ + frontend/ 根目录平铺，Docker Compose 双容器部署
- 完整 RAG 管线：PDF OCR → 结构解析 → MathChunker 切分 → Embedding → ChromaDB 向量存储 → 检索 API
- 父子索引 + 元数据扩展：page_start/page_end/source_pages/section_id/block_type
- BlockType LLM 分类：NewAPI (glm-5.1) 批量分类 1183 child chunks，99.9% 成功率
- 分层评估体系：Span Hit@5=97.9%, Section Hit@5=84.7%, MRR=0.959, 200 条重标评估集

### R002 dev-sandbox-enhancement (2026-05-20)

- Dev Sandbox 页面增强
- Playwright E2E 测试

### R001 项目初始化 (2026-05-20)

- Next.js 16 前端项目初始化
- Auth SDK 集成（OAuth 2.0 + PKCE）
- 基础页面布局与路由
