# Planning Context: R002 dev-sandbox-enhancement

> generated_at: 2026-05-20T10:05:00Z
> feature_list_version: 1.4
> requirement_cycle: R002

## Source Analysis
- .dev-flow/analysis/2026-05-20--dev-sandbox-celebration.md

## Source Decisions
- 无旧决策记录

## Architecture Understanding
- 涉及模块：src/app/dev/page.tsx（修改）、新增 src/app/dev/celebration.tsx
- 已有约束：
  - dev 页面通过 Dockerfile `rm -rf src/app/dev` 从生产构建排除
  - middleware.ts 在 production 环境拦截 /dev/* 路由
  - useAuth() 在 AuthProvider 子树内可用（layout.tsx 已注入）
- 架构影响：无（所有改动在 dev-only 目录内）
- 禁止事项：不引入外部动画库、不修改生产代码、不在 src/app/dev/ 外创建新文件
- 需要后续任务处理的架构点：无

## Interaction Chain
1. 访问 /dev → 显示 sandbox 页面（生产环境返回 404）
2. 查看登录按钮 → 点击直接跳转认证中心登录
3. 点击庆祝入口 → 打开全屏 Canvas 火焰粒子动效覆盖层
4. 动效显示庆祝文案（章鱼哥主题）→ 点击关闭或 ESC 关闭

## Logic Tree
```text
访问 /dev
├─ 登录按钮
│  ├─ 调用 useAuth().login()
│  └─ 跳转 auth-center OAuth 授权页
├─ 庆祝入口
│  ├─ 点击 → 渲染 CelebrationOverlay
│  │  ├─ Canvas 2D 火焰粒子系统
│  │  │  ├─ 渐变色粒子（红→橙→黄）
│  │  │  ├─ 上升运动 + 随机抖动
│  │  │  └─ 多层叠加
│  │  ├─ 庆祝文案（章鱼哥主题）
│  │  └─ 关闭按钮 + ESC 键监听
│  └─ 关闭 → 卸载 overlay
└─ 生产保护（已有，不需改动）
   ├─ Dockerfile: rm -rf src/app/dev
   └─ middleware: production 拦截 /dev/*
```

## Function Network
| Module | Relation | Direction | Reason | Risk |
|--------|----------|-----------|--------|------|
| dev/page.tsx | depends on | → useAuth() | 登录操作 | 无 |
| dev/page.tsx | depends on | → celebration.tsx | 庆祝动效集成 | 无 |
| celebration.tsx | depends on | → Canvas API | 火焰粒子渲染 | 无 |

## Solution Design
- 方案目标：在 dev sandbox 添加登录快捷按钮和 Canvas 火焰庆祝动效
- 选定方案：Canvas 2D 粒子火焰系统（Option B）
- 模块与边界：所有代码在 src/app/dev/ 内，零外部依赖
- 数据/API/配置/第三方集成：复用 useAuth().login()，无新 API
- 状态与错误处理：overlay 通过 state 控制显隐，ESC/关闭按钮卸载
- 测试与发布策略：已有 middleware 单元测试 + Playwright 集成测试
- 回滚或降级：删除 src/app/dev/ 目录即可

## Business Flow
1. 开发者访问 /dev → 看到登录按钮和庆祝入口
2. 点击登录 → 跳转 auth-center → 完成 OAuth 回调 → 回到 /dev 已登录
3. 点击庆祝 → 全屏火焰粒子动效 + 章鱼哥主题庆祝文案
4. 关闭庆祝 → 回到 sandbox

## State Transitions
| From | Event | To | Notes |
|------|-------|----|-------|
| sandbox 默认 | 点击庆祝 | overlay 显示 | canvas 开始动画 |
| overlay 显示 | 点击关闭 / ESC | sandbox 默认 | canvas 清理 |

## Decision Items
| ID | Source | Summary | Type | Must Plan |
|----|--------|---------|------|-----------|
| DEC-dev-001 | analysis/dev-sandbox-celebration.md | 登录按钮直接调用 useAuth().login() 跳转认证中心 | user_behavior | yes |
| DEC-dev-002 | analysis/dev-sandbox-celebration.md | 火焰动效使用 Canvas 2D 粒子系统，零外部依赖 | boundary | yes |
| DEC-dev-003 | analysis/dev-sandbox-celebration.md | 庆祝文案包含项目主题（章鱼哥、八臂、基础架构里程碑） | user_behavior | no |
| DEC-dev-004 | analysis/dev-sandbox-celebration.md | 所有新代码放在 src/app/dev/ 目录下，确保生产排除 | architecture_impact | yes |

## Capability Model
| ID | Name | Source Analysis | Source Decisions | Journey Type | Risk Tags | Must Plan | Required Evidence |
|----|------|-----------------|------------------|--------------|-----------|-----------|-------------------|
| CAP-dev-001 | 登录快捷操作 | analysis/...celebration.md | DEC-dev-001 | auth | auth | yes | entry_action,user_visible_success |
| CAP-dev-002 | 庆祝里程碑动效 | analysis/...celebration.md | DEC-dev-002 | internal | none | no | entry_action,user_visible_success |

## Contract Impacts
- 复用：useAuth() login/logout 接口
- 新增：无
- 变更风险：无

## Integration Test Strategy
- mode: local_docker
- commands: docker compose up -d（复用 xlfoundryTest auth-center）
- mock_policy: mock_allowed_for_unit_only
- required_for: auth
- confirmed_by_user: true
- notes: Playwright 验证生产 /dev 返回 404（已有 2/2 通过）

## Risks
- Canvas 粒子性能：dev-only 页面，风险可忽略

## Open Issues
- 无

## Out Of Scope
- 生产页面不受任何影响
- 不引入外部动画库
- 不需要额外的生产环境保护测试（已有覆盖）

## User Confirmation
- confirmed_at: 2026-05-20T10:10:00Z
- confirmed_scope: dev sandbox 登录快捷按钮 + Canvas 火焰粒子庆祝动效，所有代码在 src/app/dev/ 内
- unresolved_questions: 无
