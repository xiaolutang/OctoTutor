---
date: 2026-05-22
type: brainstorm
status: concluded
requirement_cycle: R006
topic: 用户认证打通
---

# 用户认证打通

## 结论
- 要做什么：
  - 后端 JWT 鉴权中间件（FastAPI Depends 注入，HS256 共享密钥）
  - 前端 apiClient 统一网络层（token 注入 + 刷新锁 + 401 重试）
  - useChatStream 改用 apiClient
- 不做什么：
  - 不改 auth-center 服务代码
  - 不改 auth-sdk-web SDK 代码
  - 不做消息持久化（R007）
  - 不做对话列表 UI（R007）
  - 不做 WebSocket / LangChain / LangGraph（R008）
- 关键约束：
  - HS256 共享密钥（本地 Docker 小项目，不是大规模微服务）
  - Depends 注入鉴权（非全局中间件，与现有代码风格一致）
  - apiClient 不导入 SDK 类，通过 registerGetToken 回调解耦
- 核心场景：
  - 登录后自动携带 token → 请求受保护 API → 正常返回
  - token 过期 → apiClient 自动刷新 → 用户无感知
  - 未登录 → 跳转认证中心
- 待确认：
  - （无，全部已确认）

## 关键讨论
- 三种鉴权模式对比，选 HS256 共享密钥理由（小项目 + auth-center 已用 HS256 + 不改 auth-center）
- 前端自检（体验优化）vs 后端验证（安全保障）职责区分
- R006/R007/R008 路线规划：鉴权打通 → 消息持久化 → Agent 重构
