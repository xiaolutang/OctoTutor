---
date: 2026-05-20
type: tech_selection
status: decided
requirement_cycle: R003
architecture_impact: true
replaces: null
---

# R003 教材知识库 — 技术选型与范围决策

## 背景

OctoTutor 已完成 R001（项目初始化 + auth）和 R002（dev-sandbox 增强），当前为纯前端 SPA（Next.js 16 + React 19）。R003 需要引入教材知识库底座，为后续 R004 AI 对话提供检索能力。

项目参考了同团队的 ragDemo 项目（Python FastAPI + ChromaDB + DashScope 的高中数学 RAG 系统），ragDemo 已有 5 本高中数学 PDF 教材和完整的 RAG 管线。

生产服务器约束：4 核、4GB RAM、40GB 存储。

## 决策清单

### DEC-003-1: R003 范围

- **选择**: 知识库底座（数据库 + 教材存储 + 向量检索 API）
- **理由**: 每轮需求包聚焦，降低风险。AI 对话留给 R004。
- **R003 交付物**:
  - 后端 API 服务（可独立启动）
  - PDF 教材入库管线
  - 向量检索 API（供 R004 调用）
- **R004 范围**: AI 对话 + 前端 Chat UI

### DEC-003-2: 后端架构 — 独立服务

- **选择**: 独立后端服务（OctoTutor-API），前后端分离
- **理由**: 前后端解耦，后端可独立扩展，与 ragDemo 技术栈对齐
- **前端**: OctoTutor (Next.js) — 已有
- **后端**: OctoTutor-API (Python FastAPI) — 新建

### DEC-003-3: 技术栈 — 复用 ragDemo 体系

- **选择**: 复用 ragDemo 技术栈，但代码独立开发（不拷贝/抄袭）
- **理由**: ragDemo 已验证了 Python 生态对数学 RAG 的适配性，LlamaIndex/chromadb/jieba 等库是 Python 原生生态，Node.js 重写成本极高且无必要
- **代码原则**: 学习 ragDemo 的架构模式和设计思路，但走全链路开发流程，代码从零实现

**技术栈**:

| 层级 | 选型 | 说明 |
|------|------|------|
| 后端框架 | Python FastAPI | 异步、高性能、自动文档 |
| 向量数据库 | ChromaDB | 轻量嵌入式，已验证 |
| Embedding | DashScope (tongyi-embedding) | 已验证，中文数学内容效果好 |
| 分词 | jieba | 中文分词，用于 BM25 |
| PDF 处理 | PyMuPDF (fitz) | PDF 渲染和文本提取 |
| OCR | DashScope 多模态 API | 数学公式 OCR 为 LaTeX |
| ORM | SQLAlchemy | 抽象层，后期迁移 PostgreSQL 只需改连接串 |
| 结构化存储 | SQLite（先行） | 嵌入式零运维，4GB 服务器友好 |

### DEC-003-4: 向量数据库 — ChromaDB（非 Qdrant）

- **选择**: ChromaDB
- **理由**:
  - ragDemo 已验证其在数学教材场景的可靠性
  - 嵌入式运行，Docker 不增加额外容器
  - 4GB 服务器内存约束下，嵌入式方案优于独立服务
  - 数据规模（5 本教材 ~几千 chunk）远低于 ChromaDB 性能上限
- **之前讨论**: 曾倾向 Qdrant，但发现 ragDemo 已用 ChromaDB 后调整为复用

### DEC-003-5: 教材数据来源 — PDF + OCR 管线

- **选择**: 复用 ragDemo 的 PDF 教材文件 + 类似的 OCR 入库管线
- **理由**: 5 本高中数学教材 PDF 已存在于 ragDemo，OCR 质量已验证
- **入库流程**（参考 ragDemo 模式，自己实现）:
  ```
  PDF → PyMuPDF 渲染页面图片 → 多模态 OCR → Markdown+LaTeX
      → 章节结构识别 → Parent-Child 分块
      → DashScope Embedding → ChromaDB 存储
  ```

