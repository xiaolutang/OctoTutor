/**
 * R009-FB002 三点菜单交互（内联在 ConversationItemCard）— 纯逻辑测试
 *
 * 测试策略：提取 ConversationItemCard 的状态管理逻辑为纯函数，覆盖：
 * - 菜单弹出/关闭
 * - 重命名提交/取消
 * - 置顶/取消置顶
 * - 删除确认/取消
 */
import { describe, it, expect } from 'vitest';
import type { ConversationItem } from '@/chat/types';

// ============================================================
// 类型定义（模拟组件状态）
// ============================================================

interface CardState {
  isRenaming: boolean;
  renameValue: string;
  menuOpen: boolean;
  deleteOpen: boolean;
}

// ============================================================
// 模拟 ConversationItemCard 逻辑（纯函数）
// ============================================================

function createInitialState(title: string): CardState {
  return {
    isRenaming: false,
    renameValue: title,
    menuOpen: false,
    deleteOpen: false,
  };
}

/** 点击三点按钮切换菜单 */
function toggleMenu(state: CardState): CardState {
  return { ...state, menuOpen: !state.menuOpen };
}

/** 关闭菜单 */
function closeMenu(state: CardState): CardState {
  return { ...state, menuOpen: false };
}

/** 点击「重命名」菜单项 */
function startRename(state: CardState, currentTitle: string): CardState {
  return {
    ...state,
    menuOpen: false,
    renameValue: currentTitle,
    isRenaming: true,
  };
}

/**
 * 重命名提交逻辑
 * 返回 { newState, shouldCallRename, renameArgs }
 */
function handleRenameSubmit(
  state: CardState,
  originalTitle: string,
): {
  newState: CardState;
  shouldCallRename: boolean;
  renameArgs: { id: string; title: string } | null;
} {
  const trimmed = state.renameValue.trim();
  if (trimmed && trimmed !== originalTitle) {
    return {
      newState: { ...state, isRenaming: false },
      shouldCallRename: true,
      renameArgs: null, // id 由外部传入，此处仅标记需要调用
    };
  }
  if (!trimmed) {
    return {
      newState: { ...state, isRenaming: false, renameValue: originalTitle },
      shouldCallRename: false,
      renameArgs: null,
    };
  }
  // trimmed === originalTitle，不做修改
  return {
    newState: { ...state, isRenaming: false },
    shouldCallRename: false,
    renameArgs: null,
  };
}

/**
 * 重命名提交（带 id 版本，用于验证 onRename 调用参数）
 */
function handleRenameSubmitWithId(
  state: CardState,
  originalTitle: string,
  itemId: string,
): {
  newState: CardState;
  shouldCallRename: boolean;
  renameArgs: { id: string; title: string } | null;
} {
  const trimmed = state.renameValue.trim();
  if (trimmed && trimmed !== originalTitle) {
    return {
      newState: { ...state, isRenaming: false },
      shouldCallRename: true,
      renameArgs: { id: itemId, title: trimmed },
    };
  }
  if (!trimmed) {
    return {
      newState: { ...state, isRenaming: false, renameValue: originalTitle },
      shouldCallRename: false,
      renameArgs: null,
    };
  }
  return {
    newState: { ...state, isRenaming: false },
    shouldCallRename: false,
    renameArgs: null,
  };
}

/** 按 Escape 取消重命名 */
function handleRenameEscape(state: CardState, originalTitle: string): CardState {
  return {
    ...state,
    renameValue: originalTitle,
    isRenaming: false,
  };
}

/** 更新重命名输入值 */
function updateRenameValue(state: CardState, value: string): CardState {
  return { ...state, renameValue: value };
}

/**
 * 点击「置顶/取消置顶」菜单项
 * 返回 { newState, action: 'pin' | 'unpin' | null }
 */
function handlePinToggle(state: CardState, itemPinned: boolean): {
  newState: CardState;
  action: 'pin' | 'unpin';
} {
  return {
    newState: { ...state, menuOpen: false },
    action: itemPinned ? 'unpin' : 'pin',
  };
}

/** 点击「删除」菜单项 */
function openDeleteDialog(state: CardState): CardState {
  return {
    ...state,
    menuOpen: false,
    deleteOpen: true,
  };
}

/** 删除确认 */
function confirmDelete(state: CardState): { newState: CardState; shouldDelete: true } {
  return {
    newState: { ...state, deleteOpen: false, menuOpen: false },
    shouldDelete: true,
  };
}

/** 删除取消 */
function cancelDelete(state: CardState): { newState: CardState; shouldDelete: false } {
  return {
    newState: { ...state, deleteOpen: false },
    shouldDelete: false,
  };
}

// ============================================================
// 测试数据
// ============================================================

const createMockItem = (overrides: Partial<ConversationItem> = {}): ConversationItem => ({
  id: 'conv-1',
  title: '测试对话',
  pinned: false,
  pinned_at: null,
  message_count: 5,
  created_at: '2026-05-24T10:00:00Z',
  updated_at: '2026-05-25T08:00:00Z',
  ...overrides,
});

// ============================================================
// 测试用例
// ============================================================

