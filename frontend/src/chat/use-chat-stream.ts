import { useRef, useState, useCallback } from 'react';
import { parseSSEEvents } from './parse-sse';
import type { SSECallbacks, SourceReference } from './types';
import { fetchWithAuth } from '../lib/api-client';

interface UseChatStreamReturn {
  sendMessage: (question: string, callbacks: SSECallbacks) => void;
  stop: () => void;
  isStreaming: boolean;
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
) {
  let firstEventReceived = false;
  let remaining = '';

  fetchWithAuth('/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, top_k: 10 }),
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

      const decoder = new TextDecoder();

      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          const chunk = decoder.decode(value, { stream: true });
          const { events, remaining: newRemaining } = parseSSEEvents(chunk, remaining);
          remaining = newRemaining;

          for (const event of events) {
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
          }
        }
      } catch (err) {
        if (firstEventReceived) {
          callbacks.onError({ code: '00001', message: '连接中断', action: 'retry' });
        } else {
          callbacks.onError({ code: '00000', message: '连接失败', action: 'retry' });
        }
      }
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

export function useChatStream(): UseChatStreamReturn {
  const [isStreaming, setIsStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const sendMessage = useCallback(
    (question: string, callbacks: SSECallbacks) => {
      const abortController = new AbortController();
      abortRef.current = abortController;
      setIsStreaming(true);

      chatStreamFetch(question, callbacks, abortController, setIsStreaming);
    },
    [],
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  return { sendMessage, stop, isStreaming };
}
