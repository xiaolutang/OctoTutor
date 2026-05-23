---
version: "3.0"
type: tasks
topic: auth-integration
requirement_cycle: R006
workflow:
  evaluate_provider: local
  mode: A
status: archived
---

# 用户认证打通 — 任务清单

基于 design.md 设计，拆解为 7 个任务。状态管理使用 Cubit，不使用 Event 模式。

---

## 执行顺序

1. ✅ R006-BF001 — JWT 鉴权基础（无依赖）
2. ✅ R006-BB001 — Router Depends 注入（依赖 BF001）
3. ✅ R006-BB002 — 后端鉴权集成验证（依赖 BB001）
4. ✅ R006-FF001 — apiClient 统一网络层（无依赖）
5. ✅ R006-FF002 — AuthContext TokenManager 注册（依赖 FF001）
6. ✅ R006-FB001 — useChatStream 改用 apiClient（依赖 FF001）
7. ✅ R006-FB002 — 前端鉴权集成验证（依赖 FB001 + FF002 + BB002）

---

## R006-BF001：middleware/auth.py — JWT 鉴权基础 `✅ 已完成`

- 文件：`backend/app/middleware/auth.py`（新建）、`backend/app/config.py`（修改）、`backend/requirements.txt`（修改）
- 改动类型：新建 + 修改
- domain: backend
- task_layer: foundation
- depends_on: []
- priority: 1
- risk_tags: [auth, config]
- smoke_required: true
- mode: negotiated
- status: completed
- acceptance_criteria:
  - get_current_user() 可 import
  - 有效 JWT → UserContext 正确提取 user_id/username
  - 无效/过期/缺失 token → HTTPException 401
  - type≠access → 401
  - 缺少 sub → 401
  - JWT_SECRET_KEY 未配置 → 启动失败
- test_tasks:
  - type: unit
    description: 13 个 JWT 验证单元测试
    scenarios: [有效token, 无header, 空Bearer, 错误scheme, 损坏token, 过期token, 边界过期, type≠access, 缺少sub, 空sub, 错误secret, 未配置secret, 正确提取user_id/username]
- contract_refs: [contracts/R006_BF001.md]
- decision_refs: [DEC-auth-001, DEC-auth-007]
- blocked_files: [backend/app/chat/router.py, backend/app/chat/stream_router.py, backend/app/api/routes/retrieve.py]

### BF001.1 新增 middleware 包和 auth.py `✅`

新增 app/middleware/__init__.py + app/middleware/auth.py，包含：
- UserContext(user_id, username) frozen dataclass
- get_current_user(request, credentials) Depends 函数
- HTTPBearer(auto_error=False) 提取 Bearer token
- python-jose HS256 解码验证（签名 + 过期 + type=access + sub 提取）

### BF001.2 修改 config.py 新增 JWT 配置 `✅`

config.py Settings 新增 auth_jwt_secret: str = Field(..., alias="JWT_SECRET_KEY")

### BF001.3 新增依赖和测试 `✅`

requirements.txt 新增 python-jose[cryptography]>=3.3.0
新增 test_middleware_auth.py 覆盖 13 个场景

---

## R006-BB001：router.py/stream_router.py/retrieve.py — Router Depends 注入 `✅ 已完成`

- 文件：`backend/app/chat/router.py`、`backend/app/chat/stream_router.py`、`backend/app/api/routes/retrieve.py`
- 改动类型：修改
- domain: backend
- task_layer: business
- depends_on: [BF001]
- priority: 2
- risk_tags: [auth]
- smoke_required: true
- mode: negotiated
- status: completed
- acceptance_criteria:
  - 无 token POST /api/chat → 401
  - 无 token POST /api/chat/stream → 401
  - 无 token POST /api/retrieve → 401
  - 无 token GET /api/health → 200
  - 有效 token POST /api/chat → 200
  - 有效 token POST /api/chat/stream → SSE 流
  - 有效 token POST /api/retrieve → 200
  - user 参数仅注入不传递到 service 层
- test_tasks:
  - type: integration
    description: 7 个集成测试（TestClient + mock JWT + dependency_overrides）
    scenarios: [无token→401×3, health→200, 有效token→200×3]
- contract_refs: [contracts/R006_BB001.md]
- decision_refs: [DEC-auth-002, DEC-auth-006, DEC-auth-007]
- blocked_files: [backend/app/chat/service.py, backend/app/api/routes/health.py, backend/app/main.py]

### BB001.1 三个路由文件注入 Depends `✅`

每个文件 +1 import +1 参数签名：
```python
from app.middleware.auth import UserContext, get_current_user
async def chat(request: ChatRequest, user: UserContext = Depends(get_current_user), ...):
```

### BB001.2 集成测试 `✅`

新增 test_router_auth_integration.py，7 个场景覆盖全部 Hard Gate

---

## R006-BB002：docker-compose + E2E — 后端鉴权集成验证 `✅ 已完成`

- 文件：`deploy/docker-compose.local.yml`（修改）、`backend/tests/e2e_auth_smoke.sh`（新建）
- 改动类型：修改 + 新建
- domain: integration
- task_layer: business
- depends_on: [BB001]
- priority: 3
- risk_tags: [auth, network, config]
- smoke_required: true
- mode: direct
- status: completed
- acceptance_criteria:
  - Docker 环境中有效 token → 200
  - 无 token → 401
  - 过期 token → 401
  - /api/health 无 token → 200
- test_tasks:
  - type: integration
    description: 9 个 E2E 冒烟测试（python-jose 生成 JWT + curl）
    scenarios: [无token→401×3, health→200, 有效token→non-401×3, 过期token→401×2]
- contract_refs: []
- decision_refs: [DEC-auth-001]
- blocked_files: []

### BB002.1 docker-compose 新增 JWT_SECRET_KEY `✅`

