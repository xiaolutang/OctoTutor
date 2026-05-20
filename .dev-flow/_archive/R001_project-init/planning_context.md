# Planning Context: R001 项目初始化

> generated_at: 2026-05-19
> feature_list_version: 1.4
> requirement_cycle: R001

## Source Analysis
- `.dev-flow/analysis/2026-05-19--1期需求汇总.md` — 全功能需求汇总
- `.dev-flow/analysis/2026-05-19--login-sdk-integration.md` — 登录 SDK 接入方案设计

## Source Decisions
- 无旧决策记录

## Architecture Understanding
- 涉及模块：项目脚手架、认证接入层、路由保护、Header UI
- 已有约束：
  - auth-sdk-web 只能在客户端运行（依赖 localStorage/window/sessionStorage）
  - 所有使用 SDK 的组件必须 `'use client'`
  - SDK 初始化必须在 `useEffect` 中（避免 SSR 报错）
  - /callback 页面的 `useSearchParams()` 必须在 Suspense 边界内
- 架构影响：无（纯前端接入，不改变现有架构）
- 禁止事项：
  - 不修改 SDK 代码
  - 不自建认证体系
  - 不在 Next.js Middleware 中使用 SDK（Edge Runtime 不兼容）
- 需要后续任务处理的架构点：无

## Interaction Chain
1. 学生访问 OctoTutor → SDK init 检查登录状态 → 已登录进入首页 / 未登录显示登录按钮
2. 点击登录 → authService.login() → 跳转 auth-center 授权页
3. auth-center 登录（账号密码/飞书扫码） → 302 回调 /callback?code=xxx&state=xxx
4. /callback 页面 → handleCallback() → 校验 state + PKCE → code 换 token → 存 localStorage → 获取用户信息
5. 跳转首页 → Header 显示用户名
6. Token 过期 → SDK 自动续期（用户无感知）
7. 点击登出 → 调 auth-center 登出 API → 清 localStorage → 跳转登录页
8. 跨 Tab → storage 事件同步登出状态

## Logic Tree
```text
访问页面
├─ SDK init (config.json → AuthService)
├─ 检查 token
│  ├─ 有 → fetchUserInfo() → 进入页面
│  └─ 无 → 显示登录按钮
├─ 登录
│  ├─ authService.login()
│  │  ├─ 生成 state + PKCE → sessionStorage
│  │  └─ window.location.href → auth-center
│  └─ /callback
│     ├─ handleCallback()
│     │  ├─ 校验 state (防 CSRF)
│     │  ├─ code + code_verifier → POST /auth/token
│     │  ├─ 存 localStorage
│     │  └─ fetchUserInfo()
│     └─ redirect → 首页
├─ 会话管理
│  ├─ TokenManager 自动续期 (JWT exp - 60s)
│  ├─ 401 自动重试
│  └─ 跨 Tab 同步 (storage 事件)
└─ 登出
   ├─ POST /auth/logout (Bearer token)
   ├─ clearTokens()
   └─ 跳转登录
```

## Function Network
| Module | Relation | Direction | Reason | Risk |
|--------|----------|-----------|--------|------|
| auth-sdk-web | 依赖 | in | 提供全部认证能力 | 低 |
| auth-center (Docker) | 依赖 | in | OAuth 授权 + Token 签发 + 用户信息 | 中（需 Docker 运行） |
| Header UI | 被依赖 | out | 需要读取 auth 状态显示用户名/登出 | 低 |

## Solution Design
- 方案目标：在 Next.js App Router 中接入 auth-sdk-web，跑通登录-使用-登出完整链路
- 选定方案：SDK 在 Client Layout 初始化，Context 向全局传递，/callback 独立页面处理
- 模块与边界：
  - AuthContext Provider（'use client'，useEffect 初始化 SDK）
  - useAuth() hook（login/logout/user/isAuthenticated）
  - /callback 页面（handleCallback → redirect）
  - RouteGuard 组件（未登录跳转）
  - Header UI（用户名 + 登出）
  - public/config.json（运行时配置）
