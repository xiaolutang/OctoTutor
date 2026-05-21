# OctoTutor 项目规格

> updated: 2026-05-20 | R003

## 项目概述

OctoTutor（章鱼哥解题）是高中数学 AI 辅导 Web 应用。通过教材知识库 + AI 对话，帮助学生理解数学概念和解题方法。

## 当前阶段

- R001 项目初始化 + Auth ✅
- R002 Dev Sandbox 增强 ✅
- **R003 教材知识库底座** ← 当前
- R004 AI 对话 + Chat UI（待规划）

## 技术栈

| 层级 | 选型 |
|------|------|
| 前端 | Next.js 16 + React 19 + TypeScript |
| 后端 | Python FastAPI + pydantic-settings |
| 向量数据库 | ChromaDB (PersistentClient, 嵌入式) |
| Embedding | DashScope tongyi-embedding-vision-flash (768d) |
| OCR | DashScope 多模态 API |
| PDF 处理 | PyMuPDF (fitz) |
| ORM | SQLAlchemy + SQLite |
| 部署 | Docker Compose + Traefik |

## 用户路径

### R003 开发者路径

1. 部署后端服务 → 配置 DashScope API Key
2. 运行入库脚本 → 5 本教材入库
3. 运行抽检 → 验证入库质量
4. 构建评估集 → 基于实际入库数据
5. 运行评估 → 获得 Hit Rate / MRR 基线

### R004 最终用户路径（预期）

1. 访问 OctoTutor → 输入数学问题
2. 后端检索相关教材 chunks → AI 生成解答
3. 展示教材引用来源（书名 + 页码 + 截图）

## 约束

- 生产服务器：4 核、4GB RAM、40GB 存储
- 5 本固定教材（必修第一/二册 + 选择性必修第一/二/三册）
- DashScope API 需要有效 API Key
- 入库为离线操作，非实时
