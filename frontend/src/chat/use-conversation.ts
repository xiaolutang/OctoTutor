import { useCallback, useRef } from 'react';
import { fetchWithAuth } from '@/lib/api-client';
import type { Message, ConversationResponse } from './types';
import { convertApiMessages } from './types';

interface UseConversationReturn {
  loadConversation: (conversationId?: string | null) => Promise<{ messages: Message[]; stale?: boolean }>;
}

/**
 * useConversation — 对话加载 hook
 *
 * - 有 conversationId 时：GET /conversations/current?conversation_id=xxx 精确加载
 * - 无 conversationId 时：GET /conversations/current 后端返回最新对话
 * - 204 返回空态
 * - API 失败时返回空消息
 * - conversationId 由调用方传入（ConversationContext），不再使用 localStorage
 */
export function useConversation(): UseConversationReturn {
  const requestIdRef = useRef(0);

  const loadConversation = useCallback(
    async (conversationId?: string | null): Promise<{ messages: Message[]; stale?: boolean }> => {
      const myRequestId = ++requestIdRef.current;

      try {
        const url = conversationId
          ? `/conversations/current?conversation_id=${encodeURIComponent(conversationId)}`
          : '/conversations/current';
        const response = await fetchWithAuth(url);
        if (response.status === 204 || !response.ok) {
          return { messages: [], stale: myRequestId !== requestIdRef.current };
        }
        const data: ConversationResponse = await response.json();
        return { messages: convertApiMessages(data.messages), stale: myRequestId !== requestIdRef.current };
      } catch {
        return { messages: [], stale: myRequestId !== requestIdRef.current };
      }
    },
    [],
  );

  return { loadConversation };
}
