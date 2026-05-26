---
date: 2026-05-26
type: brainstorm
status: concluded
requirement_cycle: R010
topic: 长对话上下文管理
---

# 长对话上下文管理

## 结论
- 要做什么：
  1. 修复 `_respond` 节点不传历史消息的 bug — 让多轮对话生效
  2. 加入 token 预算管理 + 摘要压缩 — 超阈值时 LLM 摘要 + RemoveMessage 清理旧消息，防止撞 200K 上限
  3. 新增 rewrite 节点 — 多轮时用 LLM 改写追问为独立问题，提升 RAG 检索精准度
  4. 评估基础设施 + 确定性 Graders（BB004）— 数据集(23条正负平衡) + eval runner + state_check / tool_calls / transcript / deterministic_tests / static_analysis + Tracked Metrics
  5. LLM-as-Judge 评估（BB005）— 4 维度 rubric + assertions + Judge 调用 + 评估报告生成
- 不做什么：
  - 分层记忆（短期/长期多级摘要）— 过度设计，性价比低
  - 离线对话缓存 — 不相关
- 关键约束：
  - LLM context window 200K，最大输出 128K
  - 每轮消耗约 4,000-7,000 token（RAG context 占大头）
  - 约 30-40 轮会撞上限，必须做管理
  - 摘要只在超阈值时触发，不是每轮都调 LLM
- 核心场景：
  - 追问式：「什么是函数？」→「定义域怎么求？」→「举个例子？」
  - 延续式：逐步解题教学，一个完整流程 5-10 轮
  - 用户自由切换两种模式
- 已确认决策：
  - 摘要触发阈值：65%（130K）
  - 摘要模型：复用 get_chat_model()，同模型
  - 摘要存储：AgentState.conversation_summary，PostgresSaver 自动持久化
  - 旧消息清理：RemoveMessage API，LangGraph 原生支持

## 关键讨论
- 200K 窗口虽然大，但 RAG context 每轮占 3K-5K token，实际只能撑 30-40 轮
- 方案选择：滑动窗口（太简单会断片）< 摘要压缩 + RemoveMessage（选定）< 分层记忆（过度设计）
- 用户选择一期做完：修 bug + 摘要压缩 + rewrite + 评估（拆为 BB004 确定性 + BB005 LLM Judge）全部在一个 RC 内交付
