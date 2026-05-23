import { useState, useCallback } from 'react';
import { fetchWithAuth } from '@/lib/api-client';
import { loadMessages } from './use-chat-storage';
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
  conversationId: string | null;
  loadConversation: () => Promise<{ messages: Message[]; fromCache: boolean }>;
}

/**
 * useConversation — 对话加载 hook
 *
 * - 调用 GET /api/conversations/current 获取历史消息
 * - 204 返回空态
 * - API 失败时降级到 localStorage
 */
export function useConversation(): UseConversationReturn {
  const [conversationId, setConversationId] = useState<string | null>(null);

  const loadConversation = useCallback(async (): Promise<{ messages: Message[]; fromCache: boolean }> => {
    try {
      const response = await fetchWithAuth('/conversations/current');
      if (response.status === 204) {
        return { messages: [], fromCache: false };
      }
      const data: ConversationResponse = await response.json();
      setConversationId(data.conversation_id);
      const mapped: Message[] = data.messages.map((apiMsg) => ({
        id: apiMsg.id,
        role: apiMsg.role === 'human' ? 'user' as const : 'ai' as const,
        content: apiMsg.content,
        status: mapApiStatus(apiMsg.status),
        sources: apiMsg.sources,
        thinkingSteps: apiMsg.thinking_steps,
        timestamp: new Date(apiMsg.created_at).getTime(),
      }));
      return { messages: mapped, fromCache: false };
    } catch {
      const cached = loadMessages();
      return { messages: cached ?? [], fromCache: true };
    }
  }, []);

  return { conversationId, loadConversation };
}
