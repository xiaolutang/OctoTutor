# Vibe Coding 全栈实战：章鱼哥解题 01｜搭好产品底座与登录链路

> OctoTutor（章鱼哥解题）是我正在从 0 到 1 搭建的 AI 解题助手。第一阶段先不碰复杂的智能体编排，而是把一个真实产品最基础的链路跑通：访问、登录、调试和上线。

## 一、故事背景：为什么要做这个系列

高峰期每天消耗约 6 亿 token——这是我现在用 AI 写代码的日常。从"让 AI 写个函数"到"让 AI 搭一个页面"，我越来越依赖 **Vibe Coding** 这种开发方式：用自然语言描述意图，由 AI 生成实现代码，我来负责审查、决策和组装。

但用着用着，我开始好奇一个更大的问题：**Vibe Coding 到底能不能支撑一个完整项目？**

不只是写一个函数、一个组件、一个页面，而是从 0 到 1 做一个真实的全栈产品：有需求分析，有技术选型，有登录，有前后端，有本地开发环境，也有线上部署。AI 能不能一路参与？哪些地方它能直接搞定，哪些地方还是需要人来判断、兜底和收口？

所以我决定拿一个真实项目做实验：**探索 Vibe Coding 从 0 到 1 实现全栈项目的完整过程。**

OctoTutor（章鱼哥解题）就是这个实验对象。它的目标是做一个面向高中数学学习场景的 AI 解题助手：用户可以输入题目，系统不是直接给出答案，而是解释思路、拆解步骤、指出易错点，最终像一个耐心的数学助教一样陪学生把题做明白。

---

## 二、产品要做什么：先确定最终形态和技术框架

OctoTutor 不是一开始就直接进入开发的。我先和 AI 做了一轮需求对齐，把一个问题说清楚：**这个产品到底要帮学生完成什么任务？**

### 2.1 产品的最终形态

最后定下来的产品定位是：**基于固定高中数学教材的启发式问答助手**。

这里面有两个关键词。

第一个是“固定高中数学教材”。章鱼哥不是一个什么都答的通用聊天机器人，它先只服务高中数学，而且知识来源限定在固定教材里。这样做不是因为通用问答不重要，而是因为数学解题最怕“看起来讲得很顺，但依据不清楚”。先把知识范围收窄，后面才有机会把回答质量做扎实。

第二个是“启发式”。我不希望它变成一个直接吐答案的工具。学生输入题目后，它应该更像一个助教：先判断题目考什么知识点，再拆出关键步骤，必要时反问一句，提醒容易错的地方，最后让学生知道这道题为什么这样做。

所以第一版产品的目标链路是这样的：

```
登录 → 进入对话 → 提问（文字/图片） → AI 基于固定教材启发式引导 → 继续追问或结束
```

顺着这条链路往下拆，完整 MVP 至少要满足几类用户需求：

- 学生能登录自己的学习空间
- 学生能用文字描述问题，也能上传题目图片
- 系统能看懂题目在问什么，并判断它大概对应哪些高中数学知识点
- 回答不能只是给最终答案，而是要拆解思路、提示关键步骤和易错点
- 学生没听懂时，可以继续追问，而不是每次都重新开始
- 学生之后能回看之前问过的问题和解题过程

这也是我觉得适合拿它做 Vibe Coding 实验的原因。它不是一个只有前端页面的小 demo，也不是一上来就复杂到不可控的平台系统。它有完整产品形态，有登录，有知识库，有 AI 能力，有部署上线，刚好可以观察 AI 在一个真实全栈项目里到底能走多远。

不过完整方向定下来，不代表后面就按这份清单机械执行。真实开发过程中，经常会在讨论和实现里冒出新的想法，也会因为时间、依赖和技术风险不断修正优先级。

### 2.2 技术框架的选型

知道要做什么之后，下一步才是决定怎么做。这里我先回答几个最基础的问题：为什么先做 Web，前端用什么，后端用什么。

**为什么是 Web？**

如果做移动端 App，用户体验当然可以更贴近学生日常使用场景，但对个人开发者来说，成本会明显变高。iOS 和 Android 都要处理应用打包、真机调试、商店审核、版本发布、隐私合规等问题。尤其是早期产品还在快速变化时，每次改动都走一轮客户端发布流程，迭代速度会被拖慢。

Web 是相对成本最低的方式。浏览器打开就能用，发布也更简单；出了问题可以直接在线上修，不需要等用户更新 App。更重要的是，Web 很适合快速搭一条从前端到后端的全栈链路：页面、登录、API、部署、域名、HTTPS 都能在一套工程节奏里跑通。

所以第一版先选 Web，不是因为它是最终形态的唯一答案，而是因为它最适合验证产品和技术链路。

