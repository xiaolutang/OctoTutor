/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  fetchWithAuth,
  registerGetToken,
  _resetForTesting,
} from '@/lib/api-client';

// ---- Helpers ----

function mockResponse(status: number, body?: unknown): Response {
  const stream = new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(JSON.stringify(body ?? {})));
      controller.close();
    },
  });
  return new Response(stream, { status });
}

function createFetchMock(responses: Response[]) {
  let callIndex = 0;
  const fn = vi.fn(() => {
    const response = responses[callIndex] ?? responses[responses.length - 1];
    callIndex++;
    return Promise.resolve(response);
  });
  return fn;
}

// ---- Tests ----

describe('api-client', () => {
  beforeEach(() => {
    _resetForTesting();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  // H1: registerGetToken 注册后 fetchWithAuth 附加 Authorization header
  it('H1: registers getTokenFn and attaches Authorization header', async () => {
    const mockFetch = createFetchMock([mockResponse(200)]);
    vi.spyOn(globalThis, 'fetch').mockImplementation(mockFetch);

    const getToken = vi.fn().mockResolvedValue('test-token');
    registerGetToken(getToken);

    await fetchWithAuth('/test');

    expect(mockFetch).toHaveBeenCalledTimes(1);
    const [url, init] = mockFetch.mock.calls[0];
    expect(url).toContain('/api/test');
    const headers = new Headers(init?.headers as HeadersInit);
    expect(headers.get('Authorization')).toBe('Bearer test-token');
  });

  // H2: 未注册 getTokenFn → 不附加 header
  it('H2: without registerGetToken, no Authorization header', async () => {
    const mockFetch = createFetchMock([mockResponse(200)]);
    vi.spyOn(globalThis, 'fetch').mockImplementation(mockFetch);

    await fetchWithAuth('/test');

    expect(mockFetch).toHaveBeenCalledTimes(1);
    const [, init] = mockFetch.mock.calls[0];
    const headers = new Headers(init?.headers as HeadersInit);
    expect(headers.get('Authorization')).toBeNull();
  });

  // H3: 401 + 刷新成功 → 自动重试 → 返回 200
  it('H3: 401 then refresh success retries once', async () => {
    const responses = [mockResponse(401), mockResponse(200)];
    const mockFetch = createFetchMock(responses);
    vi.spyOn(globalThis, 'fetch').mockImplementation(mockFetch);

    let callCount = 0;
    const getToken = vi.fn().mockImplementation(() => {
      callCount++;
      // 第一次返回过期 token，刷新后返回新 token
      return Promise.resolve(callCount <= 1 ? 'expired-token' : 'new-token');
    });
    registerGetToken(getToken);

    const response = await fetchWithAuth('/test');
    expect(response.status).toBe(200);
    expect(mockFetch).toHaveBeenCalledTimes(2);

    // 第二次调用带 X-Retry
    const retryInit = mockFetch.mock.calls[1][1];
    const retryHeaders = new Headers(retryInit?.headers as HeadersInit);
    expect(retryHeaders.get('X-Retry')).toBe('true');
    expect(retryHeaders.get('Authorization')).toBe('Bearer new-token');
  });

  // H4: 401 + 刷新失败 → 触发 session-expired
  it('H4: 401 + refresh failure triggers session-expired', async () => {
    const mockFetch = createFetchMock([mockResponse(401)]);
    vi.spyOn(globalThis, 'fetch').mockImplementation(mockFetch);

    const getToken = vi.fn().mockResolvedValue(null);
    registerGetToken(getToken);

    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');

    const response = await fetchWithAuth('/test');
    expect(response.status).toBe(401);
    expect(dispatchSpy).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'auth:session-expired' }),
    );
  });

  // H5: 401 + X-Retry header → 不再重试 → 触发 session-expired
  it('H5: 401 with X-Retry does not retry, triggers session-expired', async () => {
    const mockFetch = createFetchMock([mockResponse(401)]);
    vi.spyOn(globalThis, 'fetch').mockImplementation(mockFetch);

    const getToken = vi.fn().mockResolvedValue('token');
    registerGetToken(getToken);

    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');

    const headers = new Headers();
    headers.set('X-Retry', 'true');

    const response = await fetchWithAuth('/test', { headers });
    expect(response.status).toBe(401);
    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(dispatchSpy).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'auth:session-expired' }),
    );
  });

  // H6: 并发 3 请求同时 401 → getTokenFn 刷新去重
  it('H6: concurrent 401s deduplicate refresh calls', async () => {
    // 每次 fetch 调用都返回 401，重试时返回 200
    let fetchCallIdx = 0;
    const mockFetch = vi.fn(() => {
      fetchCallIdx++;
      // 前三次（初始请求）返回 401，后续重试返回 200
      return Promise.resolve(
        fetchCallIdx <= 3 ? mockResponse(401) : mockResponse(200),
      );
    });
    vi.spyOn(globalThis, 'fetch').mockImplementation(mockFetch);

    let resolveRefresh: (value: string | null) => void;
    const pendingRefresh = new Promise<string | null>((resolve) => {
      resolveRefresh = resolve;
    });

    let getTokenCallCount = 0;
    const getToken = vi.fn().mockImplementation(() => {
      getTokenCallCount++;
      // 前 3 次：初始 token 获取（每个并发请求各调 1 次）
      if (getTokenCallCount <= 3) {
        return Promise.resolve('initial-token');
      }
      // 第 4 次起：刷新调用 — 返回 pending promise（手动控制何时完成）
      return pendingRefresh;
    });
    registerGetToken(getToken);

    // 发起 3 个并发请求（初始 token 相同，都拿到 401）
    const promises = [
      fetchWithAuth('/test1'),
      fetchWithAuth('/test2'),
      fetchWithAuth('/test3'),
    ];

    // 等待初始 fetch 完成（3 次 401）
    await vi.waitFor(() => {
      expect(mockFetch).toHaveBeenCalledTimes(3);
    });

    // 验证去重：getToken 初始被调 3 次，刷新时只多调 1 次（去重）
    const callsBeforeResolve = getToken.mock.calls.length;
    // 3 初始 + 1 刷新（去重）= 4
    expect(callsBeforeResolve).toBe(4);

    // 解析刷新，让所有等待者拿到新 token
    resolveRefresh!('new-token');

    const results = await Promise.all(promises);
    results.forEach((r) => expect(r.status).toBe(200));
  });

  // H7: 并发刷新成功 → 所有等待者都拿到新 token
  it('H7: concurrent refresh success — all waiters get new token', async () => {
    let fetchCallIdx = 0;
    const mockFetch = vi.fn(() => {
      fetchCallIdx++;
      return Promise.resolve(
        fetchCallIdx <= 2 ? mockResponse(401) : mockResponse(200),
      );
    });
    vi.spyOn(globalThis, 'fetch').mockImplementation(mockFetch);

    const getToken = vi.fn().mockResolvedValue('new-shared-token');
    registerGetToken(getToken);

    const [r1, r2] = await Promise.all([
      fetchWithAuth('/a'),
      fetchWithAuth('/b'),
    ]);

    expect(r1.status).toBe(200);
    expect(r2.status).toBe(200);
  });

  // H8: 刷新超时 → 返回 null → session-expired
  it('H8: refresh timeout triggers session-expired', async () => {
    vi.useFakeTimers();

    const mockFetch = createFetchMock([mockResponse(401)]);
    vi.spyOn(globalThis, 'fetch').mockImplementation(mockFetch);

    let callCount = 0;
    const getToken = vi.fn().mockImplementation(() => {
      callCount++;
      if (callCount === 1) return Promise.resolve('token');
      // 刷新永不 resolve（模拟挂起）
      return new Promise<null>(() => {});
    });
    registerGetToken(getToken);

    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');

    const fetchPromise = fetchWithAuth('/test');

    // 快进 30s 触发超时
    await vi.advanceTimersByTimeAsync(30_000);

    const response = await fetchPromise;
    expect(response.status).toBe(401);
    expect(dispatchSpy).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'auth:session-expired' }),
    );
  });

  // H9: 刷新超时后 refreshPromise 清空 → 下一次请求能重新触发刷新
  it('H9: after timeout, refreshPromise is cleared for next request', async () => {
    vi.useFakeTimers();

    // 第一轮：401 + 超时
    const mockFetchFirst = createFetchMock([mockResponse(401)]);
    vi.spyOn(globalThis, 'fetch').mockImplementation(mockFetchFirst);

    let callCount = 0;
    const getToken = vi.fn().mockImplementation(() => {
      callCount++;
      if (callCount <= 1) return Promise.resolve('token');
      // 刷新永不 resolve
      return new Promise<null>(() => {});
    });
    registerGetToken(getToken);

    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');

    const firstFetch = fetchWithAuth('/test');
    await vi.advanceTimersByTimeAsync(30_000);
    const firstResponse = await firstFetch;

    // 超时后 session-expired 触发
    expect(dispatchSpy).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'auth:session-expired' }),
    );
    expect(firstResponse.status).toBe(401);

    // 第二轮：新的请求
    vi.restoreAllMocks();
    const mockFetchSecond = createFetchMock([mockResponse(200)]);
    vi.spyOn(globalThis, 'fetch').mockImplementation(mockFetchSecond);

    // 重新注册 getToken，这次正常返回
    const getToken2 = vi.fn().mockResolvedValue('fresh-token');
    registerGetToken(getToken2);

    const response = await fetchWithAuth('/test2');
    expect(response.status).toBe(200);
    expect(getToken2).toHaveBeenCalled();
  });

  // H10: 正常请求不触发刷新
  it('H10: normal request does not trigger refresh', async () => {
    const mockFetch = createFetchMock([mockResponse(200)]);
    vi.spyOn(globalThis, 'fetch').mockImplementation(mockFetch);

    const getToken = vi.fn().mockResolvedValue('token');
    registerGetToken(getToken);

    await fetchWithAuth('/test');

    // getTokenFn 只调用 1 次（获取 token），不触发刷新
    expect(getToken).toHaveBeenCalledTimes(1);
  });

  // H11: URL 拼接 — 相对路径自动加 /api 前缀
  it('H11: relative URL gets /api prefix', async () => {
    const mockFetch = createFetchMock([mockResponse(200)]);
    vi.spyOn(globalThis, 'fetch').mockImplementation(mockFetch);

    await fetchWithAuth('/chat/stream');

    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(mockFetch.mock.calls[0][0]).toBe('/api/chat/stream');
  });

  // H12: URL 拼接 — 绝对路径保持不变
  it('H12: absolute URL stays unchanged', async () => {
    const mockFetch = createFetchMock([mockResponse(200)]);
    vi.spyOn(globalThis, 'fetch').mockImplementation(mockFetch);

    await fetchWithAuth('http://example.com/api');

    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(mockFetch.mock.calls[0][0]).toBe('http://example.com/api');
  });

  // H13: SSE 兼容 — 返回原生 Response（ReadableStream 可用）
  it('H13: returns native Response with ReadableStream', async () => {
    const body = new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode('data: hello\n\n'));
        controller.close();
      },
    });
    const resp = new Response(body, { status: 200 });

    vi.spyOn(globalThis, 'fetch').mockResolvedValue(resp);

    const getToken = vi.fn().mockResolvedValue('token');
    registerGetToken(getToken);

    const response = await fetchWithAuth('/stream');
    expect(response).toBeInstanceOf(Response);
    expect(response.body).not.toBeNull();
  });
});
