# OctoTutor Development Summary

最后更新: 2026-06-04

## 需求包索引

| RC | 名称 | 任务数 | 状态 | 完成日期 |
|----|------|--------|------|----------|
| R001 | 项目初始化 | 6 | archived | 2026-05-20 |
| R002 | dev-sandbox-enhancement | 2 | archived | 2026-05-20 |
| R003 | knowledge-base | 17 | archived | 2026-05-21 |
| R004 | rag-dialogue | 12 | archived | 2026-05-22 |
| R005 | chat-ui-sse | 14 | archived | 2026-05-22 |
| R006 | auth-integration | 7 | archived | 2026-05-23 |
| R007 | persistence-agent-upgrade | 6 | archived | 2026-05-24 |
| R007-PATCH01 | architecture-cleanup (补丁 R007) | 7 | archived | 2026-05-24 |
| R007-PATCH02 | reverse-dependency-fix (补丁 R007) | 3 | archived | 2026-05-24 |
| R008 | architecture-refactor | 3 | archived | 2026-05-24 |
| R009 | conversation-management | 25 | archived | 2026-05-25 |
| R010 | grounding-faithfulness | 14 | archived | 2026-06-02 |
| R009-PATCH01 | stream-conversation-ownership (补丁 R009) | 5 | archived | 2026-06-02 |
| R011 | auth-race-condition | 2 | archived | 2026-06-02 |
| R012 | sse-decouple | 5 | archived | 2026-06-03 |
| R013 | code-quality-governance | 4 | archived | 2026-06-03 |
| R014 | sidebar-ux-polish | 2 | archived | 2026-06-04 |
| R015 | code-convergence | 6 | archived | 2026-06-04 |

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
| eval-infra | 确定性 Grader + LLM-as-Judge + 指数退避重试 |
| classifier | 问题分类器（textbook/unrelated + 社交噪音检测） |
| chat | ChatService 对话管线（混合检索 + Rerank + LLM 生成） |
| infra | LLM Generator + Reranker + BM25Retriever 基础设施层 |
| docker-deploy | Docker Compose 双容器 + Traefik 路由 |
| classifiers | BlockType LLM 分类（NewAPI glm-5.1） |
| chat-ui | Chat UI 组件（ChatUI + MessageBubble + ChatInput + useChatStream） |
| sse | SSE 流式端点 + 事件序列化 + 断线检测 |
| agent | LangGraph StateGraph 编排（classify→retrieve→respond / refuse） |
| persistence | PostgresSaver/MemorySaver 对话持久化 + conversation_id 多轮 |
| conversation | GET /api/conversations/current 对话历史加载 + user_id 隔离 |
| conversation-api | GET/PATCH/DELETE /api/conversations 对话列表+更新+删除+置顶 |
| conversation-repo | SQLAlchemy 2.0 async ORM Conversation CRUD 数据访问层 |
| conversation-context | ConversationProvider + useReducer 对话状态管理 + Auth 守卫 |
| sidebar | 侧边栏组件（对话列表+新建+置顶分组+右键菜单） |
| sse-decouple | SSE 断连恢复（后台任务解耦 + Queue 事件队列 + 重连端点 + 停止端点） |

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
| CAP-eval-008 | 确定性 Grader + LLM Judge + 指数退避重试评估体系 |
| CAP-agent-005 | 长对话上下文管理（summarize 摘要 + rewrite 改写 + context injection） |
| CAP-agent-006 | 分类器默认策略修正（unrelated 默认 + 社交噪音检测 + 数学关键词扩展） |
| CAP-agent-007 | 分级 Context 注入（强约束/弱参考 + 降级模式） |
| CAP-eval-001 | Relevance 相关性评估（BB010 补齐） |
| CAP-chatui-001 | SSE 流式回答（逐 token 推送 + 状态提示） |
| CAP-chatui-002 | 检索无结果兜底回答 |
| CAP-chatui-003 | 流式错误恢复（撤回 + 重试） |
| CAP-chatui-004 | 非流式 API 兼容 |
| CAP-auth-001 | JWT 鉴权验证（HS256 共享密钥 + Depends 注入） |
| CAP-auth-002 | Token 自动刷新（TokenManager + ensureValidToken） |
| CAP-auth-003 | 刷新锁去重（refreshPromise + 30s 超时 + 并发安全） |
| CAP-auth-004 | SSE 请求鉴权（fetchWithAuth + Bearer token + 401 重试） |
| CAP-agent-001 | LangGraph StateGraph 条件路由（textbook→retrieve→respond, unrelated→refuse） |
| CAP-agent-002 | 教学策略 prompt（类比驱动+启发式引导+步骤化叙事） |
| CAP-agent-003 | conversation_id 多轮对话（PostgresSaver 持久化 + MemorySaver fallback） |
| CAP-agent-004 | 对话历史加载（GET /api/conversations/current + user_id 隔离） |
| CAP-conv-001 | 对话列表分页加载（cursor-based + 置顶分离） |
| CAP-conv-002 | 对话重命名（inline edit + PATCH API） |
| CAP-conv-003 | 对话置顶/取消置顶（PATCH pinned + 分组排序） |
| CAP-conv-004 | 对话删除（DELETE API + 确认弹窗 + 自动切换） |
| CAP-conv-005 | 多对话切换（ConversationContext + activeId + 消息加载） |
| CAP-conv-006 | 流式中切换阻止（isStreaming 检测 + toast 提示） |
| CAP-conv-007 | 对话标题自动生成（LLM generate_title + SSE title 事件） |
| CAP-sec-001 | /api/chat/stream conversation_id 归属校验（id + user_id SQL 层过滤） |
| CAP-auth-005 | ConversationProvider Auth 守卫（isInitialized 依赖 + 竞态消除） |
| CAP-sse-001 | SSE 后台任务解耦（asyncio.create_task + Queue + 客户端断连不影响 graph 执行） |
| CAP-sse-002 | SSE 重连端点 GET /chat/stream/resume（活跃任务→SSE 流 / 已完成→JSON / 404/204） |
| CAP-sse-003 | 停止端点 POST /chat/stop（cancel_event 设置 + 后台任务事件边界停止） |
| CAP-sse-004 | 前端 SSE 重连（刷新后检测未完成 AI 回复 → resumeStream → 流式恢复或直接显示） |
| CAP-sse-005 | 前端停止按钮适配（fire-and-forget POST /chat/stop + 立即 abort） |

