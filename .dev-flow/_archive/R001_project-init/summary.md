# R001 项目初始化 归档

- 归档时间: 2026-05-20
- 状态: completed
- 总任务: 6
- 分支: feat/R001-project-init
- workflow: mode=A / runtime=skill_orchestrated
- providers: evaluate=local / risk=local

## 仓库提交
- OctoTutor: 195818e (HEAD on feat/R001-project-init)

## 任务列表
| 任务 | 描述 | commit |
|------|------|--------|
| R001-F000 | Next.js 项目脚手架搭建 | cf72764 |
| R001-F001 | 引入 auth-sdk-web 并初始化 AuthContext | 1bd984a |
| R001-F002 | Token 管理与会话管理（SDK 内置） | 1bd984a |
| R001-F003 | 实现路由保护组件 RouteGuard | 03720eb |
| R001-F004 | 登出功能（SDK 内置） | 1bd984a |
| R001-F005 | 端到端验证 + 标准部署脚本 | c80fe46 |
| (补充) | 修复 OAuth 回调防重入 + Playwright 集成测试 + 专用 clientId | 195818e |

## 关键交付
- Next.js 16.2.6 App Router 项目脚手架（standalone 模式）
- 接入 @xlfoundry/auth-sdk-web，实现 OAuth 2.0 Authorization Code + PKCE 登录
- AuthContext Provider + useAuth hook + RouteGuard 路由保护
- 标准 deploy/ 部署脚本（本地 Docker + 远程一键部署）
- Playwright E2E 集成测试 6 个场景全部通过
- OctoTutor 专用 clientId (MlP4hO8DKk-BOByD)

## Capability Claims vs Evidence
| Capability | Claimed Status | Evidence | Result |
|------------|----------------|----------|--------|
| CAP-auth-001 OAuth 登录回调 | completed | evidence/R001_R001-F005.md | pass |
| CAP-auth-002 Token 自动续期 | completed（SDK 内置） | evidence/R001_R001-F002.md | pass |
| CAP-auth-003 登出 | completed（SDK 内置） | evidence/R001_R001-F004.md | pass |
| CAP-auth-004 路由保护 | completed | evidence/R001_R001-F005.md | pass |

## Notes
- 旧流程任务（无 Sprint Contract），按兼容规则归档
- F001-F004 能力旅程证据在 F005 端到端验证中补充覆盖
- auth-center CORS 白名单已添加 octotutor.localhost / octotutor.xiaolutang.top
