---
date: 2026-05-21
type: brainstorm
status: concluded
requirement_cycle: R004
topic: R004 RAG 检索优化 + AI 对话
---

# R004 RAG 检索优化 + AI 对话

## 结论

- 要做什么：
  - 评估并优化 Context Precision（检索结果噪声比）
  - 按需加 Reranker 或调 top-K，收窄 LLM 输入
  - 接 LLM（NewAPI glm-5.1）实现对话 API（纯后端）
  - 评估 Faithfulness（回答是否忠实于教材内容）

- 不做什么：
  - 前端 Chat UI（下一轮 R005）
  - 对话交互设计（跟 UI 一起做）
  - 完整 BM25/Hybrid 检索重构（如 Reranker 够用就不做）

- 关键约束：
  - LLM 统一走 NewAPI（glm-5.1），和 R003 的 BlockType 分类一致
  - 检索优化和对话是同一根管线的上下游，不能割开
  - 必须先评估 Context Precision，再决定优化手段

- 核心场景：
  - 学生提问 → 检索教材 → 精炼上下文 → LLM 生成回答 → 评估回答质量

- 待确认：
  - R004 需求包正式名称
  - 是否需要流式 SSE（纯后端可先不做，等 UI 时再加）

## 关键讨论

- R003 检索基线虽然高（Span Hit@5=97.9%），但 Hit 高不代表给 LLM 的内容精炼
- 检索优化（1）和 AI 对话（2）是管线上下游，必须一起做，否则无法判断回答质量问题是出在检索还是 Prompt
- Chat UI 放下一轮，避免本轮范围过大
