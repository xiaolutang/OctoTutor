# Planning Context: R003 knowledge-base

> generated_at: 2026-05-20T22:00:00Z
> feature_list_version: 1.5
> requirement_cycle: R003

## Source Analysis
- .dev-flow/analysis/2026-05-20--R003-knowledge-base.md (confirmed)

## Source Decisions
- .dev-flow/decisions/2026-05-20--R003-tech-stack-and-scope.md (7 decisions, status=decided)

## Architecture Understanding
- 涉及模块：services/backend/（新建）、services/frontend/（迁移）、deploy/（更新）
- 已有约束：
  - 生产服务器：4 核、4GB RAM、40GB 存储
  - ChromaDB 嵌入式运行
  - DashScope API 需要有效 API Key
  - 入库为离线操作
- 架构影响：新增后端服务、ChromaDB、DashScope 依赖、Monorepo 迁移
- 禁止事项：不做 BM25/Hybrid/Reranker/Parent Promote、不做认证打通
- 需要后续任务处理的架构点：R004 AI 对话需调用 R003 检索 API

## Interaction Chain
1. 开发者配置 .env → 启动后端服务 → /api/health 确认可用
2. 开发者运行入库脚本 → 5 本教材入库 → ChromaDB 有数据
3. 开发者运行抽检 → 验证入库质量
4. 开发者构建评估集 → 基于实际入库数据
5. 开发者运行评估 → 获得 Hit Rate / MRR 基线

## Logic Tree
```text
后端服务启动
├─ config.py 加载环境变量
├─ FastAPI 初始化
├─ ChromaDB PersistentClient 初始化
└─ API 路由注册（/api/health + /api/retrieve）

入库流程
├─ PDF Reader
│  ├─ 检查 OCR 缓存
│  ├─ 无缓存 → 渲染 PNG + DashScope OCR → 存缓存
│  └─ 有缓存 → 直接读取
├─ Chunker
│  ├─ 章节正则识别 → SectionBoundary[]
│  └─ Parent-Child 分块 → Chunk[]
├─ Embedding
│  └─ DashScope API → 768 维向量
└─ VectorStore
   └─ ChromaDB upsert

检索流程
├─ query → DashScope Embedding → 768 维
└─ ChromaDB query → top-K chunks
```

## Decision Items
| ID | Summary | Type | Must Plan |
|----|---------|------|-----------|
| DEC-kb-001 | 全量 OCR + 缓存优先 | tech_choice | yes |
| DEC-kb-002 | Parent-Child 双层分块 | tech_choice | yes |
| DEC-kb-003 | 仅 cosine similarity | boundary | yes |
| DEC-kb-004 | 自建评估集 | boundary | no |
| DEC-kb-005 | Monorepo 迁移 | architecture_impact | yes |
| DEC-kb-006 | book+page 定位图片 | tech_choice | no |

## Capability Model
| ID | Name | Risk Tags | Covered By |
|----|------|-----------|------------|
| CAP-kb-001 | PDF 教材入库 | network | BF-003, BB-007 |
| CAP-kb-002 | 基础向量检索 API | none | BB-008 |
| CAP-kb-003 | 检索质量评估 | none | BB-010, BB-011 |
| CAP-kb-004 | Monorepo 结构迁移 | none | BF-001 |
| CAP-kb-005 | 后端服务 Docker 部署 | network | BF-012 |

## Out Of Scope
- BM25 / Hybrid / RRF / Reranker / Parent Promote
- AI 对话 / 生成质量
- 前端 Chat UI
- 用户认证打通
- 教材版本管理
- LangGraph Agent / Mem0 / 视频动画生成
