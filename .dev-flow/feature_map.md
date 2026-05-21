# 功能图 — R003

> updated: 2026-05-20

## 功能树

```
R003 教材知识库底座
├── infrastructure
│   ├── R003-BF-001 Monorepo 结构重组 + 前端迁移
│   └── R003-BF-002 后端脚手架搭建
├── rag-components
│   ├── R003-BF-003 PDF Reader + OCR 缓存
│   ├── R003-BF-004 章节 StructureParser + Parent-Child 分块
│   ├── R003-BF-005 DashScope Embedding 封装
│   └── R003-BF-006 ChromaDB VectorStore
├── api-ingestion
│   ├── R003-BB-007 入库管线编排
│   └── R003-BB-008 检索 API
└── quality-integration
    ├── R003-BB-009 入库抽检
    ├── R003-BB-010 构建检索评估集
    ├── R003-BB-011 检索质量评估
    └── R003-BF-012 Docker Compose 集成 + 迁移验证
```

## 依赖图

```
BF-001 ──→ BF-002 ──→ BF-003 ──┐
                      BF-004 ──┤──→ BB-007 ──→ BB-009 ──→ BB-010 ──┐
                      BF-005 ──┤                                  ├──→ BB-011
                      BF-006 ──┤                                  │
                               └──→ BB-008 ────────────────────────┘
                                                               └──→ BF-012
```

## 执行顺序（拓扑排序）

1. R003-BF-001 (Monorepo 结构重组)
2. R003-BF-002 (后端脚手架)
3. R003-BF-003 (PDF Reader) — 可与 004/005/006 并行
4. R003-BF-004 (Chunker) — 可与 003/005/006 并行
5. R003-BF-005 (Embedding) — 可与 003/004/006 并行
6. R003-BF-006 (ChromaDB) — 可与 003/004/005 并行
7. R003-BB-007 (入库管线) — 依赖 003+004+005+006
8. R003-BB-008 (检索 API) — 依赖 005+006
9. R003-BB-009 (入库抽检) — 依赖 007
10. R003-BB-010 (构建评估集) — 依赖 009
11. R003-BB-011 (检索质量评估) — 依赖 008+010
12. R003-BF-012 (Docker Compose) — 依赖 008