## 变更记录

### R015 code-convergence (2026-06-04)

- 全项目 6 视角 simplify 并行审查（125 个发现），提取 6 个高置信度共性问题做机械修复
- BF001: llm.py 删除 generate_stream 死代码 + 测试级联清理（6 文件，-330 行）
- FF002: createId() 从 5 处内联收敛到 lib/utils.ts 统一导出
- FF003: partitionByPinned 单次遍历替代 double .filter()（reducer 热路径）
- FF001: rehypePlugins 提取为模块常量，消除渲染时数组重建
- FF004: ConversationItemCard onPin/onUnpin 合并为 onTogglePin + sidebar cardProps spread
- FF005: ChatInput 移除冗余 disabled prop，统一使用 isStreaming
- 后端 683 测试 + 前端 271 测试全通过，Simplify 审查无 HIGH 问题

### R014 sidebar-ux-polish (2026-06-04)

- scrollIntoView 选中恢复：刷新后侧边栏自动滚动到当前对话项（instant），切换对话时平滑滚动（smooth）
- 菜单碰撞检测：三点菜单根据位置自动向上/向下展开，底部项不再被裁剪；点击外部自动关闭菜单
- 只改 conversation-item-card.tsx 一个文件，271 前端测试全通过

### R013 code-quality-governance (2026-06-03)

- 后端共享工具函数提取：`conversation_utils.py` 新建，`load_conversation_by_id` + `to_api_message` + `extract_latest_messages` 从 conversation_router 移出，两个路由统一导入
- 前端 Reducer 独立文件：`conversation-reducer.ts` 提取自 conversation-context.tsx，ConversationAction 类型 + reducer + initialState + localStorage 工具函数，context 和测试文件统一导入真实实现
- SSE 事件分发共享函数：`handleSSEEvent` + `BaseSSECallbacks` 类型，chatStreamFetch 和 resumeStream 复用，消除 ~40 行重复 switch-case
- Controller 竞态测试重写：30 个纯逻辑测试（+8），覆盖 needsResumePlaceholder、SSE 重连触发条件、INSERT_NEW 安全性、mounted 守卫、完整时序模拟
- 后端 683 测试 + 前端 271 测试全通过

