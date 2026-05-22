import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { chatStreamFetch } from '../../chat/use-chat-stream';
import type { SSECallbacks } from '../../chat/types';

// Mock fetch helper: builds SSE ReadableStream from event array
function mockFetchSSE(events: Array<{ type: string; data: unknown }>) {
  const sseText = events
    .map((e) => `event: ${e.type}\ndata: ${JSON.stringify(e.data)}\n\n`)
    .join('');
  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    start(controller) {
      controller.enqueue(encoder.encode(sseText));
      controller.close();
    },
  });
  return {
    ok: true,
    status: 200,
    body: stream,
  };
}

function createCallbacks(): SSECallbacks & { callbackOrder: string[] } {
  const callbackOrder: string[] = [];
  return {
    callbackOrder,
    onStatus: vi.fn((stage: string, message: string) => {
      callbackOrder.push(`onStatus:${stage}`);
    }),
    onSources: vi.fn(() => {
      callbackOrder.push('onSources');
    }),
    onToken: vi.fn(() => {
      callbackOrder.push('onToken');
    }),
    onDone: vi.fn(() => {
      callbackOrder.push('onDone');
    }),
    onError: vi.fn(() => {
      callbackOrder.push('onError');
    }),
  };
}

describe('chatStreamFetch', () => {
  let fetchSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('should trigger callbacks in order: onStatus -> onSources -> onToken -> onDone', async () => {
    const events = [
      { type: 'status', data: { stage: 'retrieving', message: '正在检索...' } },
      { type: 'sources', data: [{ chunk_id: 'c1', book: 'b1', section: 's1', page_start: 1, page_end: 5 }] },
      { type: 'token', data: 'Hello' },
      { type: 'done', data: null },
    ];

    fetchSpy.mockResolvedValue(mockFetchSSE(events));

    const cbs = createCallbacks();
    const abortController = new AbortController();
    const setStreaming = vi.fn();

    chatStreamFetch('test question', cbs, abortController, setStreaming);

    await vi.waitFor(() => {
      expect(cbs.onDone).toHaveBeenCalled();
    });

    // Verify callbacks called with correct arguments
    expect(cbs.onStatus).toHaveBeenCalledWith('retrieving', '正在检索...');
    expect(cbs.onSources).toHaveBeenCalledWith([{ chunk_id: 'c1', book: 'b1', section: 's1', page_start: 1, page_end: 5 }]);
    expect(cbs.onToken).toHaveBeenCalledWith('Hello');
    expect(cbs.onDone).toHaveBeenCalledTimes(1);
    expect(cbs.onError).not.toHaveBeenCalled();

    // Verify order: onStatus -> onSources -> onToken -> onDone
    expect(cbs.callbackOrder).toEqual([
      'onStatus:retrieving',
      'onSources',
      'onToken',
      'onDone',
    ]);

    // finally: setStreaming(false)
    expect(setStreaming).toHaveBeenCalledWith(false);
  });

  it('should call onError with code 00000 when HTTP response is not ok', async () => {
    fetchSpy.mockResolvedValue({
      ok: false,
      status: 500,
    });

    const cbs = createCallbacks();
    const abortController = new AbortController();
    const setStreaming = vi.fn();

    chatStreamFetch('test', cbs, abortController, setStreaming);

    await vi.waitFor(() => {
      expect(cbs.onError).toHaveBeenCalled();
    });

    expect(cbs.onError).toHaveBeenCalledWith(
      expect.objectContaining({ code: '00000', message: '请求失败' }),
    );
    expect(cbs.onDone).not.toHaveBeenCalled();
    // Non-ok path sets streaming false inline
    expect(setStreaming).toHaveBeenCalledWith(false);
  });

  it('should call onError with code 00001 when stream breaks after first event', async () => {
    const encoder = new TextEncoder();
    const firstChunk = encoder.encode(
      'event: status\ndata: {"stage":"retrieving","message":"..."}\n\n',
    );

    let pullCount = 0;
    const stream = new ReadableStream({
      pull(controller) {
        pullCount++;
        if (pullCount === 1) {
          controller.enqueue(firstChunk);
        } else {
          // Second read: error the stream
          controller.error(new Error('Stream broken'));
        }
      },
    });

    fetchSpy.mockResolvedValue({
      ok: true,
      status: 200,
      body: stream,
    });

    const cbs = createCallbacks();
    const abortController = new AbortController();
    const setStreaming = vi.fn();

    chatStreamFetch('test', cbs, abortController, setStreaming);

    await vi.waitFor(() => {
      expect(cbs.onError).toHaveBeenCalled();
    });

    // First event was received (onStatus), so error code should be 00001
    expect(cbs.onStatus).toHaveBeenCalled();
    expect(cbs.onError).toHaveBeenCalledWith(
      expect.objectContaining({ code: '00001', message: '连接中断' }),
    );
  });

  it('should call onError with code 00000 when fetch fails before first event', async () => {
    fetchSpy.mockRejectedValue(new TypeError('Network error'));

    const cbs = createCallbacks();
    const abortController = new AbortController();
    const setStreaming = vi.fn();

    chatStreamFetch('test', cbs, abortController, setStreaming);

    await vi.waitFor(() => {
      expect(cbs.onError).toHaveBeenCalled();
    });

    // No first event received, so code is 00000
    expect(cbs.onError).toHaveBeenCalledWith(
      expect.objectContaining({ code: '00000', message: '请求失败' }),
    );
    expect(cbs.onDone).not.toHaveBeenCalled();
    // finally: setStreaming(false)
    expect(setStreaming).toHaveBeenCalledWith(false);
  });

  it('should not trigger onError when AbortController is aborted', async () => {
    // Simulate fetch that rejects with AbortError
    fetchSpy.mockImplementation((_url: string, opts: { signal?: AbortSignal }) => {
      return new Promise((_resolve, reject) => {
        if (opts.signal?.aborted) {
          reject(new DOMException('The operation was aborted.', 'AbortError'));
        } else {
          // Simulate a delay so we can abort
          setTimeout(() => {
            reject(new DOMException('The operation was aborted.', 'AbortError'));
          }, 10);
        }
      });
    });

    const cbs = createCallbacks();
    const abortController = new AbortController();
    const setStreaming = vi.fn();

    chatStreamFetch('test', cbs, abortController, setStreaming);

    // Abort immediately
    abortController.abort();

    // Wait for async to settle
    await new Promise((r) => setTimeout(r, 100));

    // onError should NOT be called for AbortError
    expect(cbs.onError).not.toHaveBeenCalled();
    expect(cbs.onDone).not.toHaveBeenCalled();
    // finally: setStreaming(false) still runs
    expect(setStreaming).toHaveBeenCalledWith(false);
  });

  // F-ERR-01: 后端 error event → onError 被调用
  it('should call onError when backend sends error event', async () => {
    const events = [
      { type: 'error', data: { code: '02202', message: '生成中断', action: 'retry' } },
    ];
    fetchSpy.mockResolvedValue(mockFetchSSE(events));
    const cbs = createCallbacks();
    const abortController = new AbortController();
    const setStreaming = vi.fn();
    chatStreamFetch('test', cbs, abortController, setStreaming);
    await vi.waitFor(() => expect(cbs.onError).toHaveBeenCalled());
    expect(cbs.onError).toHaveBeenCalledWith({ code: '02202', message: '生成中断', action: 'retry' });
    expect(cbs.onDone).not.toHaveBeenCalled();
  });

  // F-ERR-02: error event 前有 token → onToken + onError
  it('should call onToken then onError when error follows tokens', async () => {
    const events = [
      { type: 'status', data: { stage: 'retrieving', message: '...' } },
      { type: 'token', data: '部分' },
      { type: 'error', data: { code: '02202', message: '生成中断', action: 'retry' } },
    ];
    fetchSpy.mockResolvedValue(mockFetchSSE(events));
    const cbs = createCallbacks();
    const abortController = new AbortController();
    const setStreaming = vi.fn();
    chatStreamFetch('test', cbs, abortController, setStreaming);
    await vi.waitFor(() => expect(cbs.onError).toHaveBeenCalled());
    expect(cbs.onToken).toHaveBeenCalledWith('部分');
    expect(cbs.onError).toHaveBeenCalledWith({ code: '02202', message: '生成中断', action: 'retry' });
    expect(cbs.onDone).not.toHaveBeenCalled();
    // verify order: onStatus -> onToken -> onError
    expect(cbs.callbackOrder).toEqual([
      'onStatus:retrieving',
      'onToken',
      'onError',
    ]);
  });

  // F-ERR-03: SSE 缺 event 行 → 静默跳过
  it('should silently skip SSE events without event line', async () => {
    const encoder = new TextEncoder();
    // 只发送 data 行，没有 event 行
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode('data: "hello"\n\n'));
        controller.close();
      },
    });
    fetchSpy.mockResolvedValue({ ok: true, status: 200, body: stream });
    const cbs = createCallbacks();
    const abortController = new AbortController();
    const setStreaming = vi.fn();
    chatStreamFetch('test', cbs, abortController, setStreaming);
    // 等待 stream 完成
    await new Promise((r) => setTimeout(r, 100));
    // 没有 event 行 → parseSSEEvents 不产出事件 → 无回调被调用
    expect(cbs.onToken).not.toHaveBeenCalled();
    expect(cbs.onStatus).not.toHaveBeenCalled();
    expect(cbs.onError).not.toHaveBeenCalled();
    expect(cbs.onDone).not.toHaveBeenCalled();
    // 不崩溃，setStreaming 最终被调用
    expect(setStreaming).toHaveBeenCalledWith(false);
  });

  // F-ERR-04: 多事件合并 chunk → 两个回调都触发
  it('should parse multiple SSE events in single chunk', async () => {
    const sseText = 'event: token\ndata: "hello"\n\nevent: token\ndata: "world"\n\n';
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(sseText));
        controller.close();
      },
    });
    fetchSpy.mockResolvedValue({ ok: true, status: 200, body: stream });
    const cbs = createCallbacks();
    const abortController = new AbortController();
    const setStreaming = vi.fn();
    chatStreamFetch('test', cbs, abortController, setStreaming);
    await new Promise((r) => setTimeout(r, 100));
    expect(cbs.onToken).toHaveBeenCalledTimes(2);
    expect(cbs.onToken).toHaveBeenNthCalledWith(1, 'hello');
    expect(cbs.onToken).toHaveBeenNthCalledWith(2, 'world');
  });

  // F-ERR-05: 不完整事件跨 chunk → 合并解析
  it('should handle incomplete SSE event across chunks', async () => {
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode('event: token\ndata: "hel'));
        controller.enqueue(encoder.encode('lo"\n\n'));
        controller.close();
      },
    });
    fetchSpy.mockResolvedValue({ ok: true, status: 200, body: stream });
    const cbs = createCallbacks();
    const abortController = new AbortController();
    const setStreaming = vi.fn();
    chatStreamFetch('test', cbs, abortController, setStreaming);
    await new Promise((r) => setTimeout(r, 100));
    expect(cbs.onToken).toHaveBeenCalledTimes(1);
    expect(cbs.onToken).toHaveBeenCalledWith('hello');
  });
});
