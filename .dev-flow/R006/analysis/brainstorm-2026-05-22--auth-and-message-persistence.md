---
date: 2026-05-22
type: brainstorm
status: concluded
requirement_cycle: R006
topic: 用户认证打通
---

# R006 用户认证打通

## 背景

- 认证打通已延后 3 轮（R003→R004→R005），是后续所有功能（消息持久化、LangGraph Agent）的前置依赖
- 前端认证已完备（auth-sdk-web OAuth 2.0 + PKCE），但后端完全无鉴权
- R005 useChatStream 使用原生 fetch，不附带 token

## R006 范围

- 后端 JWT 鉴权中间件（FastAPI Depends 注入）
- 前端 apiClient 统一网络层（token 管理 + 刷新锁 + 401 重试）
- useChatStream 改用 apiClient
- 不做消息持久化、不做对话列表 UI（留给 R007）

## 已确认结论

### 1. 后端认证方案：本地 JWT 验证（共享密钥模式）

#### 方案选型决策

业界三种主流鉴权模式对比：

| 模式 | 做法 | 适用场景 |
|------|------|----------|
| 共享密钥（HS256） | auth-center 签发、业务后端用同一 secret 验证 | 小系统、单体/少量服务 |
| 非对称密钥（RS256） | auth-center 持私钥签发、业务后端用公钥验证 | 微服务标准、OAuth2/OIDC |
| API 网关鉴权 | Traefik/Kong 统一验证，业务后端零感知 | 大规模系统、服务众多 |

**选择共享密钥（HS256）的理由**：
- 本地 Docker 小项目，不是大规模微服务
- auth-center 当前使用 HS256（不是 RS256），非对称密钥需要改 auth-center，违反"不改 auth-center"原则
- Traefik 配置在 xlfoundryTest 项目中，网关鉴权需要跨项目改配置，增加复杂度
- JWT secret 本质是**共享基础设施密钥**（跟数据库密码同性质），由部署层注入环境变量，不属于任何一方私有
- 本地 Docker 内网部署，secret 不泄漏到外部
- 未来升级路径：如果 auth-center 升级到 RS256，后端改从 JWKS 端点拉公钥即可

#### 具体实现

- 后端通过环境变量 AUTH_JWT_SECRET 获取 auth-center 的 JWT secret
- 使用 python-jose 库本地解码验证（HS256）
- 不查 Redis 黑名单，120min 窗口对教育工具可接受
- 预留升级口：get_current_user() 内部加黑名单检查，只改一个函数
- 不改 auth-center 代码、不改 SDK 代码
- auth-center 刷新 access_token 时不会作废旧 token（仅登出才拉黑），不存在刷新导致飞行中请求 401 的问题

#### 鉴权接入方式：FastAPI Depends 注入

- 使用 Depends(get_current_user) 按需注入，非全局中间件
- 与现有代码风格一致（get_chat_service、get_embedding 等都是 Depends）
- 需要鉴权的端点声明 user: UserContext = Depends(get_current_user)
- 不需要鉴权的端点（如 /health）不声明即可，无需白名单
- Depends 链执行顺序：鉴权失败直接 401，后续 service 组装和路由函数不执行

#### 鉴权范围

| 端点 | 是否鉴权 | 理由 |
|------|----------|------|
| GET /api/health | 否 | Docker 健康检查，不能因鉴权失败误判 |
| POST /api/retrieve | 是 | 保护检索资源 |
| POST /api/chat | 是 | 消费 LLM 资源 + 需关联用户 |
| POST /api/chat/stream | 是 | 同上 |

#### user_id 传递链路

```
get_current_user(request) → UserContext(user_id, username)
    ↓ Depends 注入
router 拿到 user
    ↓ 传递
service.handle_chat(question, top_k, user_id=user.user_id)
```

R006 暂不使用 user_id 做持久化（留给 R007），但路由层先注入 user 参数，为后续扩展预留。

#### 新增/修改文件清单（后端部分）

