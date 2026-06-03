import { useRef, useState, useCallback, useEffect } from 'react';
import { parseSSEEvents } from './parse-sse';
import type { SSECallbacks, SourceReference, ThinkingStep, Message, MessageStatus, ApiMessage } from './types';
import { fetchWithAuth } from '../lib/api-client';

interface UseChatStreamReturn {
  sendMessage: (question: string, callbacks: SSECallbacks, conversationId?: string) => void;
  stop: () => void;
  isStreaming: boolean;
}

/** resumeStream 的回调接口 */
export interface ResumeCallbacks {
  onStatus: (stage: string, message: string) => void;
  onSources: (sources: SourceReference[]) => void;
  onToken: (token: string) => void;
  onThinking: (step: ThinkingStep) => void;
  onDone: () => void;
  onError: (error: { code: string; message: string; action: string }) => void;
  /** 服务端返回 JSON（graph 已完成），直接提供完整消息列表 */
  onMessagesReady: (messages: Message[]) => void;
}

/** 将后端 ApiMessage 的 status 映射为前端 MessageStatus */
function mapApiStatus(status: ApiMessage['status']): MessageStatus {
  switch (status) {
    case 'completed':
      return 'done';
    case 'stopped':
      return 'stopped';
    case 'error':
      return 'error';
    default:
      return 'done';
  }
}

/**
 * 从 Response 的 ReadableStream 中读取并解析 SSE 事件
 * @internal 提取为共享函数，供 chatStreamFetch 和 resumeStream 复用
 */
async function readSSEStream(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  callbacks: {
    onEvent: (event: { type: string; data: unknown }) => void;
    onStreamError: (firstEventReceived: boolean) => void;
  },
): Promise<void> {
  const decoder = new TextDecoder();
  let remaining = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value, { stream: true });
      const { events, remaining: newRemaining } = parseSSEEvents(chunk, remaining);
      remaining = newRemaining;

      for (const event of events) {
        callbacks.onEvent(event);
      }
    }
  } catch {
    // 中断时的错误由调用方处理
    callbacks.onStreamError(remaining.length > 0);
  }
}

/**
 * 核心流式请求逻辑（纯副作用函数，方便测试）
 * @internal exported for testing
 */
export function chatStreamFetch(
  question: string,
  callbacks: SSECallbacks,
  abortController: AbortController,
  onSetStreaming: (v: boolean) => void,
  conversationId?: string,
) {
  let firstEventReceived = false;

  const body: Record<string, unknown> = { question, top_k: 10 };
  if (conversationId) {
    body.conversation_id = conversationId;
  }

  fetchWithAuth('/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: abortController.signal,
  })
    .then(async (response) => {
      if (!response.ok) {
        callbacks.onError({ code: '00000', message: '请求失败', action: 'retry' });
        onSetStreaming(false);
        return;
      }

      const reader = response.body?.getReader();
      if (!reader) {
        callbacks.onError({ code: '00000', message: '响应流不可用', action: 'retry' });
        onSetStreaming(false);
        return;
      }

      await readSSEStream(reader, {
        onEvent: (event) => {
          firstEventReceived = true;
          switch (event.type) {
            case 'init': {
              const d = event.data as { conversation_id: string };
              callbacks.onInit(d.conversation_id);
              break;
            }
            case 'status': {
              const d = event.data as { stage: string; message: string };
              callbacks.onStatus(d.stage, d.message);
              break;
            }
            case 'sources':
              callbacks.onSources(event.data as SourceReference[]);
              break;
            case 'thinking':
              callbacks.onThinking(event.data as ThinkingStep);
              break;
            case 'token':
              callbacks.onToken(event.data as string);
              break;
            case 'done':
              callbacks.onDone();
              break;
            case 'title': {
              const d = event.data as { conversation_id: string; title: string };
              callbacks.onTitle(d.conversation_id, d.title);
              break;
            }
            case 'error':
              callbacks.onError(event.data as { code: string; message: string; action: string });
              break;
          }
        },
        onStreamError: () => {
          if (firstEventReceived) {
            callbacks.onError({ code: '00001', message: '连接中断', action: 'retry' });
          } else {
            callbacks.onError({ code: '00000', message: '连接失败', action: 'retry' });
          }
        },
      });
    })
    .catch((err) => {
      if (err instanceof DOMException && err.name === 'AbortError') {
        return;
      }
      if (firstEventReceived) {
        callbacks.onError({ code: '00001', message: '网络异常', action: 'retry' });
      } else {
        callbacks.onError({ code: '00000', message: '请求失败', action: 'retry' });
      }
    })
    .finally(() => {
      onSetStreaming(false);
    });
}