**前端为什么选 Next.js？**

前端我选择 Next.js App Router。这个选择主要是为了少拆一些基础设施：路由、页面布局、API Route、middleware、构建输出都在同一个框架里完成。对于一个从 0 到 1 的项目来说，这比自己组合 React、路由、构建工具和部署方式更省心。

这篇文章里最先用到的能力就是这些：

- `app/` 目录组织页面和布局
- `callback/page.tsx` 处理 OAuth 回调
- `api/config/route.ts` 提供运行时配置
- `middleware.ts` 控制 dev sandbox 的生产访问
- `output: "standalone"` 方便 Docker 部署

**后端为什么选 Python / FastAPI？**

后端我倾向用 Python / FastAPI。原因很直接：后面会接教材解析、RAG、Embedding、模型调用和评估脚本，这些能力在 Python 生态里更顺手。FastAPI 本身也足够轻量，写 API、定义请求响应模型、跑本地服务都很快。

不过第一篇的重点不是后端智能能力，而是先把产品底座跑通。所以这一阶段后端不会展开讲，先把前端入口、认证链路和部署方式立住。

最终这一轮的技术框架先收成这样：

| 层级 | 选择 | 理由 |
|------|------|------|
| 产品形态 | Web 应用 | 个人开发成本低，发布快，适合先验证全栈链路 |
| 前端框架 | Next.js 16 (App Router) | 路由、布局、API Route、middleware 和部署输出都比较完整 |
| 后端框架 | Python / FastAPI | 后续 AI、RAG、评估脚本更适合接 Python 生态 |
| 部署方式 | Docker standalone | 一个镜像搞定，方便本地和线上保持一致 |

---

## 三、确定第一期实施范围：先把基础和登录跑通

产品方向定下来后，真正进入开发时还要做取舍。AI 解题助手最终要接教材知识库、图片识别和启发式引导，但这些能力都依赖一个前提：应用本身得先能跑起来，用户身份链路也得先跑通。

所以第一轮实施范围被收窄成 **R001 项目初始化**。

这一轮只做几件事：

1. 搭建 Next.js 项目脚手架
2. 接入自有登录 SDK
3. 跑通 OAuth 登录、回调、登出
4. 做 RouteGuard 路由保护
5. 补齐 Header 登录状态展示
6. 补齐基础部署脚本
7. 用端到端测试验证完整登录链路

也就是说，需求分析决定的是“产品要做成什么样”，R001 决定的是“第一期先交付什么”。第一期没有直接做 AI 解题，而是先把脚手架、登录、路由保护、部署脚本和验证链路打通。后面再接教材知识库、图片识别和智能体能力时，基础工程问题就不会反复打断主线。

### 3.1 本阶段的项目结构

到这个阶段，项目结构大致是这样：

```
src/
├── app/
│   ├── layout.tsx          # 根布局：AuthProvider + Header
│   ├── page.tsx            # 首页
│   ├── api/config/route.ts # 运行时配置（后面会讲这个决策的故事）
│   ├── callback/page.tsx   # OAuth 回调
│   ├── chat/page.tsx       # 解题对话页
│   └── dev/page.tsx        # 开发沙箱（生产环境自动裁剪）
├── contexts/auth-context.tsx  # 认证上下文
├── components/
│   ├── header.tsx          # 全局导航
│   └── route-guard.tsx     # 路由保护
└── middleware.ts           # /dev 路由守卫
```

这个结构的核心理念是：**每个目录就是一个独立的功能域**，`app/` 目录即路由，`components/` 是共享组件，`contexts/` 管理全局状态。后面新增运行时配置和 dev sandbox 时，也都顺着这个结构往里加，没有额外再拆一套工程。

---

## 四、完善基础登录功能：OAuth 2.0 + PKCE 的完整链路

R001 的范围定下来后，先搭脚手架，然后第一个要跑通的核心链路就是登录。这是所有用户功能的起点。

### 4.1 认证架构：不自建，复用已有的 auth-center

我没有选择自建用户系统。原因很简单：

1. 已有一个基于 auth-center 的统一认证平台（之前搭建的统一认证服务）
2. 它支持 OAuth 2.0 Authorization Code + PKCE 流程
3. 有现成的客户端 SDK（`@xlfoundry/auth-sdk-web`）

架构关系是这样的：

```
用户浏览器 → OctoTutor 前端 → (跳转) → auth-center 登录页
                                          ↓ (授权码回调)
                                     OctoTutor /callback → SDK 换 token → 登录完成
```

### 4.2 第一个坑：OAuth 回调被触发了两次

在接入 SDK 后，第一个遇到的问题是 **回调页面被重复处理**。