describe('ConversationItemCard 三点菜单交互逻辑', () => {
  // ----------------------------------
  // 菜单弹出
  // ----------------------------------
  describe('菜单弹出', () => {
    it('初始状态菜单应关闭', () => {
      const state = createInitialState('测试对话');
      expect(state.menuOpen).toBe(false);
    });

    it('点击三点按钮菜单应弹出', () => {
      const state = createInitialState('测试对话');
      const toggled = toggleMenu(state);
      expect(toggled.menuOpen).toBe(true);
    });

    it('再次点击三点按钮菜单应关闭', () => {
      const state = createInitialState('测试对话');
      const opened = toggleMenu(state);
      const closed = toggleMenu(opened);
      expect(closed.menuOpen).toBe(false);
    });
  });

  // ----------------------------------
  // 重命名提交
  // ----------------------------------
  describe('重命名提交', () => {
    it('点击重命名应进入重命名模式并关闭菜单', () => {
      const state = createInitialState('原标题');
      const menuOpened = toggleMenu(state);
      const renaming = startRename(menuOpened, '原标题');
      expect(renaming.isRenaming).toBe(true);
      expect(renaming.menuOpen).toBe(false);
      expect(renaming.renameValue).toBe('原标题');
    });

    it('输入新标题后提交应触发 onRename', () => {
      const item = createMockItem({ title: '原标题' });
      let state = createInitialState(item.title);
      state = startRename(state, item.title);
      state = updateRenameValue(state, '新标题');

      const result = handleRenameSubmitWithId(state, item.title, item.id);
      expect(result.shouldCallRename).toBe(true);
      expect(result.renameArgs).toEqual({ id: 'conv-1', title: '新标题' });
      expect(result.newState.isRenaming).toBe(false);
    });

    it('输入前后空格的标题提交时应 trim', () => {
      const item = createMockItem({ title: '原标题' });
      let state = createInitialState(item.title);
      state = startRename(state, item.title);
      state = updateRenameValue(state, '  新标题  ');

      const result = handleRenameSubmitWithId(state, item.title, item.id);
      expect(result.shouldCallRename).toBe(true);
      expect(result.renameArgs!.title).toBe('新标题');
    });

    it('标题未改变时提交不应触发 onRename', () => {
      const item = createMockItem({ title: '不变标题' });
      let state = createInitialState(item.title);
      state = startRename(state, item.title);
      // 不修改 renameValue

      const result = handleRenameSubmit(state, item.title);
      expect(result.shouldCallRename).toBe(false);
      expect(result.newState.isRenaming).toBe(false);
    });

    it('清空标题后提交应恢复原标题且不调用 onRename', () => {
      const item = createMockItem({ title: '原标题' });
      let state = createInitialState(item.title);
      state = startRename(state, item.title);
      state = updateRenameValue(state, '');

      const result = handleRenameSubmit(state, item.title);
      expect(result.shouldCallRename).toBe(false);
      expect(result.newState.renameValue).toBe('原标题');
      expect(result.newState.isRenaming).toBe(false);
    });

    it('仅输入空格后提交应恢复原标题且不调用 onRename', () => {
      const item = createMockItem({ title: '原标题' });
      let state = createInitialState(item.title);
      state = startRename(state, item.title);
      state = updateRenameValue(state, '   ');

      const result = handleRenameSubmit(state, item.title);
      expect(result.shouldCallRename).toBe(false);
      expect(result.newState.renameValue).toBe('原标题');
    });
  });

  // ----------------------------------
  // 重命名取消
  // ----------------------------------
  describe('重命名取消', () => {
    it('按 Escape 应恢复原标题并退出重命名', () => {
      const item = createMockItem({ title: '原标题' });
      let state = createInitialState(item.title);
      state = startRename(state, item.title);
      state = updateRenameValue(state, '修改中的标题');

      const escaped = handleRenameEscape(state, item.title);
      expect(escaped.renameValue).toBe('原标题');
      expect(escaped.isRenaming).toBe(false);
    });

    it('取消重命名后 onRename 不应被调用', () => {
      const item = createMockItem({ title: '原标题' });
      let state = createInitialState(item.title);
      state = startRename(state, item.title);
      state = updateRenameValue(state, '新标题');

      // 按 Escape 取消
      const escaped = handleRenameEscape(state, item.title);
      // 验证标题已恢复，进一步验证提交逻辑不会被触发
      // （因为组件中 Escape 后直接 setIsRenaming(false)，不会走到 handleSubmit）
      expect(escaped.renameValue).toBe('原标题');
      expect(escaped.isRenaming).toBe(false);
      // 如果此时再手动调 handleRenameSubmit，因为 renameValue 已恢复，不会触发
      const result = handleRenameSubmit(escaped, item.title);
      expect(result.shouldCallRename).toBe(false);
    });
  });

  // ----------------------------------
  // 置顶操作
  // ----------------------------------
  describe('置顶操作', () => {
    it('对未置顶的 item 点击置顶应调用 onTogglePin', () => {
      const item = createMockItem({ pinned: false });
      let state = createInitialState(item.title);
      state = toggleMenu(state);

      const result = handlePinToggle(state, item.pinned);
      expect(result.action).toBe('pin');
      expect(result.newState.menuOpen).toBe(false);
    });

    it('置顶后菜单应关闭', () => {
      const item = createMockItem({ pinned: false });
      let state = createInitialState(item.title);
      state = toggleMenu(state);
      expect(state.menuOpen).toBe(true);

      const result = handlePinToggle(state, item.pinned);
      expect(result.newState.menuOpen).toBe(false);
    });
  });

  // ----------------------------------
  // 取消置顶
  // ----------------------------------
  describe('取消置顶', () => {
    it('对已置顶的 item 点击取消置顶应调用 onTogglePin', () => {
      const item = createMockItem({ pinned: true, pinned_at: '2026-05-25T00:00:00Z' });
      let state = createInitialState(item.title);
      state = toggleMenu(state);

      const result = handlePinToggle(state, item.pinned);
      expect(result.action).toBe('unpin');
      expect(result.newState.menuOpen).toBe(false);
    });
  });

  // ----------------------------------
  // 删除确认
  // ----------------------------------
  describe('删除确认', () => {
    it('点击删除应弹出确认弹窗并关闭菜单', () => {
      let state = createInitialState('测试');
      state = toggleMenu(state);
      expect(state.menuOpen).toBe(true);

      state = openDeleteDialog(state);
      expect(state.deleteOpen).toBe(true);
      expect(state.menuOpen).toBe(false);
    });

    it('确认删除应调用 onDelete 并关闭弹窗', () => {
      let state = createInitialState('测试');
      state = openDeleteDialog(state);

      const result = confirmDelete(state);
      expect(result.shouldDelete).toBe(true);
      expect(result.newState.deleteOpen).toBe(false);
      expect(result.newState.menuOpen).toBe(false);
    });
  });

  // ----------------------------------
  // 删除取消
  // ----------------------------------
  describe('删除取消', () => {
    it('取消删除不应调用 onDelete 并关闭弹窗', () => {
      let state = createInitialState('测试');
      state = openDeleteDialog(state);
      expect(state.deleteOpen).toBe(true);

      const result = cancelDelete(state);
      expect(result.shouldDelete).toBe(false);
      expect(result.newState.deleteOpen).toBe(false);
    });

    it('取消删除后菜单也应保持关闭', () => {
      let state = createInitialState('测试');
      state = toggleMenu(state);
      state = openDeleteDialog(state);

      const result = cancelDelete(state);
      expect(result.newState.menuOpen).toBe(false);
      expect(result.newState.deleteOpen).toBe(false);
    });
  });

  // ----------------------------------
  // 边界场景
  // ----------------------------------
  describe('边界场景', () => {
    it('重命名过程中点击删除应正常处理', () => {
      const item = createMockItem({ title: '原标题' });
      let state = createInitialState(item.title);
      state = startRename(state, item.title);
      state = updateRenameValue(state, '修改中');
      expect(state.isRenaming).toBe(true);

      // 重命名模式下菜单按钮不显示（组件中 !isRenaming 控制渲染）
      // 但删除弹窗可以独立打开
      state = openDeleteDialog(state);
      expect(state.deleteOpen).toBe(true);
      expect(state.isRenaming).toBe(true);
    });

    it('完整操作流程：打开菜单 -> 重命名 -> 输入 -> 提交', () => {
      const item = createMockItem({ id: 'conv-123', title: '原始标题' });

      // 1. 初始状态
      let state = createInitialState(item.title);
      expect(state.menuOpen).toBe(false);
      expect(state.isRenaming).toBe(false);

      // 2. 打开菜单
      state = toggleMenu(state);
      expect(state.menuOpen).toBe(true);

      // 3. 点击重命名
      state = startRename(state, item.title);
      expect(state.menuOpen).toBe(false);
      expect(state.isRenaming).toBe(true);

      // 4. 输入新标题
      state = updateRenameValue(state, '更新后的标题');

      // 5. 提交（按 Enter）
      const result = handleRenameSubmitWithId(state, item.title, item.id);
      expect(result.shouldCallRename).toBe(true);
      expect(result.renameArgs).toEqual({ id: 'conv-123', title: '更新后的标题' });
      expect(result.newState.isRenaming).toBe(false);
    });

    it('完整操作流程：打开菜单 -> 删除 -> 确认', () => {
      const item = createMockItem();

      let state = createInitialState(item.title);
      state = toggleMenu(state);
      state = openDeleteDialog(state);

      const result = confirmDelete(state);
      expect(result.shouldDelete).toBe(true);
      expect(result.newState.deleteOpen).toBe(false);
      expect(result.newState.menuOpen).toBe(false);
    });

    it('完整操作流程：打开菜单 -> 删除 -> 取消', () => {
      const item = createMockItem();

      let state = createInitialState(item.title);
      state = toggleMenu(state);
      state = openDeleteDialog(state);

      const result = cancelDelete(state);
      expect(result.shouldDelete).toBe(false);
      expect(result.newState.deleteOpen).toBe(false);
    });
  });
});
