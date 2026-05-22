---
type: analysis
status: analyzed
requirement_cycle: R005
date: 2026-05-22
topic: error-scenario-test-strategy
supplement_for: 2026-05-21--R005-chat-ui-sse
supplement_reason: 遗漏补充 — R005 方案文档测试策略章节过于简略，缺少具体的异常场景测试设计、模拟技术和用例矩阵。本文档补充三层测试架构的详细方案。
---

# R005 补充：异常场景测试策略设计

## §1 分析边界

**补充范围**：R005 SSE 对话链路中 7 个异常路径的测试方案设计

**数据来源**：
- 方案文档 910-916 行定义的 7 个异常场景
- 方案文档 918-928 行的简要测试策略（待替换）
- 已有测试代码：`test_chat_service_stream.py`、`test_llm_generator_stream.py`、`test_stream_router.py`、`use-chat-stream.test.ts`、`chat-ui.test.tsx`
- 已有实现代码：`service.py`、`llm.py`、`stream_router.py`、`use-chat-stream.ts`

**不涉及**：新功能设计、架构变更、代码实现

## §2 现有测试覆盖分析

### 后端已有覆盖

| 测试文件 | 覆盖场景 | 遗漏 |
|----------|---------|------|
| `test_chat_service_stream.py` | 正常事件序列、Embedding 异常、VectorStore 异常、Reranker 降级、空检索、LLM 空响应、handle_chat 回归 | **LLM ConnectionError/TimeoutError/通用 Exception**、**意图分类 direct 路径** |
| `test_llm_generator_stream.py` | 正常 token yield、空 chunks 走 MATH_JUDGE_PROMPT、资源释放（正常+异常）、空 token 跳过 | **LLM 连接异常**、**流中异常**、**空 choices chunk**（已修复但无测试） |
| `test_stream_router.py` | SSE 格式、事件序列、断线检测、异常兜底 INTERNAL_ERROR、非流式兼容 | **error event 格式验证不足**、**超时场景** |

### 前端已有覆盖

| 测试文件 | 覆盖场景 | 遗漏 |
|----------|---------|------|
| `use-chat-stream.test.ts` | 正常回调序列、HTTP 非 200→code 00000、流中断→code 00001、fetch 失败→code 00000、AbortController 不触发 onError | **error event（后端返回的 error 类型事件）**、**多 token 分 chunk 到达**、**SSE 格式异常（缺 event/data）** |
| `chat-ui.test.tsx` | 消息创建、code=00000 撤回、code=00001 标记 error、stop、持久化、handleRegenerate、handleEdit | **handleStop 中 retrieving/generating 状态区分**、**onSources 回调行为**、**连续快速发送** |

### 关键缺口汇总

1. **后端 LLM 异常 3 分支未覆盖**：`ConnectionError`→`LLM_CONNECT_FAILED`、`TimeoutError`→`LLM_TIMEOUT`、`Exception`→`LLM_STREAM_ERROR`
2. **后端意图分类路径未覆盖**：`classify_question` 返回 "direct" 时跳过检索直接走 LLM
3. **后端空 choices chunk**：OpenAI SDK 最后一个 chunk 的 `choices=[]` 已修复但无专门测试
4. **前端 error event 接收**：后端 SSE error event（如 `02202`）到达前端时的 `onError` 行为
5. **前端多 chunk SSE 解析**：一个 TCP chunk 包含多个 SSE 事件、不完整事件跨 chunk

## §3 三层测试架构

### 3.1 L1 — 后端单元测试（pytest + mock）

**模拟技术**：