React StrictMode 会在开发模式下重复触发副作用，导致 `handleCallback()` 被调用两次。第二次调用时 OAuth state 已经被消费掉了，直接报错。

**解决方案**：用 `useRef` 做防重入：

```typescript
const processedRef = useRef(false)

useEffect(() => {
  if (!isInitialized || processedRef.current) return
  processedRef.current = true
  handleCallback().then(() => router.replace(consumeReturnUrl()))
}, [isInitialized])
```

这个 pattern 后来在多个项目中被复用——只要是"只执行一次"的副作用，都用 ref 而不是 state 来控制。

### 4.3 第二个坑：登录后跳到了首页，而不是回到原来的页面

用户访问 `/chat` 这种受保护页面时，会先被 RouteGuard 带去登录。问题是登录成功后页面跳到了 `/`，而不是回到一开始想访问的 `/chat`。这是一个影响所有受保护页面的问题。

**分析**：OAuth 登录涉及页面跳转（离开当前站点去 auth-center），回来后 React 组件树重建，之前的路由状态丢失。

**解决方案**：在 `login()` 调用前，把当前路径存到 `sessionStorage`，回调时读回来：

```typescript
// auth-context.tsx
function saveReturnUrl() {
  sessionStorage.setItem("xlfoundry_auth_return_url",
    window.location.pathname + window.location.search)
}

export function consumeReturnUrl(): string {
  const url = sessionStorage.getItem("xlfoundry_auth_return_url") || "/"
  sessionStorage.removeItem("xlfoundry_auth_return_url")
  return url
}
```

这个方案的优点是：**集中管理在 `login()` 函数内部**，所有页面的登录按钮自动受益，不需要每个页面单独处理。

### 4.4 第三个坑：配置信息硬编码在前端代码里

最初的实现是 `public/config.json` 静态文件，包含 `clientId` 和 `authCenterBaseURL`。问题是：

- 本地开发用 `http://auth.localhost`
- 线上用 `https://auth.xiaolutang.top`
- 每次发布都要改这个文件

**方案演进**：我考虑过三种方式：


| 方案                     | 优点                       | 缺点                           | 结论     |
| ------------------------ | -------------------------- | ------------------------------ | -------- |
| `NEXT_PUBLIC_*` 环境变量 | Next.js 原生支持           | **构建时固化**，运行时无法更改 | 放弃     |
| `publicRuntimeConfig`    | 运行时读取                 | standalone 模式**不兼容**      | 放弃     |
| API Route`/api/config`   | 运行时从服务端环境变量读取 | 多一次网络请求                 | **采用** |

最终方案：新增一个 API Route，从环境变量读取配置返回给客户端：

```typescript
// src/app/api/config/route.ts
export async function GET() {
  const clientId = process.env.AUTH_CLIENT_ID
  const authCenterBaseURL = process.env.AUTH_BASE_URL
  if (!clientId || !authCenterBaseURL) {
    return NextResponse.json({ error: "Missing config" }, { status: 500 })
  }
  return NextResponse.json({ clientId, authCenterBaseURL })
}
```

这样每个环境的配置只在 Docker Compose 里声明一次：

```yaml
# 本地 docker-compose.local.yml
environment:
  - AUTH_CLIENT_ID=local-client-id
  - AUTH_BASE_URL=http://auth.localhost

# 线上 docker-compose.yml
environment:
  - AUTH_CLIENT_ID=${AUTH_CLIENT_ID}   # 从远端 .env 文件读取
  - AUTH_BASE_URL=${AUTH_BASE_URL}
```

同一个 Docker 镜像，本地和线上只是环境变量不同，部署时不需要改任何代码。

---

## 五、构建自己的 Playground：给后续智能体开发留调试空间

登录跑通后，后续开发需要一个能快速调试各种功能的地方。这也是我和 AI 在下一轮需求里继续补的内容：给项目加一个只在开发环境使用的 Playground。

### 5.1 为什么需要一个开发沙箱

AI 产品的开发过程中，有大量需要快速验证的场景：登录状态切换、组件效果预览、API 调试，后面还会有模型响应、工具调用、流式输出、解题步骤渲染等调试需求。如果每次都走正式页面，效率太低。

我在 `/dev` 路由下搭建了一个开发沙箱，集中展示：

- **认证状态**：一键登录/登出，实时显示用户信息
- **庆祝动效**：Canvas 粒子火焰系统
- **快捷入口**：各页面跳转链接

Playground 的价值不只是“方便看效果”，更重要的是把开发验证和正式产品页面隔离开。后续每接入一个智能体能力，都可以先在这里验证输入输出、异常状态和交互体验，再决定是否进入正式页面。

### 5.2 生产环境保护：双重防线

dev 沙箱不能暴露给线上用户。我设计了两层防护：

**第一层：构建时裁剪**

