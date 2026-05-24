import { useCallback, useRef } from 'react';
import { fetchWithAuth } from '@/lib/api-client';
import type { Message, MessageStatus, ConversationResponse, ApiMessage } from './types';

const CONVERSATION_ID_KEY = 'octotutor_conversation_id';

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

/** 从 localStorage 读取 conversationId（过滤无效值） */
export function loadConversationId(): string | null {
  try {
    const v = localStorage.getItem(CONVERSATION_ID_KEY);
    if (!v || v === 'undefined' || v === 'null') return null;
    return v;
  } catch {
    return null;
  }
}

/** 将 conversationId 持久化到 localStorage */
export function saveConversationId(id: string): void {
  try {
    localStorage.setItem(CONVERSATION_ID_KEY, id);
  } catch {
    // ignore
  }
}

interface UseConversationReturn {
  loadConversation: () => Promise<{ messages: Message[]; fromCache: boolean }>;
}

/**
 * useConversation — 对话加载 hook
 *
 * - 有 conversationId 时：GET /conversations/current?conversation_id=xxx 精确加载
 * - 无 conversationId 时：GET /conversations/current 后端返回最新对话
 * - 204 返回空态
 * - API 失败时返回空消息（由 controller 层保证 isInitialized 后才调用）
 * - conversationId 持久化到 localStorage，刷新后恢复
 */
export function useConversation(): UseConversationReturn {
  const loadingRef = useRef(false);

  const loadConversation = useCallback(async (): Promise<{ messages: Message[]; fromCache: boolean }> => {
    // 防止并发调用
    if (loadingRef.current) {
      return { messages: [], fromCache: false };
    }
    loadingRef.current = true;

    try {
      // 读取一次，闭包固定，不再中途重读
      const storedId = loadConversationId();
      const url = storedId
        ? `/conversations/current?conversation_id=${encodeURIComponent(storedId)}`
        : '/conversations/current';
      const response = await fetchWithAuth(url);
      if (response.status === 204 || !response.ok) {
        return { messages: [], fromCache: false };
      }
      const data: ConversationResponse = await response.json();
      // 只有当本地没有 conversationId 时才用服务端的值覆盖
      if (!storedId && data.conversation_id) {
        saveConversationId(data.conversation_id);
      }
      const mapped: Message[] = data.messages.map((apiMsg) => ({
        id: apiMsg.id,
        role: apiMsg.role === 'human' ? 'user' as const : 'ai' as const,
        content: apiMsg.content,
        status: mapApiStatus(apiMsg.status),
        sources: apiMsg.sources,
        thinkingSteps: apiMsg.thinking_steps,
        timestamp: apiMsg.created_at ? new Date(apiMsg.created_at).getTime() : Date.now(),
      }));
      return { messages: mapped, fromCache: false };
    } catch {
      return { messages: [], fromCache: false };
    } finally {
      loadingRef.current = false;
    }
  }, []);

  return { loadConversation };
}