| 外部依赖 | 模拟方式 | 工具 |
|----------|---------|------|
| Embedding (DashScope) | `MagicMock(side_effect=RuntimeError("..."))` | unittest.mock |
| VectorStore (ChromaDB) | `MagicMock(query=MagicMock(side_effect=RuntimeError("...")))` | unittest.mock |
| BM25 | `MagicMock(query=MagicMock(return_value=[]))` | unittest.mock |
| Reranker | `MagicMock(rerank=MagicMock(side_effect=RuntimeError("...")))` | unittest.mock |
| LLM sync (OpenAI) | `patch.object(client.chat.completions, "create")` | unittest.mock |
| LLM async stream (AsyncOpenAI) | `MockAsyncStream` + `patch.object(async_client.chat.completions, "create", new_callable=AsyncMock)` | unittest.mock |
| 异步上下文管理器 | `MockAsyncStream.__aenter__/__aexit__` | 手动实现 |
| async gen 指定位置抛异常 | `async def _failing_stream(query, chunks): yield "token"; raise ConnectionError("...")` 或通用 `make_failing_stream(tokens, fail_after, exception)` helper | 手动实现 |

**模拟 helper — 异常 async generator**：

```python
async def _failing_stream_after(tokens: list[str], fail_after: int, exc: Exception):
    """在第 fail_after 个 yield 后抛出异常的 async generator"""
    for i, t in enumerate(tokens):
        if i == fail_after:
            raise exc
        yield t
```

用法示例：S-ERR-04 用 `_failing_stream_after([], 0, ConnectionError("refused"))`，S-ERR-05 用 `_failing_stream_after(["你", "好"], 1, TimeoutError("timeout"))`，S-ERR-06 用 `_failing_stream_after([], 0, RuntimeError("stream boom"))`。

**用例矩阵 — service.py stream_chat()**：

| ID | 场景 | 模拟方式 | 期望事件序列 | 对应错误码 |
|----|------|---------|-------------|-----------|
| S-ERR-01 | Embedding 调用失败 | `embed_query.side_effect = RuntimeError("dashscope timeout")` | status(retrieving) → error | 02102 |
| S-ERR-02 | VectorStore 查询失败 | `vector_store.query.side_effect = RuntimeError("chroma corrupted")` | status(retrieving) → error | 02103 |
| S-ERR-03 | Reranker 失败降级 | `reranker.rerank.side_effect = RuntimeError("API down")` | status → sources → status → token → done（degraded=True） | 无 error |
| S-ERR-04 | LLM ConnectionError | `generate_stream` async gen 在首个 yield 前抛 `ConnectionError` | status → sources → status → error | 02201 |
| S-ERR-05 | LLM TimeoutError | `generate_stream` async gen 在 token 间抛 `TimeoutError` | status → sources → status → token? → error | 02204 |
| S-ERR-06 | LLM 通用 Exception | `generate_stream` async gen 抛 `RuntimeError` | status → sources → status → token? → error | 02202 |
| S-ERR-07 | LLM 空响应 | `generate_stream` 不 yield 任何 token | status → sources → status → error | 02203 |
| S-ERR-08 | 意图分类 direct | 输入 "你好"，跳过检索直接走 LLM | status(generating) → token → done（无 retrieving/sources） | 无 error |
| S-ERR-09 | 意图分类 direct + LLM 空响应 | 输入 "嗨"，LLM 无输出 | status(generating) → error | 02203 |

**用例矩阵 — llm.py generate_stream()**：

| ID | 场景 | 模拟方式 | 期望行为 |
|----|------|---------|---------|
| L-ERR-01 | 空 choices chunk | 最后一个 chunk `choices=[]` | 跳过，不 IndexError |
| L-ERR-02 | 流中 delta.content=None | chunk 有 choices 但 delta.content=None | 不 yield |
| L-ERR-03 | 流中异常后资源释放 | `__anext__` 抛 RuntimeError | `__aexit__` 仍被调用 |

**用例矩阵 — stream_router.py**：

| ID | 场景 | 模拟方式 | 期望行为 |
|----|------|---------|---------|
| R-ERR-01 | service 层 error event 透传 | `stream_chat` yield error event | SSE 格式 `event: error\ndata: {...}\n\n` |
| R-ERR-02 | 多 error event 不发生 | service 正常完成 | 只有 done 无 error |
| R-ERR-03 | 请求体缺 question | POST body `{"top_k": 5}` | 422 Validation Error |

### 3.2 L1 — 前端单元测试（Vitest + mock fetch）

**模拟技术**：

