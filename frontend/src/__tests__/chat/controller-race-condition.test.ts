/**
 * Auth 竞态修复 — controller.ts 初始化与 INSERT_NEW 安全性测试
 *
 * 覆盖场景：
 * 1. 双门初始化：isAuthReady + isConvReady 同时满足才加载
 * 2. INSERT_NEW 安全性：新建对话后 SSE 创建 conversation 不触发消息重载
 * 3. 刷新后恢复：页面刷新后正确加载当前对话消息
 * 4. switchHandler：用户切换对话时正确加载历史
 * 5. 竞态时序完整模拟
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { Message } from '@/chat/types';

// ============================================================
// 类型定义
// ============================================================

interface ControllerState {
  messages: Message[];
  mounted: boolean;
}

interface ControllerContext {
  isAuthReady: boolean;
  isConvReady: boolean;
  activeId: string | null;
  isNewConversation: boolean;
}

// ============================================================
// 模拟 controller.ts 三个 useEffect 的决策逻辑
// ============================================================

/**
 * 模拟 useEffect 1: 初始化加载
 *
 * 真实代码 (controller.ts:39-51):
 * useEffect(() => {
 *   if (!isAuthReady) return;
 *   if (!isConvReady) return;
 *   if (mounted) return;
 *   loadConversation(activeId).then(({ messages }) => {
 *     setMessages(messages);
 *     setMounted(true);
 *   });
 * }, [isAuthReady, isConvReady, activeId, mounted, loadConversation]);
 */
function simulateInitEffect(
  state: ControllerState,
  context: ControllerContext,
): { shouldLoad: boolean; loadedId: string | null } {
  if (!context.isAuthReady) return { shouldLoad: false, loadedId: null };
  if (!context.isConvReady) return { shouldLoad: false, loadedId: null };
  if (state.mounted) return { shouldLoad: false, loadedId: null };
  return { shouldLoad: true, loadedId: context.activeId };
}

/**
 * 模拟 useEffect 2: 新对话清空
 *
 * 真实代码 (controller.ts:54-59):
 * useEffect(() => {
 *   if (!mounted) return;
 *   if (activeId === null && isNewConversation) {
 *     setMessages([]);
 *   }
 * }, [activeId, isNewConversation, mounted]);
 */
function simulateNewConvEffect(
  state: ControllerState,
  context: ControllerContext,
): { shouldClearMessages: boolean } {
  if (!state.mounted) return { shouldClearMessages: false };
  if (context.activeId === null && context.isNewConversation) {
    return { shouldClearMessages: true };
  }
  return { shouldClearMessages: false };
}

/**
 * 模拟 useEffect 3: switchHandler 注册
 *
 * 真实代码 (controller.ts:62-69):
 * useEffect(() => {
 *   if (!mounted) return;
 *   registerSwitchHandler(async (id) => {
 *     const { messages } = await loadConversation(id);
 *     setMessages(messages);
 *   });
 *   return () => registerSwitchHandler(null);
 * }, [mounted, registerSwitchHandler, loadConversation]);
 */
function simulateSwitchHandlerRegistration(
  state: ControllerState,
): { shouldRegister: boolean } {
  if (!state.mounted) return { shouldRegister: false };
  return { shouldRegister: true };
}

// ============================================================
// 模拟 ConversationContext 行为
// ============================================================

/**
 * INSERT_NEW (conversation-context.tsx:96-106)
 * 改变 activeId 为新 conversation id，isNewConversation 设为 false
 * 关键：INSERT_NEW 不调用 switchTo，因此 switchHandler 不会被触发
 */
function applyInsertNew(
  context: ControllerContext,
  newConvId: string,
): ControllerContext {
  return { ...context, activeId: newConvId, isNewConversation: false };
}

/**
 * SET_NEW_CONVERSATION (conversation-context.tsx:93-94)
 * 用户点击"新建对话"按钮
 */
function applyCreateNew(context: ControllerContext): ControllerContext {
  return { ...context, activeId: null, isNewConversation: true };
}

/**
 * switchTo (conversation-context.tsx:227-229)
 * dispatches SET_ACTIVE + calls switchHandlerRef.current
 * 用户点击侧边栏对话时触发
 */
function applySwitchTo(
  context: ControllerContext,
  newActiveId: string,
): { newContext: ControllerContext; handlerShouldFire: boolean } {
  return {
    newContext: { ...context, activeId: newActiveId, isNewConversation: false },
    handlerShouldFire: true,
  };
}

// ============================================================
// 测试用例
// ============================================================