后端服务 environment 新增 JWT_SECRET_KEY=${JWT_SECRET_KEY}

### BB002.2 E2E 冒烟测试脚本 `✅`

新增 e2e_auth_smoke.sh，9 个测试覆盖 CAP-auth-001

---

## R006-FF001：api-client.ts — apiClient 统一网络层 `✅ 已完成`

- 文件：`frontend/src/lib/api-client.ts`（新建）、`frontend/src/__tests__/lib/api-client.test.ts`（新建）
- 改动类型：新建
- domain: ui
- task_layer: foundation
- depends_on: []
- priority: 4
- risk_tags: [auth, network]
- smoke_required: true
- mode: negotiated
- status: completed
- acceptance_criteria:
  - registerGetToken 注册后 fetchWithAuth 自动附加 Authorization header
  - 401 + 刷新成功 → 自动重试一次
  - 401 + X-Retry → 不重试 → 触发 session-expired
  - 并发调用 → refreshPromise 只刷新一次
  - 未注册 getTokenFn → 不附加 header（降级）
  - 30s 超时保护
  - 返回原生 Response（SSE 兼容）
- test_tasks:
  - type: unit
    description: 13 个单元测试（vitest + jsdom + mock fetch）
    scenarios: [token注入, 无token降级, 401重试, 刷新失败, X-Retry防循环, 并发去重, 超时, URL拼接, SSE兼容]
- contract_refs: [contracts/R006_FF001.md]
- decision_refs: [DEC-auth-003, DEC-auth-004, DEC-auth-005]
- blocked_files: [frontend/src/contexts/auth-context.tsx, frontend/src/chat/use-chat-stream.ts]

### FF001.1 新建 api-client.ts `✅`

导出 registerGetToken + fetchWithAuth，核心逻辑：
- BASE_URL='/api'
- refreshPromise 刷新锁 + 30s 超时
- X-Retry 防循环
- auth:session-expired CustomEvent 解耦
- 不导入任何 SDK 类

### FF001.2 单元测试 `✅`

13 个测试覆盖全部 Hard Gate

---

## R006-FF002：auth-context.tsx — AuthContext TokenManager 注册 `✅ 已完成`

- 文件：`frontend/src/contexts/auth-context.tsx`（修改）、`frontend/src/__tests__/contexts/auth-context-token.test.ts`（新建）
- 改动类型：修改
- domain: ui
- task_layer: business
- depends_on: [FF001]
- priority: 5
- risk_tags: [auth]
- smoke_required: true
- mode: negotiated
- status: completed
- acceptance_criteria:
  - TokenManager 独立实例 setConfig 被调用
  - registerGetToken 在 init 后被调用
  - getAccessToken() 返回有效 token
  - auth:session-expired 事件触发 service.login()
  - 不修改已有 login/logout/handleCallback 方法
- test_tasks:
  - type: unit
    description: 8 个测试（mock TokenManager + AuthService）
    scenarios: [setConfig调用, registerGetToken调用, getAccessToken返回token, session-expired触发login, 共享config去重]
- contract_refs: []
- decision_refs: [DEC-auth-003, DEC-auth-008]
- blocked_files: [frontend/src/lib/api-client.ts, frontend/node_modules/@xlfoundry/auth-sdk-web]

### FF002.1 AuthContext 集成 TokenManager `✅`

新增独立 TokenManager 实例 + registerGetToken + auth:session-expired 监听。
提取共享 sdkConfig 变量消除重复配置。

### FF002.2 单元测试 `✅`

8 个测试覆盖全部 Hard Gate

---

## R006-FB001：use-chat-stream.ts — useChatStream 改用 apiClient `✅ 已完成`

- 文件：`frontend/src/chat/use-chat-stream.ts`（修改）
- 改动类型：修改
- domain: ui
- task_layer: business
- depends_on: [FF001]
- priority: 6
- risk_tags: [auth, network]
- smoke_required: true
- mode: direct
- status: completed
- acceptance_criteria:
  - chatStreamFetch 使用 fetchWithAuth 而非原生 fetch
  - URL 路径正确（/chat/stream）
  - SSE 流式接收正常
  - token 自动附加
- test_tasks:
  - type: unit
    description: 验证 fetch 调用替换
    scenarios: [import正确, URL正确, SSE正常]
- contract_refs: []
- decision_refs: [DEC-auth-005]
- blocked_files: []

### FB001.1 替换 fetch 为 fetchWithAuth `✅`

2 行修改：
```typescript
import { fetchWithAuth } from '../lib/api-client'
fetchWithAuth('/chat/stream', { ... })
```

---

## R006-FB002：E2E 测试 — 前端鉴权集成验证 `✅ 已完成`

- 文件：`frontend/tests/e2e_auth_smoke.sh`（新建）
- 改动类型：新建
- domain: integration
- task_layer: business
- depends_on: [FB001, FF002, BB002]
- priority: 7
- risk_tags: [auth, network]
- smoke_required: true
- mode: direct
- status: completed
- acceptance_criteria:
  - 登录 → Chat → SSE 正常
  - token 过期 → 鉴权拒绝
  - 无 token → 401
  - /api/health → 200
  - 前端 Docker 镜像构建成功
- test_tasks:
  - type: integration
    description: 15 个 E2E 冒烟测试
    scenarios: [前端页面加载, health公开访问, 无token鉴权拦截, 有效token SSE, 过期/无效/错误类型token拒绝]
- contract_refs: []
- decision_refs: [DEC-auth-003, DEC-auth-004, DEC-auth-005]
- blocked_files: []

### FB002.1 E2E 冒烟测试脚本 `✅`

新增 e2e_auth_smoke.sh，15 个测试覆盖 CAP-auth-001 到 CAP-auth-004