### R012 sse-decouple (2026-06-03)

- 后端 graph 执行解耦：`_run_graph` 后台任务 + `asyncio.Queue` 事件队列 + `_active_graphs` 注册表，客户端断连后 graph 继续运行
- SSE 重连端点 `GET /chat/stream/resume`：活跃任务→复用同一 Queue 返回 SSE 流；已完成→返回 JSON（完整消息）；无消息→204
- 停止端点 `POST /chat/stop`：设置 `cancel_event`，后台任务在下一个事件边界停止，不更新 stats
- 前端 SSE 重连：刷新后检测未完成 AI 回复（generating/retrieving status + 2 min 窗口），发起 resumeStream 恢复流式显示或直接显示完整回复
- 前端停止适配：fire-and-forget POST /chat/stop + 立即 abort，移除旧轮询逻辑
- 收敛：`_create_sse_generator` 共享 SSE 生成器、`readSSEStream` 共享解析、autouse test fixture、冗余测试合并
- 16 后端测试全通过

### R011 auth-race-condition (2026-06-02)

- ConversationProvider Auth 守卫修复：useEffect 依赖 `[]` → `[isInitialized]`，加 `if (!isInitialized) return` 守卫
- 消除刷新 /chat 后对话列表竞态：AuthProvider 异步初始化完成前不再发起未认证的 fetchConversationList
- 参照 `controller.ts:37-48` 模式，3 行改动（+3/-3），净增 0 行
- 附带发现并修复 auth-sdk-web `init()` token 过期判断 bug（hasRefreshToken 守卫）

### R009-PATCH01 stream-conversation-ownership（补丁 R009）(2026-06-02)

- stream_router.py 归属校验：已有 conversation_id 进入 graph.astream 前校验 id + user_id
- 归属失败 → SSE error 03901（对话不存在），DB 异常 → SSE error 02901
- 新增 _single_error_event helper 替代内联 async generator
- 4 个归属测试（not_found/db_error/pass/new_skip）+ 4 个旧测试补 get_by_id mock
- architecture.md 不变量补充 stream 归属校验
- 40 测试全通过（stream_conversation + sse_integration + router_auth）

### R010 grounding-faithfulness (2026-06-02)

- 长对话上下文管理：summarize 摘要压缩（超阈值自动触发 + RemoveMessage 清理）+ rewrite 多轮改写（6 条历史窗口 + 首轮透传）+ respond 节点修复
- 分类器默认策略修正：默认改 unrelated（宁可拒答不误答）+ 社交噪音检测（去问候后残余为空→unrelated）+ 数学关键词扩展（"题"、"算"）
- 分级 Context 注入：高相关性→强约束 prompt / 低相关性→弱参考 / 降级模式→弱参考
- 评估体系：确定性 Grader（关键词匹配 + page 验证）+ LLM-as-Judge（Faithfulness + Coverage + Relevance 合并评估）+ 1s→5s→10s 指数退避重试 + 非标准 API 兼容
- 代码收敛：闭包参数注入（relevance_threshold / top_k）+ 测试工厂统一（_helpers.py）+ 测试精简（parametrize 合并）+ conftest section_id 动态推导
- 全量评估脚本 run_eval.py：200 题 Faithfulness 全量跑通，Faithfulness≈0.82, Coverage≈0.63, Relevance≈0.88

### R009 conversation-management (2026-05-25)

- 后端 SQLAlchemy async ORM：Conversation 模型 + composite indexes + ConversationRepo CRUD（单次 DB round trip UPDATE RETURNING）
- conversation_router：GET 列表（cursor 分页 + 置顶分离）+ PATCH 更新（标题/置顶）+ DELETE 删除 + user_id 隔离
- LLM 标题自动生成：generate_title 非流式调用 + SSE title 事件推送
- 前端 ConversationContext + useReducer：9 种 action 管理对话状态（SET_ACTIVE/INSERT_NEW/UPDATE_ITEM/REMOVE_ITEM 等）
- 侧边栏组件：对话列表 + 新建按钮 + 置顶分组 + 右键菜单（重命名/置顶/删除）+ 确认弹窗
- chat-layout 集成：ConversationProvider + sidebar + main 三区布局
- Simplify 收敛修复：requestIdRef 竞态、INSERT_NEW 排序、UPDATE_ITEM 重排、auto-scroll、死代码清理、错误处理
- E2E：Playwright conversation.spec.ts 8 场景覆盖（布局/创建/切换/重命名/置顶/取消/删除/流式阻止）
- 241 前端单元测试 + 3 E2E 测试全通过