| 场景 | 模拟方式 | 工具 |
|------|---------|------|
| fetch 返回非 200 | `fetchSpy.mockResolvedValue({ ok: false, status: 500 })` | vi.fn + vi.stubGlobal |
| fetch 网络异常 | `fetchSpy.mockRejectedValue(new TypeError('Network error'))` | vi.fn |
| SSE 流中断 | `ReadableStream` pull 第二次 `controller.error()` | Web API |
| 后端 error event | `mockFetchSSE([{ type: 'error', data: { code: '02202', ... } }])` | 自定义 helper |
| 多 chunk 到达 | `ReadableStream` 分多次 enqueue | Web API |
| AbortController | `abortController.abort()` + fetch reject `DOMException('AbortError')` | Web API |
| 不完整 SSE 数据 | `controller.enqueue(encoder.encode('event: tok'))` 不发 `\n\n` | Web API |

**用例矩阵 — use-chat-stream.ts chatStreamFetch()**：

| ID | 场景 | 模拟方式 | 期望行为 |
|----|------|---------|---------|
| F-ERR-01 | 后端 error event | SSE 流包含 `event: error` | `onError({ code: '02202', ... })`，不调 `onDone` |
| F-ERR-02 | 后端 error event + 前面有 token | 先 token event 再 error event | `onToken` + `onError`，不调 `onDone` |
| F-ERR-03 | SSE 格式异常（缺 event 行） | chunk 只有 `data: {...}\n\n` | 事件类型为空，静默跳过 |
| F-ERR-04 | 多事件合并 chunk | 一个 chunk 包含 2 个 `\n\n` 分隔的完整事件 | 两个回调都触发 |
| F-ERR-05 | 不完整事件跨 chunk | 第一个 chunk 只到 `event: to`，第二个补全 `ken\ndata: "x"\n\n` | 合并后正确解析，触发 `onToken` |

**用例矩阵 — chat-ui 核心逻辑**：

| ID | 场景 | 模拟方式 | 期望行为 |
|----|------|---------|---------|
| U-ERR-01 | 后端 error event 触发 onError | `onError({ code: '02202', message: '生成中断', action: 'retry' })` | AI 消息 status='error'，保留已有 content |
| U-ERR-02 | 连续快速发送 | handleSend 调用两次 | 第二次 isStreaming=true 阻止（或排队） |
| U-ERR-03 | handleStop 在 retrieving 状态 | status='retrieving' 时调用 stop | AI 消息 status='stopped'，content=''，保存 |
| U-ERR-04 | handleStop 在 generating 状态 | status='generating' 且有部分 token 时 stop | AI 消息 status='stopped'，content=已有 token，保存 |

### 3.3 L2 — 集成测试（Docker 环境）

**模拟策略**：Docker 环境运行真实后端（ChatService + ChromaDB），仅 mock 外部 API（DashScope/LLM）。

**模拟技术**：

| 场景 | 实现方式 | 工具 |
|------|---------|------|
| LLM 连接超时 | 将 `NEWAPI_BASE_URL` 设为不可达地址 | docker-compose environment |
| LLM 返回慢 | 使用 `NEWAPI_BASE_URL` 指向本地 mock 服务（响应延迟 30s） | 自定义 HTTP server |
| Embedding 失败 | 将 `DASHSCOPE_API_KEY` 设为无效值 | docker-compose environment |
| 完整正常流程 | 使用真实 API Key | docker-compose env_file |

**用例矩阵**：

| ID | 场景 | 环境配置 | 验证方式 |
|----|------|---------|---------|
| I-ERR-01 | LLM 不可达 | `NEWAPI_BASE_URL=http://localhost:1/v1` | curl 验证 SSE error event code=02201 |
| I-ERR-02 | Embedding 认证失败 | `DASHSCOPE_API_KEY=invalid` | curl 验证 SSE error event code=02102 |
| I-ERR-03 | 正常数学问题 | 真实 API Key + ChromaDB 有数据 | curl 验证完整 status→sources→status→token×N→done |
| I-ERR-04 | 闲聊不检索 | 真实 API Key | curl 验证无 retrieving/sources，直接 generating→token→done |