- 数据/API/配置/第三方集成：
  - SDK 本地 file: 引用
  - config.json 运行时加载（clientId 复用 playground 的）
  - auth-center 外部服务（已部署）
  - Token 存储 SDK 内部管理 localStorage
- 状态与错误处理：
  - SDK init 失败 → 提示刷新
  - OAuth code 无效 → 清除 state/PKCE，提示重试
  - state 校验失败 → 阻止 CSRF，提示重试
  - Token 续期失败 → 清除 token，跳转登录
  - 登出 API 失败 → 仍清本地，正常跳转
- 测试与发布策略：
  - 集成测试必须连真实 auth-center（本地 Docker）
  - 不 mock 认证流程
  - 纯前端变更，Vercel 自动回滚
- 回滚或降级：纯前端，Vercel 自动回滚

## Business Flow
1. 搭建 Next.js 脚手架 → 可运行的空项目
2. 引入 SDK + 初始化 → 页面可检查登录状态
3. 实现 /callback → OAuth 回调跑通
4. 实现路由保护 → 未登录自动跳转
5. Header UI → 登录状态可视 + 登出
6. 端到端验证 → 全链路通畅

## State Transitions
| From | Event | To | Notes |
|------|-------|----|-------|
| 未登录 | authService.login() | 认证中心授权页 | 整页跳转 |
| 认证中心 | 登录成功 | /callback?code=xxx | 302 回调 |
| /callback | handleCallback() 成功 | 已登录（首页） | token 存 localStorage |
| /callback | handleCallback() 失败 | 错误提示 | 不存 token |
| 已登录 | Token 即将过期 | 自动续期 | 用户无感知 |
| 已登录 | 续期失败 | 未登录（跳转登录） | 清除 token |
| 已登录 | logout() | 未登录（登录页） | 清除 token + auth-center 登出 |

## Decision Items
| ID | Source | Summary | Type | Must Plan |
|----|--------|---------|------|-----------|
| DEC-auth-001 | analysis/login-sdk-integration.md | SDK 引入方式：本地 file: | tech_choice | no |
| DEC-auth-002 | analysis/login-sdk-integration.md | 运行时配置：config.json | tech_choice | no |
| DEC-auth-003 | analysis/login-sdk-integration.md | 路由保护粒度 | user_behavior | yes |

## Capability Model
| ID | Name | Source Analysis | Journey Type | Risk Tags | Must Plan | Required Evidence |
|----|------|-----------------|--------------|-----------|-----------|-------------------|
| CAP-auth-001 | OAuth 登录回调 | login-sdk-integration.md | auth/oauth | auth,network | yes | entry_action, actual_authorize_or_endpoint, callback_or_completion, state_or_identity_check, user_visible_success, failure_path_result |
| CAP-auth-002 | Token 自动续期 | login-sdk-integration.md | auth | auth | yes | user_visible_success, failure_path_result |
| CAP-auth-003 | 登出 | login-sdk-integration.md | auth | auth | no | user_visible_success |
| CAP-auth-004 | 路由保护 | login-sdk-integration.md | standard | ux | no | user_visible_success, failure_path_result |

## Contract Impacts
- 复用：无（纯前端接入）
- 新增：无
- 变更风险：无

## Integration Test Strategy
- mode: local_docker
- commands: cd xlfoundryTest && docker compose up -d
- mock_policy: mock_allowed_for_unit_only
- required_for: auth, oauth, callback, network
- confirmed_by_user: true
- notes: 复用 xlfoundryTest 的 auth-center Docker 环境

## Risks
- Next.js SSR 与 SDK 浏览器 API 冲突 → 确保 'use client' + useEffect 初始化
- auth-center Docker 未启动 → 开发文档说明启动步骤

## Open Issues
- 无

## Out Of Scope
- 飞书登录：auth-center 内部能力，OctoTutor 不感知
- 自定义登录 UI：使用认证中心默认登录页
- 后端 Token 校验：第一期纯前端
- auth-center 后端：外部服务，已部署
- 教材知识库、AI 辅导引擎：后续需求包

## User Confirmation
- confirmed_at: 2026-05-19
- confirmed_scope: R001 项目初始化 — 脚手架搭建 + 登录 SDK 接入 + 端到端验证
- unresolved_questions: 无
