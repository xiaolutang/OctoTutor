---
version: "1.0"
type: tasks
topic: ip-direct-access
requirement_cycle: R017
workflow:
  evaluate_provider: local
  mode: direct
plan_format_exemption: true
status: planned
---

# IP 直连改造 — 任务清单

基于 design.md 设计，将线上部署从域名切换到 IP 直连。
全局约束：零代码改动，只改部署配置文件。

---

## 执行顺序

1. ✅ 任务 1 — R017-BF001 docker-compose.yml 路由改造（无依赖）
   - ✅ 1.1 前端 labels 去 Host + 去 TLS
   - ✅ 1.2 后端 labels 去 Host + 去 TLS
2. ✅ 任务 2 — R017-BF002 .remote.env 认证地址更新（无依赖）
3. ⬜ 任务 3 — 部署验证（依赖任务 1、2）

---

## R017-BF001：docker-compose.yml — Traefik 路由去域名去 TLS `✅ 已完成`

- 文件：`deploy/docker-compose.yml`
- 改动类型：配置
- domain: infra
- task_layer: foundation
- depends_on: []
- priority: 5
- risk_tags: [network]
- smoke_required: true
- mode: direct
- status: completed
- acceptance_criteria:
  - ✅ 前端 labels 无 Host()、无 tls、无 certresolver，entrypoints 为 web
  - ✅ 后端 labels 无 Host()、无 tls、无 certresolver，entrypoints 为 web
  - ✅ 文件注释更新为 IP 直连模式说明
- test_tasks: []
- contract_refs: []
- decision_refs: []
- blocked_files:
  - frontend/**
  - backend/**

### BF001.1 前端 labels 改造 `✅`

将 octotutor-frontend 的 Traefik labels 从域名 HTTPS 模式改为 IP HTTP 模式。

改前：
```yaml
labels:
  - "traefik.enable=true"
  - "traefik.http.routers.octotutor-frontend.rule=Host(`${OCTOTUTOR_DOMAIN:-octotutor.xiaolutang.top}`)"
  - "traefik.http.routers.octotutor-frontend.entrypoints=websecure"
  - "traefik.http.routers.octotutor-frontend.tls=true"
  - "traefik.http.routers.octotutor-frontend.tls.certresolver=ali"
  - "traefik.http.routers.octotutor-frontend.priority=1"
  - "traefik.http.routers.octotutor-frontend.service=octotutor-frontend-svc"
  - "traefik.http.services.octotutor-frontend-svc.loadbalancer.server.port=3000"
```

改后：
```yaml
labels:
  - "traefik.enable=true"
  - "traefik.http.routers.octotutor-frontend.rule=PathPrefix(`/`)"
  - "traefik.http.routers.octotutor-frontend.entrypoints=web"
  - "traefik.http.routers.octotutor-frontend.priority=1"
  - "traefik.http.routers.octotutor-frontend.service=octotutor-frontend-svc"
  - "traefik.http.services.octotutor-frontend-svc.loadbalancer.server.port=3000"
```

变更：rule 从 `Host(...)` 改为 `PathPrefix(/)`，entrypoints 从 `websecure` 改为 `web`，删除 `tls=true` 和 `tls.certresolver=ali` 两行。

### BF001.2 后端 labels 改造 `✅`

将 octotutor-backend 的 Traefik labels 从域名 HTTPS 模式改为 IP HTTP 模式。

改前：
```yaml
labels:
  - "traefik.enable=true"
  - "traefik.http.routers.octotutor-backend.rule=Host(`${OCTOTUTOR_DOMAIN:-octotutor.xiaolutang.top}`) && PathPrefix(`/api/`)"
  - "traefik.http.routers.octotutor-backend.entrypoints=websecure"
  - "traefik.http.routers.octotutor-backend.tls=true"
  - "traefik.http.routers.octotutor-backend.tls.certresolver=ali"
  - "traefik.http.routers.octotutor-backend.priority=10"
  - "traefik.http.routers.octotutor-backend.service=octotutor-backend-svc"
  - "traefik.http.services.octotutor-backend-svc.loadbalancer.server.port=8000"
```

改后：
```yaml
labels:
  - "traefik.enable=true"
  - "traefik.http.routers.octotutor-backend.rule=PathPrefix(`/api/`)"
  - "traefik.http.routers.octotutor-backend.entrypoints=web"
  - "traefik.http.routers.octotutor-backend.priority=10"
  - "traefik.http.routers.octotutor-backend.service=octotutor-backend-svc"
  - "traefik.http.services.octotutor-backend-svc.loadbalancer.server.port=8000"
```

变更：rule 从 `Host(...) && PathPrefix(/api/)` 改为纯 `PathPrefix(/api/)`，entrypoints 从 `websecure` 改为 `web`，删除 `tls=true` 和 `tls.certresolver=ali` 两行。

### BF001.3 文件头部注释更新 `✅`

将文件顶部注释从"TLS + 域名路由"更新为"IP 直连 + PathPrefix 路由"。

---

## R017-BF002：.remote.env — AUTH_BASE_URL 更新 `✅ 已完成`

- 文件：`deploy/.remote.env`
- 改动类型：配置
- domain: infra
- task_layer: foundation
- depends_on: []
- priority: 5
- risk_tags: [auth]
- smoke_required: true
- mode: direct
- status: completed
- acceptance_criteria:
  - ✅ AUTH_BASE_URL 值为 `http://111.229.125.161/auth`
- test_tasks: []
- contract_refs: []
- decision_refs: []
- blocked_files:
  - frontend/**
  - backend/**

### BF002.1 AUTH_BASE_URL 改值 `✅`

改前：
```
AUTH_BASE_URL=https://auth.xiaolutang.top
```

改后：
```
AUTH_BASE_URL=http://111.229.125.161/auth
```