### DEC-003-7: 项目结构 — Monorepo

- **选择**: Monorepo，前后端在同一仓库
- **理由**: 1 人团队，前后端一对一关系，接口变更原子提交，后期拆微服务只需在 services/ 下新增目录
- **目标结构**:
  ```
  OctoTutor/
    services/
      frontend/       (Next.js，现有代码迁移)
      backend/        (Python FastAPI，新建)
    packages/         (共享代码，按需)
    deploy/           (共享部署配置)
    .dev-flow/        (项目管理)
  ```
- **迁移成本**: 现有代码量小（R001+R002），结构调整工作量可控

### DEC-003-6: RAG 架构模式 — 学习 ragDemo，独立实现

- **参考 ragDemo 的架构模式**（自己实现）:
  - Parent-Child 双层分块：先检 child 后提升 parent，兼顾精度和上下文完整性
  - Hybrid 检索：Dense (向量) + BM25 (关键词)，RRF 融合
  - Reranker：DashScope Rerank API 二次排序
  - Source Diversity：同一来源去重，保证结果多样性
- **不实现的部分**（R004 或更后）:
  - LangGraph Agent 图
  - Mem0 会话记忆
  - 视频/动画生成

## 架构影响

本决策引入以下架构变更（需通过 xlfoundry-plan 确认）:

1. **新增后端服务**: OctoTutor-API (Python FastAPI)，作为独立 Docker 容器部署
2. **新增数据存储**: ChromaDB（嵌入后端容器）+ SQLite/文件系统（教材数据）
3. **新增外部服务依赖**: DashScope API（Embedding + OCR + Reranker）
4. **前端对接变更**: Next.js 前端需要通过 HTTP 调用 OctoTutor-API
5. **部署架构变更**: 从单容器（Next.js）变为双容器（Next.js + FastAPI）

architecture.md 需要更新以反映这些变更。

## 开放问题

- ~~OctoTutor-API 的项目结构放在哪里？独立仓库 vs monorepo 子目录~~ → **已决定：Monorepo**
- ~~结构化存储选择：SQLite 先行 vs 直接上 PostgreSQL~~ → **已决定：SQLite + SQLAlchemy ORM**
- ~~前后端认证打通方式~~ → **R003 不需要（教材检索无需用户身份），R004 再解决**

## 补充说明

#### 兜底与失败策略（Step 2.5 门禁补充）

- **DashScope API 不可用**：Embedding 请求指数退避重试 3 次；OCR 重试 2 次后跳过该页并记录日志；R003 不引入本地备用模型，降级表现为入库管线暂停等待恢复、检索 API 在无 embedding 时返回空结果
- **OCR 失败**：重试 2 次，仍失败则跳过该页，日志记录失败页码和原因，不影响其他页面处理
- **ChromaDB 不可用**：嵌入式运行，数据损坏或磁盘满时 health 检查返回 unhealthy；R003 不做定期备份（数据可通过入库脚本重建），不做 BM25 降级
- **入库管线中断恢复**：入库采用"先删旧数据再入库"的幂等策略；OCR 缓存（parsed/）天然支持断点续传（有缓存跳过），重新运行入库脚本即可恢复

#### 边界条件（Step 2.5 门禁补充）

- **ChromaDB 为空时**：检索 API 正常返回 `{"chunks": [], "total": 0}`，HTTP 200；health 端点 `document_count: 0` 表示未初始化
- **PDF 文件不存在/目录为空**：入库脚本检测并报错退出，提示"PDF 目录为空或文件不存在"
- **PDF 页数为 0 或文件损坏**：PyMuPDF 解析失败时跳过该文件并记录日志，继续处理其他文件
- **OCR 结果为空**：跳过该页，日志记录，不阻塞入库流程
- **冷启动**：R003 不做自动入库（需手动运行入库脚本）；首次部署后需手动执行 `python -m ingestion` 入库教材数据

## 后续动作

- 进入 xlfoundry-plan 拆解 R003 任务
- 产出详细的 feature_list.json 和 API 契约