```
新增：
  app/middleware/__init__.py        # 中间件包
  app/middleware/auth.py            # JWT 验证 + get_current_user() + UserContext

修改：
  app/config.py                     # 新增 auth_jwt_secret 配置项
  app/chat/router.py                # 注入 Depends(get_current_user)
  app/chat/stream_router.py         # 注入 Depends(get_current_user)
  app/api/routes/retrieve.py        # 注入 Depends(get_current_user)
```

### 2. 前端统一网络层：apiClient

- 新增 api-client.ts，替代散落在各处的原生 fetch
- 从 useAuth() 取 token，自动附加 Bearer header
- 支持两种请求：普通 JSON 和 SSE ReadableStream（返回值和原生 fetch 一致）
- useChatStream 内部 fetch → apiClient.fetch（解耦，不直接依赖 auth SDK）

#### apiClient 内部处理流程

```
apiClient.fetch(url, options)
  → 1. 从 useAuth() 取 token
  → 2. token 过期检查
      → 未过期：直接使用
      → 已过期：进入刷新锁（refreshPromise 去重）
         → 已有刷新进行中？复用同一个 Promise 等待
         → 没有刷新？发起刷新，创建 Promise
         → 刷新成功：检查用户是否已退出（是则丢弃结果）
         → 刷新失败：传播给所有等待者
  → 3. 附加 Authorization: Bearer {token}
  → 4. 发送请求
  → 5. 响应处理
      → 非 401：直接返回 Response
      → 401 且非重试请求：拿新 token 重试一次
      → 401 且已是重试（X-Retry 标记）：抛异常，跳转登录页
```

#### 刷新锁（refreshPromise）防御场景

| 场景 | 行为 |
|------|------|
| 多个请求同时发现过期 | 只刷新一次，共享同一个 Promise 结果 |
| 刷新进行中用户点退出 | 刷新成功后检查退出状态，丢弃新 token |
| 刷新本身失败 | finally 清空 refreshPromise，reject 传播给所有等待者 |
| 刷新请求本身返回 401 | X-Retry 标记防止无限循环 |
| 飞行中请求遇到 401 | 拿已刷新的新 token 重试（旧 token 未被作废，仅自然过期才 401） |
| 多 Tab 不同步 | SDK storage-sync 监听跨 Tab + 401 兜底 |

#### 新增/修改文件清单（前端部分）

```
新增：
  src/lib/api-client.ts             # 统一网络层（token 注入 + 刷新锁 + 401 重试）

修改：
  src/hooks/use-chat-stream.ts      # 内部 fetch → apiClient.fetch
```

### 3. 认证时序

```
前端自检（体验优化）：发请求前检查过期，过期先续期
后端验证（安全保障）：JWT 解码 + 签名校验 + 过期检查 + 提取 user_id
401 兜底：后端返回 401 → apiClient 自动续期 + 重试一次 → 仍失败跳转登录
```

前端自检和后端验证的职责区分：
- 前端自检：只是看过期时间（exp），避免无效请求，不是安全验证
- 后端验证：校验签名（防篡改）+ 过期 + 提取 user_id，不可跳过

## R006/R007/R008 路线规划

```
R006（本轮）：
  ✅ 鉴权打通（JWT Depends 注入）
  ✅ apiClient（前端统一网络层）

R007（消息持久化 + 对话管理）：
  ✅ PostgreSQL 消息持久化（解决 RISK-006）
  ✅ 对话列表 UI + 切换对话
  ✅ 页面刷新从后端加载（替代 localStorage）

R008（Agent 重构）：
  ✅ 引入 LangGraph 重构后端为 Agent 架构
  ✅ 多轮上下文管理
  ✅ messages 表格式兼容 LangChain（R007 已铺路）
```

## 不做（已确认）

- 不改 auth-center 服务代码
- 不改 auth-sdk-web SDK 代码
- 不做消息持久化（留给 R007）
- 不做对话列表 UI（留给 R007）
- 不做 WebSocket（继续用 SSE）
- 不引入 LangChain/LangGraph（留给 R008）
- 不做多轮对话上下文管理（留给 R008）
- 不做教材页面图片查看
- 不做 👍👎 反馈按钮
