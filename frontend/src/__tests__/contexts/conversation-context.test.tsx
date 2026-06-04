/**
 * FF003: ConversationContext 状态管理测试
 *
 * 测试 conversation-reducer.ts 中的 conversationReducer 纯函数。
 * Reducer 已提取为独立模块，无需 import conversation-context.tsx（避免 auth-sdk-web symlink 问题）。
 */

/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import type { ConversationItem, ConversationListState } from '@/chat/types';
import {
  conversationReducer,
  initialState,
} from '@/chat/conversation-reducer';
import { createId } from '@/lib/utils';

const STORAGE_KEY = 'octotutor_active_conversation_id';

// ============================================================
// 测试数据工厂
// ============================================================

function createMockItem(overrides: Partial<ConversationItem> = {}): ConversationItem {
  return {
    id: `conv-${createId()}`,
    title: '测试对话',
    pinned: false,
    pinned_at: null,
    message_count: 1,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

const mockItems: ConversationItem[] = [
  createMockItem({ id: 'conv-1', title: '对话一' }),
  createMockItem({ id: 'conv-2', title: '对话二' }),
  createMockItem({ id: 'conv-3', title: '对话三' }),
];

// ============================================================
// 测试
// ============================================================

describe('FF003: ConversationContext 状态管理', () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  // ============================================================
  // T1: 初始化加载列表 — INIT_LIST
  // ============================================================
  describe('T1: 初始化加载列表 (INIT_LIST)', () => {
    it('should set items, cursor, hasMore and mark as initialized', () => {
      const result = {
        items: mockItems,
        cursor: 'cursor-page-2',
        hasMore: true,
      };

      const nextState = conversationReducer(initialState, {
        type: 'INIT_LIST',
        payload: result,
      });

      expect(nextState.items).toEqual(mockItems);
      expect(nextState.items).toHaveLength(3);
      expect(nextState.cursor).toBe('cursor-page-2');
      expect(nextState.hasMore).toBe(true);
      expect(nextState.isInitialized).toBe(true);
      expect(nextState.isLoading).toBe(false);
    });

    it('should set hasMore=false when no more pages', () => {
      const result = {
        items: mockItems,
        cursor: null,
        hasMore: false,
      };

      const nextState = conversationReducer(initialState, {
        type: 'INIT_LIST',
        payload: result,
      });

      expect(nextState.hasMore).toBe(false);
      expect(nextState.cursor).toBeNull();
      expect(nextState.isInitialized).toBe(true);
    });

    it('should replace existing items on INIT_LIST', () => {
      const stateWithItems: ConversationListState = {
        ...initialState,
        items: [createMockItem({ id: 'old-item' })],
      };

      const nextState = conversationReducer(stateWithItems, {
        type: 'INIT_LIST',
        payload: { items: mockItems, cursor: null, hasMore: false },
      });

      expect(nextState.items).toEqual(mockItems);
      expect(nextState.items.find((i) => i.id === 'old-item')).toBeUndefined();
    });
  });

  // ============================================================
  // T2: SET_LOADING
  // ============================================================
  it('T2: SET_LOADING should toggle loading state', () => {
    const loading = conversationReducer(initialState, {
      type: 'SET_LOADING',
      payload: true,
    });
    expect(loading.isLoading).toBe(true);

    const notLoading = conversationReducer(loading, {
      type: 'SET_LOADING',
      payload: false,
    });
    expect(notLoading.isLoading).toBe(false);
  });

  // ============================================================
  // T3: switchTo 切换 — SET_ACTIVE
  // ============================================================
  describe('T3: switchTo 切换 (SET_ACTIVE)', () => {
    it('should update activeId to the given id', () => {
      const state: ConversationListState = {
        ...initialState,
        items: mockItems,
      };

      const nextState = conversationReducer(state, {
        type: 'SET_ACTIVE',
        payload: 'conv-2',
      });

      expect(nextState.activeId).toBe('conv-2');
    });

    it('should reset isNewConversation to false when switching', () => {
      const state: ConversationListState = {
        ...initialState,
        isNewConversation: true,
      };

      const nextState = conversationReducer(state, {
        type: 'SET_ACTIVE',
        payload: 'conv-1',
      });

      expect(nextState.isNewConversation).toBe(false);
    });

    it('should allow setting activeId to null', () => {
      const state: ConversationListState = {
        ...initialState,
        activeId: 'conv-1',
      };

      const nextState = conversationReducer(state, {
        type: 'SET_ACTIVE',
        payload: null,
      });

      expect(nextState.activeId).toBeNull();
    });

    it('should persist activeId to sessionStorage', () => {
      conversationReducer(initialState, {
        type: 'SET_ACTIVE',
        payload: 'conv-1',
      });

      expect(sessionStorage.getItem(STORAGE_KEY)).toBe('conv-1');
    });

    it('should remove from sessionStorage when activeId is null', () => {
      sessionStorage.setItem(STORAGE_KEY, 'conv-1');
      conversationReducer(initialState, {
        type: 'SET_ACTIVE',
        payload: null,
      });

      expect(sessionStorage.getItem(STORAGE_KEY)).toBeNull();
    });
  });

  // ============================================================
  // T4: createNew — SET_NEW_CONVERSATION
  // ============================================================
  describe('T4: createNew (SET_NEW_CONVERSATION)', () => {
    it('should set isNewConversation=true and activeId=null', () => {
      const state: ConversationListState = {
        ...initialState,
        activeId: 'conv-1',
        isNewConversation: false,
      };

      const nextState = conversationReducer(state, {
        type: 'SET_NEW_CONVERSATION',
        payload: true,
      });

      expect(nextState.isNewConversation).toBe(true);
      expect(nextState.activeId).toBeNull();
    });

    it('should keep existing items intact', () => {
      const state: ConversationListState = {
        ...initialState,
        items: mockItems,
      };

      const nextState = conversationReducer(state, {
        type: 'SET_NEW_CONVERSATION',
        payload: true,
      });

      expect(nextState.items).toEqual(mockItems);
    });
  });

  // ============================================================
  // T5: insertNewConversation — INSERT_NEW
  // ============================================================
  describe('T5: insertNewConversation (INSERT_NEW)', () => {
    it('should insert new item at the top of items', () => {
      const state: ConversationListState = {
        ...initialState,
        items: mockItems,
      };

      const newItem = createMockItem({ id: 'conv-new', title: '新对话' });

      const nextState = conversationReducer(state, {
        type: 'INSERT_NEW',
        payload: newItem,
      });

      expect(nextState.items).toHaveLength(4);
      expect(nextState.items[0]).toEqual(newItem);
      expect(nextState.items[0].id).toBe('conv-new');
    });

    it('should set activeId to the new item id', () => {
      const state: ConversationListState = {
        ...initialState,
        items: mockItems,
        activeId: 'conv-1',
      };

      const newItem = createMockItem({ id: 'conv-new' });

      const nextState = conversationReducer(state, {
        type: 'INSERT_NEW',
        payload: newItem,
      });

      expect(nextState.activeId).toBe('conv-new');
    });

    it('should set isNewConversation to false', () => {
      const state: ConversationListState = {
        ...initialState,
        isNewConversation: true,
      };

      const newItem = createMockItem({ id: 'conv-new' });

      const nextState = conversationReducer(state, {
        type: 'INSERT_NEW',
        payload: newItem,
      });

      expect(nextState.isNewConversation).toBe(false);
    });

    it('should preserve existing items after the new one', () => {
      const state: ConversationListState = {
        ...initialState,
        items: mockItems,
      };

      const newItem = createMockItem({ id: 'conv-new' });

      const nextState = conversationReducer(state, {
        type: 'INSERT_NEW',
        payload: newItem,
      });

      // 原有项目依次后移
      expect(nextState.items[1]).toEqual(mockItems[0]);
      expect(nextState.items[2]).toEqual(mockItems[1]);
      expect(nextState.items[3]).toEqual(mockItems[2]);
    });
  });

  // ============================================================
  // T6: updateTitle — UPDATE_TITLE
  // ============================================================
  describe('T6: updateTitle (UPDATE_TITLE)', () => {
    it('should update the title of the matching item', () => {
      const state: ConversationListState = {
        ...initialState,
        items: mockItems,
      };

      const nextState = conversationReducer(state, {
        type: 'UPDATE_TITLE',
        payload: { id: 'conv-2', title: '新标题' },
      });

      const updated = nextState.items.find((i) => i.id === 'conv-2');
      expect(updated?.title).toBe('新标题');
    });

    it('should not modify other items', () => {
      const state: ConversationListState = {
        ...initialState,
        items: mockItems,
      };

      const nextState = conversationReducer(state, {
        type: 'UPDATE_TITLE',
        payload: { id: 'conv-2', title: '新标题' },
      });

      const item1 = nextState.items.find((i) => i.id === 'conv-1');
      const item3 = nextState.items.find((i) => i.id === 'conv-3');
      expect(item1?.title).toBe('对话一');
      expect(item3?.title).toBe('对话三');
    });

    it('should not change items if id does not match', () => {
      const state: ConversationListState = {
        ...initialState,
        items: mockItems,
      };

      const nextState = conversationReducer(state, {
        type: 'UPDATE_TITLE',
        payload: { id: 'non-existent', title: '不存在' },
      });

      expect(nextState.items).toEqual(mockItems);
    });
  });

  // ============================================================
  // T7: loadMore 分页 — APPEND_PAGE
  // ============================================================
  describe('T7: loadMore 分页 (APPEND_PAGE)', () => {
    it('should append new items to existing list', () => {
      const state: ConversationListState = {
        ...initialState,
        items: mockItems,
        cursor: 'cursor-page-1',
        hasMore: true,
      };

      const nextPage = [
        createMockItem({ id: 'conv-4', title: '对话四' }),
        createMockItem({ id: 'conv-5', title: '对话五' }),
      ];

      const nextState = conversationReducer(state, {
        type: 'APPEND_PAGE',
        payload: { items: nextPage, cursor: 'cursor-page-3', hasMore: true },
      });

      expect(nextState.items).toHaveLength(5);
      expect(nextState.items[3].id).toBe('conv-4');
      expect(nextState.items[4].id).toBe('conv-5');
    });

    it('should update cursor after loading more', () => {
      const state: ConversationListState = {
        ...initialState,
        items: mockItems,
        cursor: 'cursor-page-1',
        hasMore: true,
      };

      const nextState = conversationReducer(state, {
        type: 'APPEND_PAGE',
        payload: {
          items: [createMockItem({ id: 'conv-4' })],
          cursor: 'cursor-page-3',
          hasMore: false,
        },
      });

      expect(nextState.cursor).toBe('cursor-page-3');
      expect(nextState.hasMore).toBe(false);
    });

    it('should handle last page (hasMore=false, cursor=null)', () => {
      const state: ConversationListState = {
        ...initialState,
        items: mockItems,
        cursor: 'cursor-page-2',
        hasMore: true,
      };

      const nextState = conversationReducer(state, {
        type: 'APPEND_PAGE',
        payload: {
          items: [createMockItem({ id: 'conv-last' })],
          cursor: null,
          hasMore: false,
        },
      });

      expect(nextState.hasMore).toBe(false);
      expect(nextState.cursor).toBeNull();
      expect(nextState.items).toHaveLength(4);
    });

    it('should preserve existing items order when appending', () => {
      const state: ConversationListState = {
        ...initialState,
        items: mockItems,
      };

      const newPage = [createMockItem({ id: 'conv-4' })];

      const nextState = conversationReducer(state, {
        type: 'APPEND_PAGE',
        payload: { items: newPage, cursor: null, hasMore: false },
      });

      // 原有顺序不变
      expect(nextState.items[0].id).toBe('conv-1');
      expect(nextState.items[1].id).toBe('conv-2');
      expect(nextState.items[2].id).toBe('conv-3');
      expect(nextState.items[3].id).toBe('conv-4');
    });
  });

  // ============================================================
  // T8: deleteConversation — REMOVE_ITEM
  // ============================================================
  describe('T8: deleteConversation 移除 (REMOVE_ITEM)', () => {
    it('should remove the item with matching id', () => {
      const state: ConversationListState = {
        ...initialState,
        items: mockItems,
      };

      const nextState = conversationReducer(state, {
        type: 'REMOVE_ITEM',
        payload: 'conv-2',
      });

      expect(nextState.items).toHaveLength(2);
      expect(nextState.items.find((i) => i.id === 'conv-2')).toBeUndefined();
    });

    it('should not affect other items', () => {
      const state: ConversationListState = {
        ...initialState,
        items: mockItems,
      };

      const nextState = conversationReducer(state, {
        type: 'REMOVE_ITEM',
        payload: 'conv-2',
      });

      expect(nextState.items[0].id).toBe('conv-1');
      expect(nextState.items[1].id).toBe('conv-3');
    });

    it('should handle removing non-existent id gracefully', () => {
      const state: ConversationListState = {
        ...initialState,
        items: mockItems,
      };

      const nextState = conversationReducer(state, {
        type: 'REMOVE_ITEM',
        payload: 'non-existent',
      });

      expect(nextState.items).toEqual(mockItems);
      expect(nextState.items).toHaveLength(3);
    });
  });

  // ============================================================
  // T9: 删除当前对话自动切换 — REMOVE_ITEM + SET_ACTIVE 组合
  // ============================================================
  describe('T9: 删除当前对话自动切换', () => {
    it('should switch to first remaining item after deleting active conversation', () => {
      // 模拟 Provider 中 deleteConversation 的逻辑：
      // 1. REMOVE_ITEM 删除
      // 2. 如果删除的是 activeId，SET_ACTIVE 到列表第一个

      const state: ConversationListState = {
        ...initialState,
        items: mockItems,
        activeId: 'conv-1',
      };

      // Step 1: remove item
      const afterRemove = conversationReducer(state, {
        type: 'REMOVE_ITEM',
        payload: 'conv-1',
      });

      expect(afterRemove.items.find((i) => i.id === 'conv-1')).toBeUndefined();

      // Step 2: simulate Provider logic — remaining items 的第一个
      const remaining = afterRemove.items;
      const newActiveId = remaining.length > 0 ? remaining[0].id : null;

      const afterSwitch = conversationReducer(afterRemove, {
        type: 'SET_ACTIVE',
        payload: newActiveId,
      });

      expect(afterSwitch.activeId).toBe('conv-2');
    });

    it('should set activeId to null when deleting the only conversation', () => {
      const onlyItem = createMockItem({ id: 'conv-only' });
      const state: ConversationListState = {
        ...initialState,
        items: [onlyItem],
        activeId: 'conv-only',
      };

      // Step 1: remove
      const afterRemove = conversationReducer(state, {
        type: 'REMOVE_ITEM',
        payload: 'conv-only',
      });

      expect(afterRemove.items).toHaveLength(0);

      // Step 2: remaining 为空，activeId 应该设为 null
      const remaining = afterRemove.items;
      const newActiveId = remaining.length > 0 ? remaining[0].id : null;

      const afterSwitch = conversationReducer(afterRemove, {
        type: 'SET_ACTIVE',
        payload: newActiveId,
      });

      expect(afterSwitch.activeId).toBeNull();
    });

    it('should keep activeId unchanged when deleting non-active conversation', () => {
      const state: ConversationListState = {
        ...initialState,
        items: mockItems,
        activeId: 'conv-1',
      };

      const afterRemove = conversationReducer(state, {
        type: 'REMOVE_ITEM',
        payload: 'conv-3',
      });

      // activeId 不是被删除的 id，所以不需要切换
      expect(afterRemove.activeId).toBe('conv-1');
    });

    it('should switch to correct item when deleting active in middle of list', () => {
      const state: ConversationListState = {
        ...initialState,
        items: mockItems,
        activeId: 'conv-2', // 中间的项
      };

      const afterRemove = conversationReducer(state, {
        type: 'REMOVE_ITEM',
        payload: 'conv-2',
      });

      const remaining = afterRemove.items;
      const newActiveId = remaining.length > 0 ? remaining[0].id : null;

      const afterSwitch = conversationReducer(afterRemove, {
        type: 'SET_ACTIVE',
        payload: newActiveId,
      });

      // 删除 conv-2 后，remaining = [conv-1, conv-3]，第一个是 conv-1
      expect(afterSwitch.activeId).toBe('conv-1');
      expect(afterSwitch.items).toHaveLength(2);
    });
  });

  // ============================================================
  // T10: UPDATE_ITEM
  // ============================================================
  describe('T10: UPDATE_ITEM', () => {
    it('should replace entire item with updated version', () => {
      const state: ConversationListState = {
        ...initialState,
        items: mockItems,
      };

      const updatedItem: ConversationItem = {
        ...mockItems[1],
        title: '更新后标题',
        pinned: true,
        pinned_at: '2026-01-02T00:00:00Z',
      };

      const nextState = conversationReducer(state, {
        type: 'UPDATE_ITEM',
        payload: updatedItem,
      });

      const found = nextState.items.find((i) => i.id === 'conv-2');
      expect(found?.title).toBe('更新后标题');
      expect(found?.pinned).toBe(true);
      expect(found?.pinned_at).toBe('2026-01-02T00:00:00Z');
    });

    it('should not modify other items', () => {
      const state: ConversationListState = {
        ...initialState,
        items: mockItems,
      };

      const updatedItem: ConversationItem = {
        ...mockItems[1],
        title: '更新后标题',
      };

      const nextState = conversationReducer(state, {
        type: 'UPDATE_ITEM',
        payload: updatedItem,
      });

      // UPDATE_ITEM 会重排序，用 find 按 id 检查而非 index
      const other1 = nextState.items.find((i) => i.id === 'conv-1');
      const other3 = nextState.items.find((i) => i.id === 'conv-3');
      expect(other1?.title).toBe('对话一');
      expect(other3?.title).toBe('对话三');
    });
  });

  // ============================================================
  // T11: 初始状态验证
  // ============================================================
  describe('T11: 初始状态', () => {
    it('should have correct initial state', () => {
      expect(initialState.items).toEqual([]);
      expect(initialState.cursor).toBeNull();
      expect(initialState.hasMore).toBe(false);
      expect(initialState.isLoading).toBe(false);
      expect(initialState.isInitialized).toBe(false);
      expect(initialState.activeId).toBeNull();
      expect(initialState.isNewConversation).toBe(false);
    });
  });

  // ============================================================
  // T12: 完整工作流 — 创建新对话 -> 插入 -> 更新标题 -> 切换 -> 删除
  // ============================================================
  describe('T12: 完整工作流', () => {
    it('should handle full conversation lifecycle', () => {
      let state = initialState;

      // 1. 初始化加载列表
      state = conversationReducer(state, {
        type: 'INIT_LIST',
        payload: { items: mockItems, cursor: 'page-2', hasMore: true },
      });
      expect(state.items).toHaveLength(3);
      expect(state.isInitialized).toBe(true);

      // 2. 切换到某个对话
      state = conversationReducer(state, {
        type: 'SET_ACTIVE',
        payload: 'conv-1',
      });
      expect(state.activeId).toBe('conv-1');
      expect(state.isNewConversation).toBe(false);

      // 3. 创建新对话
      state = conversationReducer(state, {
        type: 'SET_NEW_CONVERSATION',
        payload: true,
      });
      expect(state.isNewConversation).toBe(true);
      expect(state.activeId).toBeNull();

      // 4. 插入新创建的对话
      const newItem = createMockItem({ id: 'conv-new', title: '新建对话' });
      state = conversationReducer(state, {
        type: 'INSERT_NEW',
        payload: newItem,
      });
      expect(state.items[0].id).toBe('conv-new');
      expect(state.activeId).toBe('conv-new');
      expect(state.isNewConversation).toBe(false);
      expect(state.items).toHaveLength(4);

      // 5. 更新标题
      state = conversationReducer(state, {
        type: 'UPDATE_TITLE',
        payload: { id: 'conv-new', title: '更新后的标题' },
      });
      expect(state.items[0].title).toBe('更新后的标题');

      // 6. 切换到另一个对话
      state = conversationReducer(state, {
        type: 'SET_ACTIVE',
        payload: 'conv-2',
      });
      expect(state.activeId).toBe('conv-2');

      // 7. 删除新创建的对话（非 activeId）
      state = conversationReducer(state, {
        type: 'REMOVE_ITEM',
        payload: 'conv-new',
      });
      expect(state.items).toHaveLength(3);
      expect(state.activeId).toBe('conv-2'); // activeId 不变

      // 8. 加载更多
      const moreItems = [createMockItem({ id: 'conv-6' })];
      state = conversationReducer(state, {
        type: 'APPEND_PAGE',
        payload: { items: moreItems, cursor: null, hasMore: false },
      });
      expect(state.items).toHaveLength(4);
      expect(state.hasMore).toBe(false);

      // 9. 删除当前 activeId 对话，自动切换
      state = conversationReducer(state, {
        type: 'REMOVE_ITEM',
        payload: 'conv-2',
      });
      const remaining = state.items;
      const nextActive = remaining.length > 0 ? remaining[0].id : null;
      state = conversationReducer(state, {
        type: 'SET_ACTIVE',
        payload: nextActive,
      });
      expect(state.activeId).toBe('conv-1'); // 切换到剩余的第一个
    });
  });

  // ============================================================
  // T13: Provider 函数逻辑验证（模拟 use-conversation-list 模块）
  // ============================================================
  describe('T13: Provider 函数逻辑模拟', () => {
    it('loadMore should skip when hasMore=false', () => {
      const state: ConversationListState = {
        ...initialState,
        items: mockItems,
        cursor: 'page-2',
        hasMore: false, // 没有更多了
      };

      // 模拟 loadMore 的 guard: if (!state.hasMore) return
      const shouldFetchMore = state.hasMore && !!state.cursor;
      expect(shouldFetchMore).toBe(false);
    });

    it('loadMore should skip when cursor is null', () => {
      const state: ConversationListState = {
        ...initialState,
        items: mockItems,
        cursor: null,
        hasMore: true,
      };

      const shouldFetchMore = state.hasMore && !!state.cursor;
      expect(shouldFetchMore).toBe(false);
    });

    it('loadMore should proceed when hasMore=true and cursor exists', () => {
      const state: ConversationListState = {
        ...initialState,
        items: mockItems,
        cursor: 'page-2',
        hasMore: true,
      };

      const shouldFetchMore = state.hasMore && !!state.cursor;
      expect(shouldFetchMore).toBe(true);
    });

    it('deleteConversation should identify if deleted item is active', () => {
      const state: ConversationListState = {
        ...initialState,
        items: mockItems,
        activeId: 'conv-1',
      };

      // 模拟 Provider 中的判断: if (state.activeId === id)
      expect(state.activeId === 'conv-1').toBe(true); // 是当前对话，需要自动切换
      expect(state.activeId === 'conv-2').toBe(false); // 不是当前对话
    });
  });
});
