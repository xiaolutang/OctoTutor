import { useCallback, useRef } from 'react';
import { fetchWithAuth } from '@/lib/api-client';
import type { Message, MessageStatus, ConversationResponse, ApiMessage } from './types';

/**
 * 将后端 API 消息状态映射为前端 MessageStatus
 */
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

interface UseConversationReturn {
  loadConversation: (conversationId?: string | null) => Promise<{ messages: Message[] }>;
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
  const loadingRef = useRef(false);

  const loadConversation = useCallback(
    async (conversationId?: string | null): Promise<{ messages: Message[] }> => {
      if (loadingRef.current) {
        return { messages: [] };
      }
      loadingRef.current = true;

      try {
        const url = conversationId
          ? `/conversations/current?conversation_id=${encodeURIComponent(conversationId)}`
          : '/conversations/current';
        const response = await fetchWithAuth(url);
        if (response.status === 204 || !response.ok) {
          return { messages: [] };
        }
        const data: ConversationResponse = await response.json();
        const mapped: Message[] = data.messages.map((apiMsg) => ({
          id: apiMsg.id,
          role: apiMsg.role === 'human' ? ('user' as const) : ('ai' as const),
          content: apiMsg.content,
          status: mapApiStatus(apiMsg.status),
          sources: apiMsg.sources,
          thinkingSteps: apiMsg.thinking_steps,
          timestamp: apiMsg.created_at ? new Date(apiMsg.created_at).getTime() : Date.now(),
        }));
        return { messages: mapped };
      } catch {
        return { messages: [] };
      } finally {
        loadingRef.current = false;
      }
    },
    [],
  );

  return { loadConversation };
}
