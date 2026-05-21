# 模块结构 — R003

> updated: 2026-05-20

## 目录结构

```
OctoTutor/
├── services/
│   ├── frontend/                    # Next.js（R001+R002 迁移）
│   │   ├── src/
│   │   ├── package.json
│   │   └── Dockerfile
│   └── backend/                     # FastAPI（R003 新建）
│       ├── app/
│       │   ├── __init__.py
│       │   ├── main.py              # FastAPI 入口
│       │   ├── config.py            # pydantic-settings
│       │   ├── rag/
│       │   │   ├── __init__.py
│       │   │   ├── readers/
│       │   │   │   ├── __init__.py
│       │   │   │   └── pdf_reader.py    # PDF Reader + OCR 缓存
│       │   │   ├── chunkers/
│       │   │   │   ├── __init__.py
│       │   │   │   └── math_chunker.py  # 章节识别 + Parent-Child
│       │   │   ├── embeddings.py         # DashScope Embedding 封装
│       │   │   └── vector_store.py       # ChromaDB 封装
│       │   ├── api/
│       │   │   ├── __init__.py
│       │   │   └── routes/
│       │   │       ├── __init__.py
│       │   │       ├── health.py         # GET /api/health
│       │   │       └── retrieve.py       # POST /api/retrieve
│       │   ├── ingestion/
│       │   │   ├── __init__.py
│       │   │   └── pipeline.py           # 入库编排
│       │   └── evaluation/
│       │       ├── __init__.py
│       │       ├── spot_check.py         # 入库抽检
│       │       ├── eval_runner.py        # 检索质量评估
│       │       └── eval_types.py         # EvalItem / EvalResult 类型
│       ├── data/
│       │   ├── raw/                  # PDF 文件
│       │   ├── parsed/               # OCR 缓存
│       │   ├── images/               # 页面 PNG
│       │   ├── chroma_db/            # ChromaDB 向量存储
│       │   └── evaluation/           # 评估数据集
│       ├── tests/
│       ├── Dockerfile
│       ├── requirements.txt
│       └── .env.template
├── deploy/
│   ├── docker-compose.yml
│   └── docker-compose.local.yml
├── .dev-flow/
└── packages/                         # 共享代码（按需）
```

## 模块职责

| 模块 | 职责 | 对应任务 |
|------|------|---------|
| services/frontend/ | Next.js 前端 | R003-BF-001 |
| app/config.py | 统一配置管理 | R003-BF-002 |
| app/main.py | FastAPI 入口 + 路由注册 | R003-BF-002 |
| app/rag/readers/ | PDF 读取 + OCR 缓存 | R003-BF-003 |
| app/rag/chunkers/ | 章节识别 + 分块 | R003-BF-004 |
| app/rag/embeddings.py | DashScope Embedding | R003-BF-005 |
| app/rag/vector_store.py | ChromaDB 封装 | R003-BF-006 |
| app/ingestion/ | 入库编排 | R003-BB-007 |
| app/api/routes/ | health + retrieve API | R003-BB-008 |
| app/evaluation/ | 抽检 + 评估集 + 评估 | R003-BB-009/010/011 |
| deploy/ | Docker Compose | R003-BF-012 |
