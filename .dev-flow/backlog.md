# Project Backlog

项目级想法池。记录想到但当前不做的事情。

## 待办

- [ ] RAG 检索结果缓存
  - 来源：R010 设计讨论
  - 原因：多轮对话每轮 query 不同缓存命中率低，但跨用户相同问题场景有价值
  - 优先级：低

- [ ] 评估 Transcript 日志持久化
  - 来源：R010 BB004 评估体系设计（参考 Anthropic eval 文章）
  - 原因：当前评估只输出分数报告，缺少中间产物（rewritten_question、context_chunks、AI 回答）的完整日志，不便于回查评分器有效性
  - 优先级：中


- [ ] 最后一条消息的重新编辑功能
  - 来源：R010 评估过程中想到
  - 原因：用户发送消息后发现有误，需要支持对最后一条消息重新编辑并重新生成 AI 回复（类似 ChatGPT 的编辑消息功能）
  - 优先级：中

- [ ] 项目级别增加限流
  - 来源：工作中想到
  - 原因：当前系统只有前端 isStreaming 防重复发送和后端限流错误码预留，还没有真正的服务端限流；后续需要按 user_id/IP 做请求频率控制，避免对话、检索和 LLM 调用被滥用
  - 优先级：中

- [ ] 项目级别思考智能体的 harness
  - 来源：工作中想到
  - 原因：随着需求和智能体能力变复杂，需要沉淀一套面向本项目的智能体开发 harness，把需求澄清、方案设计、实现执行、独立评估、证据留存和复盘串成可追溯流程
  - 优先级：中

- [ ] 增加智能体的多模态识别能力
  - 来源：工作中想到
  - 原因：数学学习场景里用户很可能上传题目图片、截图或包含公式的内容，需要让智能体具备图片/公式/文本混合输入的识别能力，再接入后续解题和检索链路
  - 优先级：中

- [ ] appendToken 逐 token 全量重渲染优化
  - 来源：R015 simplify 审查 Agent 3 HIGH
  - 原因：流式回答时每个 token 都触发消息列表全量重渲染，需拆分流式状态为独立 state，架构级改动
  - 优先级：中

- [ ] scrollIntoView 每 token 触发节流
  - 来源：R015 simplify 审查 Agent 3 MEDIUM
  - 原因：每个 token 都触发 scrollIntoView，需 RAF 节流或 IntersectionObserver
  - 优先级：低

- [ ] _active_graphs 无过期清理
  - 来源：R015 simplify 审查 Agent 3 HIGH
  - 原因：后端 _active_graphs 注册表无过期清理机制，长时间运行可能内存泄漏，需设计定期清理策略
  - 优先级：中

- [ ] summarize/rewrite 串行改并行
  - 来源：R015 simplify 审查 Agent 3 MEDIUM
  - 原因：Agent Graph 中 summarize 和 rewrite 串行执行，可并行化提升响应速度，需 Graph 拓扑变更
  - 优先级：低

- [ ] 测试中复制源码逻辑重构
  - 来源：R015 simplify 审查 Agent 5 HIGH × 9
  - 原因：9 处测试复制了源码逻辑而非导入真实实现，大规模测试重构，需提取纯函数
  - 优先级：中

- [ ] 无效/冗余测试清理
  - 来源：R015 simplify 审查 Agent 5 MEDIUM × 7
  - 原因：7 处无效或冗余测试需逐个评估测试价值后删除
  - 优先级：低

- [ ] AuthContext value useMemo 优化
  - 来源：R015 simplify 审查 Agent 3 MEDIUM
  - 原因：AuthContext value 每次渲染创建新对象，影响面较大需谨慎处理
  - 优先级：低

- [ ] ConversationItemCard memo 优化
  - 来源：R015 simplify 审查 Agent 3 LOW
  - 原因：需评估回调引用稳定性后再决定是否加 React.memo
  - 优先级：低

- [ ] cn() 全局替换统一
  - 来源：R015 simplify 审查 Agent 2 MEDIUM × 9
  - 原因：9 处手写 className 拼接可替换为 cn() 工具函数，机械但量大
  - 优先级：低

- [ ] createId 碰撞风险改进
  - 来源：R015 simplify 审查 Agent 2 MEDIUM
  - 原因：Date.now().toString(36) + Math.random() 方案在高并发下有碰撞风险，可考虑 crypto.randomUUID() 或 nanoid
  - 优先级：低

- [ ] 重构类 RC 归档时检查 feature-map 节点拆分
  - 来源：R018 归档 feature-map 代码一致性审查
  - 原因：R012/R013 重构把大模块拆成小模块（如 Controller、Reducer、ConvUtils），归档时没有同步更新功能图节点，导致多次归档后累积偏差
  - 优先级：中

- [ ] 数据库连接池加固（SQLAlchemy + PostgresSaver）
  - 来源：工作中发现（线上 PostgresSaver 单连接断开后无法重连，对话消息加载失败）
  - 原因：PostgresSaver 当前用 psycopg 单连接，无重连机制；SQLAlchemy engine 缺少 pool_pre_ping 保活配置。需改为：1) PostgresSaver 从单连接改为 psycopg_pool.AsyncConnectionPool（自动重连+保活）；2) SQLAlchemy 加 pool_pre_ping=True + pool_recycle=1800
  - 优先级：高

- [ ] 前端 controller.ts 重命名 + Hook 职责拆分
  - 来源：R019 方案设计讨论
  - 原因：controller.ts 应改为 use-chat-controller.ts 符合 React Hook 命名惯例；useChatController 330 行职责偏大，可拆为 useChatMessages、useStreamResume 等更小的 Hook
  - 优先级：低

## 已完成

- [x] /chat 刷新后对话列表时有时无（L2 缺陷 — Auth 竞态）
  - 来源：工作中发现（R010 真实评估部署后用户刷新测试）
  - 完成：2026-06-05
  - 证据：conversation-context.tsx 的 useEffect 依赖已改为 [isInitialized]，竞态已修复
  - 关联缺陷 ID: DF-20260527-01，关联任务: R009-FF003

## 已放弃

- [~] 新建对话 UX 优化：点击"新建对话"后立即在 sidebar 插入占位卡片
  - 来源：R009 验收时发现
  - 放弃：2026-05-25
  - 原因：R009 的 lazy creation + INSERT_NEW 流程已处理此场景，SSE init 事件触发后插入新卡片，非遗漏问题
