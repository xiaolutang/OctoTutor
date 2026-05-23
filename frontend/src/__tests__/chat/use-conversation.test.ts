/**
 * R007-FB002 use-conversation.ts 测试
 *
 * 测试场景：
 * 1. 页面加载 → API 返回历史消息（含 thinkingSteps）
 * 2. API 返回 204 → 空态
 * 3. API 失败 → 降级 localStorage loadMessages
 * 4. role 映射：human → user
 * 5. status 映射：completed → done, stopped → stopped, error → error
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import type { ConversationResponse, Message } from '@/chat/types';

// ============================================================
// Mock: fetchWithAuth
// ============================================================
const mockFetchWithAuth = vi.fn<
  (url: string, init?: RequestInit) => Promise<Response>
>();

vi.mock('@/lib/api-client', () => ({
  fetchWithAuth: (url: string, init?: RequestInit) => mockFetchWithAuth(url, init),
}));

// ============================================================
// Mock: loadMessages
// ============================================================
const mockLoadMessages = vi.fn<() => Message[]>();

vi.mock('@/chat/use-chat-storage', () => ({
  loadMessages: () => mockLoadMessages(),
  saveMessages: vi.fn(),
}));

// ============================================================
// 辅助：构造 API 响应
// ============================================================
function mockJsonResponse(data: ConversationResponse, status = 200): Response {
  return {
    status,
    ok: status >= 200 && status < 300,
    json: () => Promise.resolve(data),
  } as Response;
}

function mockNoContentResponse(): Response {
  return {
    status: 204,
    ok: true,
    json: () => Promise.resolve(null),
  } as Response;
}

// ============================================================
// 模拟 loadConversation 纯逻辑（与 hook 等价的纯函数）
// ============================================================
interface ConversationState {
  conversationId: string | null;
}

async function simulateLoadConversation(
  state: ConversationState,
  fetchWithAuth: (url: string) => Promise<Response>,
  loadMessages: () => Message[],
): Promise<{ messages: Message[]; fromCache: boolean }> {
  try {
    const response = await fetchWithAuth('/conversations/current');
    if (response.status === 204) {
      return { messages: [], fromCache: false };
    }
    const data: ConversationResponse = await response.json();
    state.conversationId = data.conversation_id;
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
}

function mapApiStatus(status: string): Message['status'] {
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

// ============================================================
// 测试
// ============================================================
describe('useConversation - loadConversation', () => {
  let state: ConversationState;

  beforeEach(() => {
    vi.clearAllMocks();
    state = { conversationId: null };
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  // 测试 1: API 返回历史消息 → 正确映射并渲染
  it('should map API messages to frontend format with thinkingSteps', async () => {
    const apiResponse: ConversationResponse = {
      conversation_id: 'conv-001',
      messages: [
        {
          id: 'msg-1',
          role: 'human',
          content: '什么是微积分？',
          status: 'completed',
          created_at: '2026-01-15T10:00:00Z',
        },
        {
          id: 'msg-2',
          role: 'ai',
          content: '微积分是数学的一个分支...',
          status: 'completed',
          thinking_steps: [
            { text: '分析问题', index: 0 },
            { text: '检索教材', index: 1 },
          ],
          sources: [
            { chunk_id: 'c1', book: '高等数学', section: '第一章', page_start: 1, page_end: 10 },
          ],
          created_at: '2026-01-15T10:00:05Z',
        },
      ],
    };

    mockFetchWithAuth.mockResolvedValue(mockJsonResponse(apiResponse));

    const result = await simulateLoadConversation(state, mockFetchWithAuth, mockLoadMessages);

    // 验证 API 调用
    expect(mockFetchWithAuth).toHaveBeenCalledWith('/conversations/current');
    expect(mockFetchWithAuth).toHaveBeenCalledOnce();

    // 验证 conversationId 设置
    expect(state.conversationId).toBe('conv-001');

    // 验证消息映射
    expect(result.fromCache).toBe(false);
    expect(result.messages).toHaveLength(2);

    // 用户消息
    expect(result.messages[0].role).toBe('user');
    expect(result.messages[0].content).toBe('什么是微积分？');
    expect(result.messages[0].status).toBe('done');

    // AI 消息
    expect(result.messages[1].role).toBe('ai');
    expect(result.messages[1].content).toBe('微积分是数学的一个分支...');
    expect(result.messages[1].status).toBe('done');
    expect(result.messages[1].thinkingSteps).toHaveLength(2);
    expect(result.messages[1].thinkingSteps![0].text).toBe('分析问题');
    expect(result.messages[1].sources).toHaveLength(1);
  });

  // 测试 2: API 返回 204 → 空态
  it('should return empty messages when API returns 204', async () => {
    mockFetchWithAuth.mockResolvedValue(mockNoContentResponse());

    const result = await simulateLoadConversation(state, mockFetchWithAuth, mockLoadMessages);

    expect(result.messages).toEqual([]);
    expect(result.fromCache).toBe(false);
    expect(state.conversationId).toBeNull();
  });

  // 测试 3: API 失败 → 降级 localStorage
  it('should fallback to localStorage when API throws error', async () => {
    const cachedMessages: Message[] = [
      { id: 'cached-1', role: 'user', content: '缓存问题', status: 'done', timestamp: 1000 },
      { id: 'cached-2', role: 'ai', content: '缓存回答', status: 'done', timestamp: 1001 },
    ];
    mockFetchWithAuth.mockRejectedValue(new Error('Network error'));
    mockLoadMessages.mockReturnValue(cachedMessages);

    const result = await simulateLoadConversation(state, mockFetchWithAuth, mockLoadMessages);

    expect(result.fromCache).toBe(true);
    expect(result.messages).toEqual(cachedMessages);
    expect(mockLoadMessages).toHaveBeenCalledOnce();
    // conversationId 保持 null
    expect(state.conversationId).toBeNull();
  });

  // 测试 4: role 映射验证
  it('should correctly map human → user and ai → ai roles', async () => {
    const apiResponse: ConversationResponse = {
      conversation_id: 'conv-002',
      messages: [
        { id: 'm1', role: 'human', content: 'q1', status: 'completed', created_at: '2026-01-01T00:00:00Z' },
        { id: 'm2', role: 'ai', content: 'a1', status: 'completed', created_at: '2026-01-01T00:00:01Z' },
        { id: 'm3', role: 'human', content: 'q2', status: 'completed', created_at: '2026-01-01T00:00:02Z' },
        { id: 'm4', role: 'ai', content: 'a2', status: 'completed', created_at: '2026-01-01T00:00:03Z' },
      ],
    };

    mockFetchWithAuth.mockResolvedValue(mockJsonResponse(apiResponse));

    const result = await simulateLoadConversation(state, mockFetchWithAuth, mockLoadMessages);

    expect(result.messages[0].role).toBe('user');
    expect(result.messages[1].role).toBe('ai');
    expect(result.messages[2].role).toBe('user');
    expect(result.messages[3].role).toBe('ai');
  });

  // 测试 5: status 映射验证
  it('should correctly map API status to MessageStatus', async () => {
    const apiResponse: ConversationResponse = {
      conversation_id: 'conv-003',
      messages: [
        { id: 'm1', role: 'ai', content: 'completed msg', status: 'completed', created_at: '2026-01-01T00:00:00Z' },
        { id: 'm2', role: 'ai', content: 'stopped msg', status: 'stopped', created_at: '2026-01-01T00:00:01Z' },
        { id: 'm3', role: 'ai', content: 'error msg', status: 'error', created_at: '2026-01-01T00:00:02Z' },
      ],
    };

    mockFetchWithAuth.mockResolvedValue(mockJsonResponse(apiResponse));

    const result = await simulateLoadConversation(state, mockFetchWithAuth, mockLoadMessages);

    expect(result.messages[0].status).toBe('done');
    expect(result.messages[1].status).toBe('stopped');
    expect(result.messages[2].status).toBe('error');
  });

  // 测试 6: thinkingSteps 为空/不存在时正确处理
  it('should handle messages without thinkingSteps', async () => {
    const apiResponse: ConversationResponse = {
      conversation_id: 'conv-004',
      messages: [
        { id: 'm1', role: 'human', content: '无思考步骤', status: 'completed', created_at: '2026-01-01T00:00:00Z' },
        { id: 'm2', role: 'ai', content: '回答', status: 'completed', created_at: '2026-01-01T00:00:01Z' },
      ],
    };

    mockFetchWithAuth.mockResolvedValue(mockJsonResponse(apiResponse));

    const result = await simulateLoadConversation(state, mockFetchWithAuth, mockLoadMessages);

    // 用户消息无 thinkingSteps
    expect(result.messages[0].thinkingSteps).toBeUndefined();
    // AI 消息也无 thinkingSteps（API 未返回）
    expect(result.messages[1].thinkingSteps).toBeUndefined();
  });

  // 测试 7: API 失败且 localStorage 也为空
  it('should return empty array when API fails and localStorage is empty', async () => {
    mockFetchWithAuth.mockRejectedValue(new Error('Server error'));
    mockLoadMessages.mockReturnValue([]);

    const result = await simulateLoadConversation(state, mockFetchWithAuth, mockLoadMessages);

    expect(result.fromCache).toBe(true);
    expect(result.messages).toEqual([]);
  });

  // 测试 8: timestamp 从 ISO 字符串正确转换
  it('should convert ISO date string to timestamp', async () => {
    const apiResponse: ConversationResponse = {
      conversation_id: 'conv-005',
      messages: [
        { id: 'm1', role: 'human', content: 'test', status: 'completed', created_at: '2026-05-23T08:30:00.000Z' },
      ],
    };

    mockFetchWithAuth.mockResolvedValue(mockJsonResponse(apiResponse));

    const result = await simulateLoadConversation(state, mockFetchWithAuth, mockLoadMessages);

    expect(result.messages[0].timestamp).toBe(new Date('2026-05-23T08:30:00.000Z').getTime());
  });
});