### R007-PATCH02 reverse-dependency-fix（补丁 R007）(2026-05-24)

- api/routes DI 模式统一：health.py + retrieve.py 改用 `request.app.state`，消除 `from app.main import app` 反向依赖
- chunks_to_sources 层级迁移：从 domain/models.py 移入 rag/context_builder.py，消除 domain→rag 跨层反向依赖
- 570 后端测试全通过

### R007-PATCH01 architecture-cleanup（补丁 R007）(2026-05-24)

- LLMGenerator 封装修复：`get_chat_model()` 公共方法替代私有属性访问（`_client.api_key`/`_base_url`/`_model`）
- 共享工具函数提取：`chunks_to_sources()` → domain/models.py（R007-PATCH02 迁移至 rag/context_builder.py），`build_numbered_context()` → rag/context_builder.py
- conversation_router user_id 隔离：PostgresSaver 改用 `alist` 从存储 config 验证归属，MemorySaver `_extract_latest_messages` 统一遍历
- 后端死代码清理：删除 `stream_chat()`、`retrieve_node`/`respond_node` 空壳、`test_chat_service_stream.py`
- 前端死代码清理：删除 `use-chat-storage.ts`、简化 `updateMsg`、`use-conversation` 移除冗余 state
- architecture.md 路径修正（`services/frontend/` → `frontend/`）+ FORBID-5 补充
- 570 后端 + 96 前端测试全通过

### R007 persistence-agent-upgrade (2026-05-24)

- LangGraph StateGraph 编排：classify→retrieve→respond / refuse 条件路由，AgentState TypedDict
- 教学策略 prompt：类比驱动+启发式引导+步骤化叙事+纠正误解+知识关联+趣味记忆
- PostgresSaver 持久化：AsyncPostgresSaver + 自动建库 + MemorySaver fallback
- SSE 集成重构：stream_router 改用 `graph.stream()` + stream_mode=["updates","messages"]
- conversation_id 多轮对话：UUID4 自动创建 + checkpoint 恢复 + conversation_router GET API
- 前端对话加载：useConversation hook + conversationId localStorage 持久化
- Thinking 事件 + conversationId 类型 + 流式 hook 重构

### R006 auth-integration (2026-05-23)

- 后端 JWT 鉴权中间件：UserContext + get_current_user Depends 注入，HS256 共享密钥验证（签名+过期+type+sub），3 个受保护端点 + health 公开
- 前端 apiClient 统一网络层：registerGetToken 回调解耦 + fetchWithAuth 自动 Bearer + refreshPromise 刷新锁去重 + 30s 超时 + X-Retry 防循环 + auth:session-expired CustomEvent
- AuthContext TokenManager 注册：独立实例 + 共享 sdkConfig + session-expired 监听触发 login
- useChatStream 改用 apiClient：2 行替换，SSE 流式鉴权透明处理
- Docker 部署配置：JWT_SECRET_KEY 环境变量 + lockfile 兼容修复
- E2E 全栈验证：后端 9/9 + 前端 15/15 全部 PASS

### R005 chat-ui-sse (2026-05-22)

- 后端 SSE 流式端点：AsyncOpenAI 双客户端 + 事件序列化 + 断线检测 + 闲聊分类跳过检索
- 前端 Chat UI 完整交互：发送 + 流式显示 + 停止 + 来源卡片 + KaTeX 数学公式 + 消息持久化
- 用户消息原地编辑：textarea + 确认/取消 + 截断重发（DEC-edit-001~004）
- 测试覆盖：后端/前端 L1 异常路径 + Docker SSE 集成测试，38 个前端测试全部通过
- 简化收敛：_build_messages 提取 + appendAndSend 辅助函数 + Protocol 补齐 generate_stream

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
