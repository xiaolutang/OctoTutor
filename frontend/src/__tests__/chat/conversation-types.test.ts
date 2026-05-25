import { describe, it, expect } from 'vitest';
import type {
  ConversationItem,
  ConversationListState,
  SSECallbacks,
} from '../../chat/types';

/**
 * R009-FF002: 类型定义测试
 * 验证 ConversationItem / ConversationListState / SSECallbacks 接口字段完整性
 */
describe('ConversationItem type', () => {
  it('should accept a valid ConversationItem with all required fields', () => {
    const item: ConversationItem = {
      id: 'conv-001',
      title: '测试对话',
      pinned: false,
      pinned_at: null,
      message_count: 5,
      created_at: '2025-01-01T00:00:00Z',
      updated_at: '2025-01-01T01:00:00Z',
    };

    // 验证所有字段都存在且类型正确
    expect(item.id).toBe('conv-001');
    expect(item.title).toBe('测试对话');
    expect(item.pinned).toBe(false);
    expect(item.pinned_at).toBeNull();
    expect(item.message_count).toBe(5);
    expect(item.created_at).toBe('2025-01-01T00:00:00Z');
    expect(item.updated_at).toBe('2025-01-01T01:00:00Z');
  });

  it('should accept pinned_at as a string when pinned is true', () => {
    const item: ConversationItem = {
      id: 'conv-002',
      title: '置顶对话',
      pinned: true,
      pinned_at: '2025-01-02T00:00:00Z',
      message_count: 10,
      created_at: '2025-01-01T00:00:00Z',
      updated_at: '2025-01-02T00:00:00Z',
    };

    expect(item.pinned).toBe(true);
    expect(item.pinned_at).toBe('2025-01-02T00:00:00Z');
  });

  it('should have exactly 7 fields in ConversationItem', () => {
    const item: ConversationItem = {
      id: 'conv-003',
      title: '字段检查',
      pinned: false,
      pinned_at: null,
      message_count: 0,
      created_at: '2025-01-01T00:00:00Z',
      updated_at: '2025-01-01T00:00:00Z',
    };

    const keys = Object.keys(item);
    expect(keys).toHaveLength(7);
    expect(keys).toContain('id');
    expect(keys).toContain('title');
    expect(keys).toContain('pinned');
    expect(keys).toContain('pinned_at');
    expect(keys).toContain('message_count');
    expect(keys).toContain('created_at');
    expect(keys).toContain('updated_at');
  });
});

describe('ConversationListState type', () => {
  it('should accept a valid ConversationListState with all required fields', () => {
    const state: ConversationListState = {
      items: [],
      cursor: null,
      hasMore: true,
      isLoading: false,
      isInitialized: false,
      activeId: null,
      isNewConversation: false,
    };

    expect(state.items).toEqual([]);
    expect(state.cursor).toBeNull();
    expect(state.hasMore).toBe(true);
    expect(state.isLoading).toBe(false);
    expect(state.isInitialized).toBe(false);
    expect(state.activeId).toBeNull();
    expect(state.isNewConversation).toBe(false);
  });

  it('should accept items array with ConversationItem objects', () => {
    const item: ConversationItem = {
      id: 'conv-001',
      title: '对话1',
      pinned: false,
      pinned_at: null,
      message_count: 3,
      created_at: '2025-01-01T00:00:00Z',
      updated_at: '2025-01-01T00:00:00Z',
    };

    const state: ConversationListState = {
      items: [item],
      cursor: 'cursor-abc',
      hasMore: false,
      isLoading: false,
      isInitialized: true,
      activeId: 'conv-001',
      isNewConversation: false,
    };

    expect(state.items).toHaveLength(1);
    expect(state.items[0]).toEqual(item);
    expect(state.cursor).toBe('cursor-abc');
    expect(state.activeId).toBe('conv-001');
    expect(state.isInitialized).toBe(true);
  });

  it('should have exactly 7 fields in ConversationListState', () => {
    const state: ConversationListState = {
      items: [],
      cursor: null,
      hasMore: false,
      isLoading: false,
      isInitialized: false,
      activeId: null,
      isNewConversation: false,
    };

    const keys = Object.keys(state);
    expect(keys).toHaveLength(7);
    expect(keys).toContain('items');
    expect(keys).toContain('cursor');
    expect(keys).toContain('hasMore');
    expect(keys).toContain('isLoading');
    expect(keys).toContain('isInitialized');
    expect(keys).toContain('activeId');
    expect(keys).toContain('isNewConversation');
  });

  it('should represent a loading state correctly', () => {
    const state: ConversationListState = {
      items: [],
      cursor: null,
      hasMore: true,
      isLoading: true,
      isInitialized: false,
      activeId: null,
      isNewConversation: false,
    };

    expect(state.isLoading).toBe(true);
    expect(state.isInitialized).toBe(false);
    expect(state.hasMore).toBe(true);
  });

  it('should represent a new conversation state correctly', () => {
    const state: ConversationListState = {
      items: [],
      cursor: null,
      hasMore: false,
      isLoading: false,
      isInitialized: true,
      activeId: null,
      isNewConversation: true,
    };

    expect(state.isNewConversation).toBe(true);
    expect(state.activeId).toBeNull();
  });
});

describe('SSECallbacks type', () => {
  it('should accept callbacks object with onTitle callback', () => {
    const callbacks: SSECallbacks = {
      onInit: (_conversationId: string) => {},
      onStatus: (_stage: string, _message: string) => {},
      onSources: (_sources: never[]) => {},
      onToken: (_token: string) => {},
      onThinking: (_step: never) => {},
      onDone: () => {},
      onTitle: (_conversationId: string, _title: string) => {},
      onError: (_error: { code: string; message: string; action: string }) => {},
    };

    // 验证 onTitle 是一个函数
    expect(typeof callbacks.onTitle).toBe('function');
  });

  it('should have exactly 8 callback fields including onTitle', () => {
    const callbacks: SSECallbacks = {
      onInit: () => {},
      onStatus: () => {},
      onSources: () => {},
      onToken: () => {},
      onThinking: () => {},
      onDone: () => {},
      onTitle: () => {},
      onError: () => {},
    };

    const keys = Object.keys(callbacks);
    expect(keys).toHaveLength(8);
    expect(keys).toContain('onTitle');
    expect(keys).toContain('onInit');
    expect(keys).toContain('onStatus');
    expect(keys).toContain('onSources');
    expect(keys).toContain('onToken');
    expect(keys).toContain('onThinking');
    expect(keys).toContain('onDone');
    expect(keys).toContain('onError');
  });
});