Dockerfile 里加了一个 build arg：

```dockerfile
ARG EXCLUDE_DEV=false
RUN if [ "$EXCLUDE_DEV" = "true" ]; then rm -rf ./src/app/dev; fi
```

线上构建传 `--build-arg EXCLUDE_DEV=true`，直接从源码层面删除 dev 页面。

**第二层：运行时拦截**

即使构建时没有裁剪，middleware 也会拦截：

```typescript
export function middleware() {
  if (process.env.ENABLE_DEV_SANDBOX !== "true") {
    return NextResponse.rewrite(new URL("/not-found", "http://localhost"))
  }
  return NextResponse.next()
}
```

只有显式设置 `ENABLE_DEV_SANDBOX=true` 才能访问 `/dev`，线上默认不设置。

### 5.3 一个小彩蛋：火焰粒子庆祝动效

在基础架构搭建完成后，我在 dev 沙箱里做了一个 Canvas 2D 火焰粒子系统来庆祝：

- 300 个粒子，3 层渲染（红、橙、黄）
- 全屏 Overlay，展示项目名和技术栈
- ESC 键或按钮关闭

这不是核心功能，但它让开发过程有了仪式感。从零到一构建一个项目，每一步都值得庆祝。

---

## 六、发布上线：从本地到线上的完整部署链路

开发沙箱就绪，登录链路也跑通了，接下来就是把产品部署到线上。

### 6.1 部署架构

线上部署架构：

```
用户 → https://octotutor.xiaolutang.top
          ↓ (TLS)
       Traefik 网关 (gateway network)
          ↓ (Docker 内部网络路由)
       octotutor 容器 (port 3000)
          ↓ (auth-network)
       auth-center 容器
```

关键技术决策：

- **Traefik 网关**：复用已有的 Traefik 实例，通过 Docker labels 自动注册路由
- **TLS 证书**：Traefik 自动管理 Let's Encrypt 证书
- **双网络隔离**：`gateway` 网络对外暴露，`auth-network` 网络用于内部服务通信

### 6.2 一键部署脚本

部署流程从手动操作进化到一键脚本：

```bash
./deploy/remote-deploy.sh
```

脚本执行 5 个步骤：

```
[0/5] SSH 连通性检查
[1/5] 本地构建 Docker 镜像（交叉编译 linux/amd64）
[2/5] 导出镜像（docker save | gzip，仅 53MB）
[3/5] SCP 传输到服务器
[4/5] 远端加载镜像 + 生成 .env + docker compose up
```

### 6.3 环境隔离的实现方式

最关键的设计是 **`.remote.env` 文件留在本地**，不提交 git：

```bash
# deploy/.remote.env（本地文件，在 .gitignore 中）
REMOTE_HOST=your.server.ip
REMOTE_USER=root
AUTH_CLIENT_ID=your-client-id
AUTH_BASE_URL=https://auth.xiaolutang.top
```

部署脚本读取这个文件，把 AUTH 变量传递到远端，在远端生成 `.env` 供 Docker Compose 使用。这样：

- 敏感配置不进 git
- 本地开发配置不进 git
- 同一个镜像可以部署到任何环境

### 6.4 线上验证清单

部署完成后需要验证的关键链路：

1. HTTPS 访问 `https://octotutor.xiaolutang.top/` → 200
2. `/api/config` 返回正确的线上配置
3. 点击登录 → 跳转 auth-center → 登录成功 → 回到原页面
4. `/dev` 路由返回 404（生产环境保护生效）

---

## 七、写在后面：第一阶段解决了什么

回头看这一阶段，踩了不少坑，但也有几个决策做对了：

1. 没有自建用户系统，复用了 auth-center——省下了大量工作
2. 配置从静态文件改成了运行时注入——部署时再也不用改代码了
3. 搭了独立的开发沙箱——调试方便，也不怕污染生产环境
4. 用了 Docker standalone 模式——远端部署时传输的压缩包只有约 53MB

更重要的是，这一阶段让我再次确认了一件事：AI 辅助编码很擅长生成局部实现，但真实产品的麻烦经常藏在模块之间。登录链路、运行时配置、开发入口、生产保护、部署验证，这些地方单独看都不复杂，放到一起就需要反复对齐和验证。

到这里，OctoTutor 已经有了一个可以继续迭代的产品底座：

1. 用户可以访问
2. 登录链路可用
3. 配置可以按环境切换
4. 开发调试有独立 Playground
5. 项目可以一键部署上线

不过这些都还是基础设施，章鱼哥现在还不会解题。下一篇会进入更核心的部分：接入 AI 对话能力，设计解题助手的输入输出，让它从一个“能上线的 Web 应用”开始变成一个“能和学生对话的 AI 助手”。
