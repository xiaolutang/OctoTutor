/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  fetchWithAuth,
  registerAuthHandlers,
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

  // H1: registerAuthHandlers 注册后 fetchWithAuth 附加 Authorization header
  it('H1: registers auth handlers and attaches Authorization header', async () => {
    const mockFetch = createFetchMock([mockResponse(200)]);
    vi.spyOn(globalThis, 'fetch').mockImplementation(mockFetch);

    const getToken = vi.fn().mockResolvedValue('test-token');
    const onUnauthorized = vi.fn().mockResolvedValue(null);
    registerAuthHandlers({ getToken, onUnauthorized });

    await fetchWithAuth('/test');

    expect(mockFetch).toHaveBeenCalledTimes(1);
    const [url, init] = mockFetch.mock.calls[0];
    expect(url).toContain('/api/test');
    const headers = new Headers(init?.headers as HeadersInit);
    expect(headers.get('Authorization')).toBe('Bearer test-token');
  });

  // H2: 未注册 authHandlers → 不附加 header
  it('H2: without registerAuthHandlers, no Authorization header', async () => {
    const mockFetch = createFetchMock([mockResponse(200)]);
    vi.spyOn(globalThis, 'fetch').mockImplementation(mockFetch);

    await fetchWithAuth('/test');

    expect(mockFetch).toHaveBeenCalledTimes(1);
    const [, init] = mockFetch.mock.calls[0];
    const headers = new Headers(init?.headers as HeadersInit);
    expect(headers.get('Authorization')).toBeNull();
  });

  // H3: 401 + onUnauthorized 返回新 token → 自动重试 → 返回 200
  it('H3: 401 then onUnauthorized returns new token retries once', async () => {
    const responses = [mockResponse(401), mockResponse(200)];
    const mockFetch = createFetchMock(responses);
    vi.spyOn(globalThis, 'fetch').mockImplementation(mockFetch);

    const getToken = vi.fn().mockResolvedValue('expired-token');
    const onUnauthorized = vi.fn().mockResolvedValue('new-token');
    registerAuthHandlers({ getToken, onUnauthorized });

    const response = await fetchWithAuth('/test');
    expect(response.status).toBe(200);
    expect(mockFetch).toHaveBeenCalledTimes(2);
    expect(onUnauthorized).toHaveBeenCalledTimes(1);

    // 第二次调用带 X-Retry
    const retryInit = mockFetch.mock.calls[1][1];
    const retryHeaders = new Headers(retryInit?.headers as HeadersInit);
    expect(retryHeaders.get('X-Retry')).toBe('true');
    expect(retryHeaders.get('Authorization')).toBe('Bearer new-token');
  });

  // H4: 401 + onUnauthorized 返回 null → 不重试，返回 401
  it('H4: 401 + onUnauthorized returns null does not retry', async () => {
    const mockFetch = createFetchMock([mockResponse(401)]);
    vi.spyOn(globalThis, 'fetch').mockImplementation(mockFetch);

    const getToken = vi.fn().mockResolvedValue('token');
    const onUnauthorized = vi.fn().mockResolvedValue(null);
    registerAuthHandlers({ getToken, onUnauthorized });

    const response = await fetchWithAuth('/test');
    expect(response.status).toBe(401);
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  // H5: 401 + X-Retry header → 不再重试
  it('H5: 401 with X-Retry does not retry', async () => {
    const mockFetch = createFetchMock([mockResponse(401)]);
    vi.spyOn(globalThis, 'fetch').mockImplementation(mockFetch);

    const getToken = vi.fn().mockResolvedValue('token');
    const onUnauthorized = vi.fn().mockResolvedValue('new-token');
    registerAuthHandlers({ getToken, onUnauthorized });

    const headers = new Headers();
    headers.set('X-Retry', 'true');

    const response = await fetchWithAuth('/test', { headers });
    expect(response.status).toBe(401);
    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  // H6: 正常请求不触发 onUnauthorized
  it('H6: normal request does not trigger onUnauthorized', async () => {
    const mockFetch = createFetchMock([mockResponse(200)]);
    vi.spyOn(globalThis, 'fetch').mockImplementation(mockFetch);

    const getToken = vi.fn().mockResolvedValue('token');
    const onUnauthorized = vi.fn().mockResolvedValue(null);
    registerAuthHandlers({ getToken, onUnauthorized });

    await fetchWithAuth('/test');

    expect(getToken).toHaveBeenCalledTimes(1);
    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  // H7: URL 拼接 — 相对路径自动加 /api 前缀
  it('H7: relative URL gets /api prefix', async () => {
    const mockFetch = createFetchMock([mockResponse(200)]);
    vi.spyOn(globalThis, 'fetch').mockImplementation(mockFetch);

    await fetchWithAuth('/chat/stream');

    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(mockFetch.mock.calls[0][0]).toBe('/api/chat/stream');
  });

  // H8: URL 拼接 — 绝对路径保持不变
  it('H8: absolute URL stays unchanged', async () => {
    const mockFetch = createFetchMock([mockResponse(200)]);
    vi.spyOn(globalThis, 'fetch').mockImplementation(mockFetch);

    await fetchWithAuth('http://example.com/api');

    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(mockFetch.mock.calls[0][0]).toBe('http://example.com/api');
  });

  // H9: SSE 兼容 — 返回原生 Response（ReadableStream 可用）
  it('H9: returns native Response with ReadableStream', async () => {
    const body = new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode('data: hello\n\n'));
        controller.close();
      },
    });
    const resp = new Response(body, { status: 200 });

    vi.spyOn(globalThis, 'fetch').mockResolvedValue(resp);

    const getToken = vi.fn().mockResolvedValue('token');
    const onUnauthorized = vi.fn().mockResolvedValue(null);
    registerAuthHandlers({ getToken, onUnauthorized });

    const response = await fetchWithAuth('/stream');
    expect(response).toBeInstanceOf(Response);
    expect(response.body).not.toBeNull();
  });

  // H10: 无 authHandlers 时 401 不重试
  it('H10: 401 without authHandlers does not retry', async () => {
    const mockFetch = createFetchMock([mockResponse(401)]);
    vi.spyOn(globalThis, 'fetch').mockImplementation(mockFetch);

    // 不注册 authHandlers
    const response = await fetchWithAuth('/test');
    expect(response.status).toBe(401);
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });
});