**测试执行脚本设计**：

```bash
#!/bin/bash
# scripts/test-sse-integration.sh
# 在 Docker 后端容器内执行 SSE 集成测试

BACKEND_URL="http://localhost:8000"

echo "=== SSE 集成测试 ==="

# Test 1: 正常流程
echo "--- Test 1: 正常数学问题 ---"
curl -s -X POST "$BACKEND_URL/api/chat/stream" \
  -H "Content-Type: application/json" \
  -d '{"question":"什么是集合？","top_k":5}' | head -20

# Test 2: 闲聊（意图分类 direct）
echo "--- Test 2: 闲聊 ---"
curl -s -X POST "$BACKEND_URL/api/chat/stream" \
  -H "Content-Type: application/json" \
  -d '{"question":"你好","top_k":5}' | head -10

# Test 3: 非流式接口回归
echo "--- Test 3: 非流式回归 ---"
curl -s -X POST "$BACKEND_URL/api/chat" \
  -H "Content-Type: application/json" \
  -d '{"question":"什么是集合？","top_k":5}'
```

## §4 Decision Items

| ID | Type | Description | Must Plan |
|----|------|-------------|-----------|
| DEC-test-001 | architecture | 后端异常测试统一使用 `_build_normal_service` + 修改单个组件 side_effect 模式，保持 test helper 一致性 | no |
| DEC-test-002 | pattern | 前端 SSE 测试使用 `mockFetchSSE` helper 构造 ReadableStream，新增不完整 chunk 场景需扩展 helper | no |
| DEC-test-003 | architecture | L2 集成测试通过 docker-compose environment 变更模拟异常，不引入额外 mock 服务 | yes |
| DEC-test-004 | tool | 后端 L1 使用纯 mock（不依赖 respx/httpx），前端 L1 使用 vi.stubGlobal('fetch') | no |

## §5 集成测试环境策略

**环境隔离与恢复**：

L2 集成测试需要修改 `docker-compose.local.yml` 的 environment 变量来模拟异常。采用 **专用测试 compose override** 方案，不修改原始 compose 文件：

1. 创建 `deploy/docker-compose.test-override.yml`，仅覆盖 environment：
   ```yaml
   services:
     octotutor-backend:
       environment:
         - NEWAPI_BASE_URL=http://localhost:1/v1   # 模拟 LLM 不可达
   ```
2. 测试脚本使用 `-f docker-compose.local.yml -f docker-compose.test-override.yml` 双文件启动，override 自动合并
3. 测试完成后 `docker compose -f docker-compose.local.yml down` 清理测试容器，再用 `deploy.sh --backend-only` 重建正常环境
4. 每个异常场景（I-ERR-01/02）使用独立的 override 文件，互不干扰

**执行流程**：
```bash
# 异常场景测试
docker compose -f docker-compose.local.yml -f docker-compose.test-override.llm-down.yml up -d octotutor-backend
# ... 运行测试断言 ...
docker compose -f docker-compose.local.yml -f docker-compose.test-override.llm-down.yml down

# 恢复正常环境
bash deploy/deploy.sh local --backend-only
```

## §6 风险与缺口

| 风险 | 影响 | 缓解 |
|------|------|------|
| LLM 真实超时难以稳定复现 | L2 集成测试不稳定 | 使用不可达 URL 模拟连接失败，超时场景降级为 L1 mock 测试 |
| Docker 环境依赖真实 API Key | CI 环境可能缺少凭据 | L2 集成测试标记为 `@pytest.mark.integration`，CI 可选跳过 |
| 前端 ReadableStream mock 行为可能与浏览器不一致 | 测试通过但生产有问题 | 关键路径补充手动验证 |

## §7 集成测试要求

- 后端 L2 集成测试需 Docker 环境 + 真实 ChromaDB 数据
- 前端 E2E 测试不在本次补充范围内（需要 Playwright 环境，后续 R006 统一安排）
- L1 mock 测试应覆盖所有错误码枚举值的触发路径