/**
 * SSE 重连：GET /chat/stream/resume?conversation_id=xxx
 *
 * 服务端可能返回：
 * - SSE 流（text/event-stream）→ 流式恢复 token
 * - JSON（application/json）→ graph 已完成，直接返回完整消息列表
 * - 404/204 → 找不到可恢复的流，返回错误
 */
export function resumeStream(
  conversationId: string,
  callbacks: ResumeCallbacks,
): Promise<void> {
  const url = `/chat/stream/resume?conversation_id=${encodeURIComponent(conversationId)}`;

  return fetchWithAuth(url, { method: 'GET' })
    .then(async (response) => {
      // 404 / 204 → 无法恢复
      if (response.status === 404 || response.status === 204) {
        callbacks.onError({
          code: 'INTERRUPTED',
          message: 'AI 回复因页面刷新而中断，请重新生成',
          action: 'retry',
        });
        return;
      }

      if (!response.ok) {
        callbacks.onError({ code: '00000', message: '恢复请求失败', action: 'retry' });
        return;
      }

      const contentType = response.headers.get('content-type') || '';

      // JSON 响应 → graph 已完成，直接提供完整消息
      if (contentType.includes('application/json')) {
        const data = await response.json();
        const messages: Message[] = (data.messages as ApiMessage[]).map((apiMsg) => ({
          id: apiMsg.id,
          role: apiMsg.role === 'human' ? ('user' as const) : ('ai' as const),
          content: apiMsg.content,
          status: mapApiStatus(apiMsg.status),
          sources: apiMsg.sources,
          thinkingSteps: apiMsg.thinking_steps,
          timestamp: apiMsg.created_at ? new Date(apiMsg.created_at).getTime() : Date.now(),
        }));
        callbacks.onMessagesReady(messages);
        return;
      }

      // SSE 流式响应 → 复用 SSE 解析逻辑
      const reader = response.body?.getReader();
      if (!reader) {
        callbacks.onError({ code: '00000', message: '响应流不可用', action: 'retry' });
        return;
      }

      let firstEventReceived = false;

      await readSSEStream(reader, {
        onEvent: (event) => {
          firstEventReceived = true;
          switch (event.type) {
            case 'status': {
              const d = event.data as { stage: string; message: string };
              callbacks.onStatus(d.stage, d.message);
              break;
            }
            case 'sources':
              callbacks.onSources(event.data as SourceReference[]);
              break;
            case 'thinking':
              callbacks.onThinking(event.data as ThinkingStep);
              break;
            case 'token':
              callbacks.onToken(event.data as string);
              break;
            case 'done':
              callbacks.onDone();
              break;
            case 'error':
              callbacks.onError(event.data as { code: string; message: string; action: string });
              break;
          }
        },
        onStreamError: () => {
          if (firstEventReceived) {
            callbacks.onError({ code: '00001', message: '恢复连接中断', action: 'retry' });
          } else {
            callbacks.onError({ code: '00000', message: '恢复连接失败', action: 'retry' });
          }
        },
      });
    })
    .catch(() => {
      callbacks.onError({ code: '00000', message: '恢复请求异常', action: 'retry' });
    });
}

export function useChatStream(): UseChatStreamReturn {
  const [isStreaming, setIsStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const conversationIdRef = useRef<string | undefined>(undefined);

  // 组件卸载时终止正在进行的 SSE 连接
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  const sendMessage = useCallback(
    (question: string, callbacks: SSECallbacks, conversationId?: string) => {
      const abortController = new AbortController();
      abortRef.current = abortController;
      conversationIdRef.current = conversationId;
      setIsStreaming(true);

      chatStreamFetch(question, callbacks, abortController, setIsStreaming, conversationId);
    },
    [],
  );

  const stop = useCallback(async () => {
    if (conversationIdRef.current) {
      try {
        await fetchWithAuth('/chat/stop', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ conversation_id: conversationIdRef.current }),
        });
      } catch {
        // POST /chat/stop 失败不阻断 abort
      }
    }
    abortRef.current?.abort();
  }, []);

  return { sendMessage, stop, isStreaming };
}