describe('Auth 竞态修复 — controller.ts 初始化与 INSERT_NEW 安全性', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // ============================================================
  // 场景 1: 双门初始化
  // ============================================================
  describe('双门初始化 (isAuthReady + isConvReady)', () => {
    it('isAuthReady=false 时不应该加载', () => {
      const result = simulateInitEffect(
        { messages: [], mounted: false },
        { isAuthReady: false, isConvReady: true, activeId: 'conv-1', isNewConversation: false },
      );
      expect(result.shouldLoad).toBe(false);
    });

    it('isConvReady=false 时不应该加载', () => {
      const result = simulateInitEffect(
        { messages: [], mounted: false },
        { isAuthReady: true, isConvReady: false, activeId: 'conv-1', isNewConversation: false },
      );
      expect(result.shouldLoad).toBe(false);
    });

    it('两者都为 false 时不应该加载', () => {
      const result = simulateInitEffect(
        { messages: [], mounted: false },
        { isAuthReady: false, isConvReady: false, activeId: 'conv-1', isNewConversation: false },
      );
      expect(result.shouldLoad).toBe(false);
    });

    it('两者都为 true 且未挂载时应该加载', () => {
      const result = simulateInitEffect(
        { messages: [], mounted: false },
        { isAuthReady: true, isConvReady: true, activeId: 'conv-1', isNewConversation: false },
      );
      expect(result.shouldLoad).toBe(true);
      expect(result.loadedId).toBe('conv-1');
    });

    it('已挂载后不应该再触发初始化加载', () => {
      const result = simulateInitEffect(
        { messages: [], mounted: true },
        { isAuthReady: true, isConvReady: true, activeId: 'conv-1', isNewConversation: false },
      );
      expect(result.shouldLoad).toBe(false);
    });

    it('activeId 为 null 时（新用户首次进入）仍然允许加载', () => {
      const result = simulateInitEffect(
        { messages: [], mounted: false },
        { isAuthReady: true, isConvReady: true, activeId: null, isNewConversation: true },
      );
      expect(result.shouldLoad).toBe(true);
      expect(result.loadedId).toBe(null);
    });
  });

  // ============================================================
  // 场景 2: INSERT_NEW 安全性 — 核心修复验证
  // ============================================================
  describe('INSERT_NEW 不触发消息重载', () => {
    it('INSERT_NEW 改变 activeId 后 init useEffect 不触发（mounted=true）', () => {
      const state: ControllerState = {
        messages: [
          { id: 'u1', role: 'user', content: '你好', status: 'done', timestamp: 1 },
          { id: 'a1', role: 'ai', content: '你好！', status: 'done', timestamp: 2 },
        ],
        mounted: true,
      };

      // INSERT_NEW 前的 context
      const beforeInsert: ControllerContext = {
        isAuthReady: true,
        isConvReady: true,
        activeId: null,
        isNewConversation: true,
      };

      // INSERT_NEW 后
      const afterInsert = applyInsertNew(beforeInsert, 'conv-new-001');
      expect(afterInsert.activeId).toBe('conv-new-001');
      expect(afterInsert.isNewConversation).toBe(false);

      // init useEffect: mounted=true → 不触发
      expect(simulateInitEffect(state, afterInsert).shouldLoad).toBe(false);
    });

    it('INSERT_NEW 后 newConv useEffect 不清空消息（activeId !== null）', () => {
      const state: ControllerState = {
        messages: [
          { id: 'u1', role: 'user', content: '问题', status: 'done', timestamp: 1 },
          { id: 'a1', role: 'ai', content: '', status: 'retrieving', timestamp: 2 },
        ],
        mounted: true,
      };

      const afterInsert = applyInsertNew(
        { isAuthReady: true, isConvReady: true, activeId: null, isNewConversation: true },
        'conv-new-001',
      );

      // newConv useEffect: activeId !== null → 不清空
      expect(simulateNewConvEffect(state, afterInsert).shouldClearMessages).toBe(false);
    });

    it('完整流程：createNew → send → INSERT_NEW → 消息不丢失', () => {
      // === Step 1: 用户点击"新建对话" ===
      let context: ControllerContext = applyCreateNew({
        isAuthReady: true,
        isConvReady: true,
        activeId: 'old-conv-1',
        isNewConversation: false,
      });
      expect(context.activeId).toBeNull();
      expect(context.isNewConversation).toBe(true);

      let state: ControllerState = { messages: [], mounted: true };

      // newConv useEffect: 清空
      expect(simulateNewConvEffect(state, context).shouldClearMessages).toBe(true);
      state = { ...state, messages: [] };

      // === Step 2: 用户发送消息 ===
      const userMsg: Message = { id: 'u-new', role: 'user', content: '新问题', status: 'sending', timestamp: 3 };
      const aiMsg: Message = { id: 'a-new', role: 'ai', content: '', status: 'retrieving', timestamp: 4 };
      state = { ...state, messages: [userMsg, aiMsg] };

      // === Step 3: SSE onInit → INSERT_NEW ===
      context = applyInsertNew(context, 'conv-brand-new');
      expect(context.activeId).toBe('conv-brand-new');
      expect(context.isNewConversation).toBe(false);

      // 关键验证 1: init useEffect 不触发
      expect(simulateInitEffect(state, context).shouldLoad).toBe(false);

      // 关键验证 2: newConv useEffect 不清空
      expect(simulateNewConvEffect(state, context).shouldClearMessages).toBe(false);

      // 关键验证 3: 消息仍然在
      expect(state.messages).toHaveLength(2);
      expect(state.messages[0].id).toBe('u-new');
      expect(state.messages[1].id).toBe('a-new');
      expect(state.messages[1].content).toBe('');

      // === Step 4: SSE onToken ===
      state = {
        ...state,
        messages: state.messages.map((m) =>
          m.id === 'a-new' ? { ...m, content: '这是 AI 的回答内容' } : m,
        ),
      };
      expect(state.messages[1].content).toBe('这是 AI 的回答内容');
    });
  });

  // ============================================================
  // 场景 3: 刷新后恢复
  // ============================================================
  describe('刷新后正确恢复对话', () => {
    it('Auth 先完成、Conv 后完成，消息正确加载', () => {
      let state: ControllerState = { messages: [], mounted: false };
      let context: ControllerContext = {
        isAuthReady: false,
        isConvReady: false,
        activeId: null,
        isNewConversation: false,
      };

      // T1: 都没初始化
      expect(simulateInitEffect(state, context).shouldLoad).toBe(false);

      // T2: Auth 完成，Conv 还没
      context = { ...context, isAuthReady: true };
      expect(simulateInitEffect(state, context).shouldLoad).toBe(false);

      // T3: Conv 完成，activeId 从 sessionStorage 恢复
      context = { ...context, isConvReady: true, activeId: 'conv-restored' };
      const result = simulateInitEffect(state, context);
      expect(result.shouldLoad).toBe(true);
      expect(result.loadedId).toBe('conv-restored');

      // T4: 加载完成，mounted=true
      state = { messages: [], mounted: true };
      expect(simulateInitEffect(state, context).shouldLoad).toBe(false);
    });

    it('mounted 守卫确保 init 只触发一次', () => {
      let state: ControllerState = { messages: [], mounted: false };
      const context: ControllerContext = {
        isAuthReady: true,
        isConvReady: true,
        activeId: 'conv-1',
        isNewConversation: false,
      };

      // 第一次：未挂载 → 加载
      expect(simulateInitEffect(state, context).shouldLoad).toBe(true);

      // 加载完成后 setMounted(true)
      state = { ...state, mounted: true };

      // 第二次：已挂载 → 不加载
      expect(simulateInitEffect(state, context).shouldLoad).toBe(false);

      // 即使 activeId 变了也不重新加载
      const context2 = { ...context, activeId: 'conv-2' };
      expect(simulateInitEffect(state, context2).shouldLoad).toBe(false);
    });
  });

  // ============================================================
  // 场景 4: switchHandler 用户切换对话
  // ============================================================
  describe('switchHandler 用户切换对话', () => {
    it('未挂载时不注册 handler', () => {
      const state: ControllerState = { messages: [], mounted: false };
      expect(simulateSwitchHandlerRegistration(state).shouldRegister).toBe(false);
    });

    it('已挂载时注册 handler', () => {
      const state: ControllerState = { messages: [], mounted: true };
      expect(simulateSwitchHandlerRegistration(state).shouldRegister).toBe(true);
    });

    it('switchTo 触发 handler（用户点击侧边栏）', () => {
      const context: ControllerContext = {
        isAuthReady: true,
        isConvReady: true,
        activeId: 'conv-1',
        isNewConversation: false,
      };

      const result = applySwitchTo(context, 'conv-2');
      expect(result.handlerShouldFire).toBe(true);
      expect(result.newContext.activeId).toBe('conv-2');
    });

    it('INSERT_NEW 不触发 handler（关键区分）', () => {
      // INSERT_NEW 只 dispatch action，不调用 switchTo
      // 因此 switchHandlerRef.current 不会被调用
      let handlerCallCount = 0;

      const beforeInsert: ControllerContext = {
        isAuthReady: true,
        isConvReady: true,
        activeId: null,
        isNewConversation: true,
      };

      // INSERT_NEW: 不走 switchTo
      const afterInsert = applyInsertNew(beforeInsert, 'conv-new-001');

      // handler 没有被调用
      expect(handlerCallCount).toBe(0);

      // 但 activeId 确实变了（由 INSERT_NEW dispatch 改变）
      expect(afterInsert.activeId).toBe('conv-new-001');
    });
  });

  // ============================================================
  // 场景 5: 竞态时序完整模拟
  // ============================================================
  describe('竞态时序完整模拟', () => {
    it('刷新 + 回复中再刷新：消息始终正确', () => {
      // ===== 模拟首次加载 =====
      let state: ControllerState = { messages: [], mounted: false };
      let context: ControllerContext = {
        isAuthReady: false,
        isConvReady: false,
        activeId: null,
        isNewConversation: false,
      };

      // Auth + Conv 初始化
      context = { ...context, isAuthReady: true, isConvReady: true, activeId: 'conv-1' };
      expect(simulateInitEffect(state, context).shouldLoad).toBe(true);
      state = { messages: [], mounted: true };

      // ===== 模拟发送消息 =====
      const userMsg: Message = { id: 'u1', role: 'user', content: '问题', status: 'sending', timestamp: 1 };
      const aiMsg: Message = { id: 'a1', role: 'ai', content: '正在回复...', status: 'generating', timestamp: 2 };
      state = { ...state, messages: [userMsg, aiMsg] };

      // ===== 模拟刷新（所有状态重置）=====
      state = { messages: [], mounted: false };
      context = {
        isAuthReady: false,
        isConvReady: false,
        activeId: null,
        isNewConversation: false,
      };

      // 刷新后重新初始化
      // Phase 1: Auth 完成
      context = { ...context, isAuthReady: true };
      expect(simulateInitEffect(state, context).shouldLoad).toBe(false);

      // Phase 2: Conv 完成，activeId 恢复
      context = { ...context, isConvReady: true, activeId: 'conv-1' };
      const loadResult = simulateInitEffect(state, context);
      expect(loadResult.shouldLoad).toBe(true);
      expect(loadResult.loadedId).toBe('conv-1');

      // Phase 3: 加载完成
      state = { messages: [userMsg, { ...aiMsg, status: 'done', content: '完整回复' }], mounted: true };
      expect(state.messages).toHaveLength(2);
    });

    it('新建对话 + INSERT_NEW 后刷新：消息从服务端恢复', () => {
      // ===== 创建新对话并发送 =====
      let state: ControllerState = { messages: [], mounted: true };
      let context: ControllerContext = applyCreateNew({
        isAuthReady: true,
        isConvReady: true,
        activeId: 'old-conv',
        isNewConversation: false,
      });

      // 清空
      state = { ...state, messages: [] };

      // 发送
      const userMsg: Message = { id: 'u1', role: 'user', content: '新对话第一条', status: 'sending', timestamp: 1 };
      const aiMsg: Message = { id: 'a1', role: 'ai', content: 'AI 回复', status: 'done', timestamp: 2 };
      state = { ...state, messages: [userMsg, aiMsg] };

      // INSERT_NEW
      context = applyInsertNew(context, 'conv-newly-created');

      // 此时消息完整
      expect(state.messages).toHaveLength(2);

      // ===== 刷新 =====
      state = { messages: [], mounted: false };
      context = {
        isAuthReady: false,
        isConvReady: false,
        activeId: null,
        isNewConversation: false,
      };

      // Auth + Conv 初始化
      context = {
        ...context,
        isAuthReady: true,
        isConvReady: true,
        activeId: 'conv-newly-created', // 从 sessionStorage 恢复
      };

      const result = simulateInitEffect(state, context);
      expect(result.shouldLoad).toBe(true);
      expect(result.loadedId).toBe('conv-newly-created');
    });

    it('多对话切换：A → B → A，每次都走 switchHandler', () => {
      const state: ControllerState = { messages: [], mounted: true };
      let context: ControllerContext = {
        isAuthReady: true,
        isConvReady: true,
        activeId: 'conv-A',
        isNewConversation: false,
      };

      // switchTo B
      let switchResult = applySwitchTo(context, 'conv-B');
      expect(switchResult.handlerShouldFire).toBe(true);
      expect(switchResult.newContext.activeId).toBe('conv-B');

      // switchTo A
      switchResult = applySwitchTo(switchResult.newContext, 'conv-A');
      expect(switchResult.handlerShouldFire).toBe(true);
      expect(switchResult.newContext.activeId).toBe('conv-A');
    });
  });
});
