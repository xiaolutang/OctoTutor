import { fetchWithAuth } from '@/lib/api-client';
import type { ConversationItem } from './types';

interface ConversationListResponse {
  items: ConversationItem[];
  cursor: string | null;
  has_more: boolean;
}

export async function fetchConversationList(
  cursor?: string,
  limit = 20,
): Promise<{ items: ConversationItem[]; cursor: string | null; hasMore: boolean }> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (cursor) params.set('cursor', cursor);

  const response = await fetchWithAuth(`/conversations?${params}`);
  if (!response.ok) {
    throw new Error(`获取对话列表失败: ${response.status}`);
  }
  const data: ConversationListResponse = await response.json();
  return { items: data.items, cursor: data.cursor, hasMore: data.has_more };
}

export async function patchConversation(
  id: string,
  data: { title?: string; pinned?: boolean },
): Promise<ConversationItem> {
  const response = await fetchWithAuth(`/conversations/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || `更新对话失败: ${response.status}`);
  }
  return response.json();
}

export async function deleteConversation(id: string): Promise<void> {
  const response = await fetchWithAuth(`/conversations/${id}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    throw new Error(`删除对话失败: ${response.status}`);
  }
}
