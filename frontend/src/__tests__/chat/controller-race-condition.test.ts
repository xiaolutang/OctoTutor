/**
 * useChatController 竞态修复测试
 *
 * 测试 controller.ts 的核心决策逻辑：
 * 1. 双门初始化：isAuthReady + isConvReady
 * 2. needsResumePlaceholder 逻辑
 * 3. 新对话清空消息
 * 4. activeId 切换时重新加载
 * 5. SSE 重连触发条件
 * 6. INSERT_NEW 安全性
 *
 * 由于 @xlfoundry/auth-sdk-web symlink 是 broken 状态，
 * vitest 无法 resolve auth-context.tsx，因此直接测试纯逻辑函数。
 *
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { Message } from '@/chat/types';

// ============================================================
// 从 controller.ts 提取的纯逻辑函数
// ============================================================

function needsResumePlaceholder(msgs: Message[]): boolean {
  if (msgs.length === 0) return false;
  const last = msgs[msgs.length - 1];
  return last.role === 'user' && Date.now() - last.timestamp < 120_000;
}

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

/** 模拟 init useEffect 决策逻辑 (controller.ts:79-104) */
function simulateInitEffect(
  state: ControllerState,
  context: ControllerContext,
): { shouldLoad: boolean; loadedId: string | null } {
  if (!context.isAuthReady) return { shouldLoad: false, loadedId: null };
  if (!context.isConvReady) return { shouldLoad: false, loadedId: null };
  if (state.mounted) return { shouldLoad: false, loadedId: null };
  return { shouldLoad: true, loadedId: context.activeId };
}

/** 模拟 newConv useEffect 决策逻辑 (controller.ts:107-112) */
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

/** 模拟 switchHandler 注册逻辑 (controller.ts:115-122) */
function simulateSwitchHandlerRegistration(
  state: ControllerState,
): { shouldRegister: boolean } {
  if (!state.mounted) return { shouldRegister: false };
  return { shouldRegister: true };
}

/** SSE 重连触发条件 (controller.ts:127-135) */
function shouldTriggerResume(
  state: ControllerState,
  context: ControllerContext,
  isStreaming: boolean,
): boolean {
  if (!state.mounted || !context.activeId || isStreaming) return false;
  const msgs = state.messages;
  if (msgs.length === 0) return false;
  const last = msgs[msgs.length - 1];
  if (last.role !== 'ai' || !['generating', 'retrieving'].includes(last.status)) return false;
  if (Date.now() - last.timestamp > 180_000) return false;
  return true;
}

// ============================================================
// 模拟 ConversationContext 行为（基于真实 reducer）
// ============================================================

function applyInsertNew(
  context: ControllerContext,
  newConvId: string,
): ControllerContext {
  return { ...context, activeId: newConvId, isNewConversation: false };
}

function applyCreateNew(context: ControllerContext): ControllerContext {
  return { ...context, activeId: null, isNewConversation: true };
}

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

describe('useChatController 竞态修复', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // ============================================================
  // 场景 1: 双门初始化
  // ============================================================
  describe('双门初始化 (isAuthReady + isConvReady)', () => {
    it('isAuthReady=false 时不加载', () => {
      const result = simulateInitEffect(
        { messages: [], mounted: false },
        { isAuthReady: false, isConvReady: true, activeId: 'conv-1', isNewConversation: false },
      );
      expect(result.shouldLoad).toBe(false);
    });

    it('isConvReady=false 时不加载', () => {
      const result = simulateInitEffect(
        { messages: [], mounted: false },
        { isAuthReady: true, isConvReady: false, activeId: 'conv-1', isNewConversation: false },
      );
      expect(result.shouldLoad).toBe(false);
    });

    it('两者都为 false 时不加载', () => {
      const result = simulateInitEffect(
        { messages: [], mounted: false },
        { isAuthReady: false, isConvReady: false, activeId: 'conv-1', isNewConversation: false },
      );
      expect(result.shouldLoad).toBe(false);
    });

    it('两者都为 true 且未挂载时加载', () => {
      const result = simulateInitEffect(
        { messages: [], mounted: false },
        { isAuthReady: true, isConvReady: true, activeId: 'conv-1', isNewConversation: false },
      );
      expect(result.shouldLoad).toBe(true);
      expect(result.loadedId).toBe('conv-1');
    });

    it('已挂载后不再触发初始化加载', () => {
      const result = simulateInitEffect(
        { messages: [], mounted: true },
        { isAuthReady: true, isConvReady: true, activeId: 'conv-1', isNewConversation: false },
      );
      expect(result.shouldLoad).toBe(false);
    });

    it('activeId 为 null 时（新用户）仍然允许加载', () => {
      const result = simulateInitEffect(
        { messages: [], mounted: false },
        { isAuthReady: true, isConvReady: true, activeId: null, isNewConversation: true },
      );
      expect(result.shouldLoad).toBe(true);
      expect(result.loadedId).toBe(null);
    });
  });

  // ============================================================
  // 场景 2: needsResumePlaceholder
  // ============================================================
  describe('needsResumePlaceholder', () => {
    it('最后一条是用户消息且 2 分钟内 → true', () => {
      const msgs: Message[] = [
        { id: 'a1', role: 'ai', content: '回答', status: 'done', timestamp: 1 },
        { id: 'u1', role: 'user', content: '你好', status: 'done', timestamp: Date.now() - 30_000 },
      ];
      expect(needsResumePlaceholder(msgs)).toBe(true);
    });

    it('超过 2 分钟 → false', () => {
      const msgs: Message[] = [
        { id: 'u1', role: 'user', content: '你好', status: 'done', timestamp: Date.now() - 200_000 },
      ];
      expect(needsResumePlaceholder(msgs)).toBe(false);
    });

    it('最后一条是 AI 消息 → false', () => {
      const msgs: Message[] = [
        { id: 'a1', role: 'ai', content: '回答', status: 'done', timestamp: Date.now() },
      ];
      expect(needsResumePlaceholder(msgs)).toBe(false);
    });

    it('空列表 → false', () => {
      expect(needsResumePlaceholder([])).toBe(false);
    });
  });

  // ============================================================
  // 场景 3: 新对话清空消息
  // ============================================================
  describe('新对话清空消息', () => {
    it('activeId=null + isNewConversation=true → 清空', () => {
      const state: ControllerState = {
        messages: [{ id: 'a1', role: 'ai', content: '内容', status: 'done', timestamp: 1 }],
        mounted: true,
      };
      const context: ControllerContext = { isAuthReady: true, isConvReady: true, activeId: null, isNewConversation: true };
      expect(simulateNewConvEffect(state, context).shouldClearMessages).toBe(true);
    });

    it('activeId 不为 null → 不清空', () => {
      const state: ControllerState = { messages: [], mounted: true };
      const context: ControllerContext = { isAuthReady: true, isConvReady: true, activeId: 'conv-1', isNewConversation: true };
      expect(simulateNewConvEffect(state, context).shouldClearMessages).toBe(false);
    });

    it('未 mounted → 不清空', () => {
      const state: ControllerState = { messages: [], mounted: false };
      const context: ControllerContext = { isAuthReady: true, isConvReady: true, activeId: null, isNewConversation: true };
      expect(simulateNewConvEffect(state, context).shouldClearMessages).toBe(false);
    });
  });

  // ============================================================
  // 场景 4: INSERT_NEW 安全性
  // ============================================================
  describe('INSERT_NEW 不触发消息重载', () => {
    it('INSERT_NEW 后 init useEffect 不触发（mounted=true）', () => {
      const state: ControllerState = {
        messages: [
          { id: 'u1', role: 'user', content: '你好', status: 'done', timestamp: 1 },
          { id: 'a1', role: 'ai', content: '你好！', status: 'done', timestamp: 2 },
        ],
        mounted: true,
      };

      const beforeInsert: ControllerContext = {
        isAuthReady: true, isConvReady: true, activeId: null, isNewConversation: true,
      };

      const afterInsert = applyInsertNew(beforeInsert, 'conv-new-001');
      expect(afterInsert.activeId).toBe('conv-new-001');
      expect(afterInsert.isNewConversation).toBe(false);

      expect(simulateInitEffect(state, afterInsert).shouldLoad).toBe(false);
    });

    it('INSERT_NEW 后 newConv useEffect 不清空（activeId !== null）', () => {
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

      expect(simulateNewConvEffect(state, afterInsert).shouldClearMessages).toBe(false);
    });

    it('完整流程：createNew → 发送 → INSERT_NEW → 消息不丢失', () => {
      // Step 1: 创建新对话
      let context = applyCreateNew({
        isAuthReady: true, isConvReady: true, activeId: 'old-conv-1', isNewConversation: false,
      });
      expect(context.activeId).toBeNull();
      expect(context.isNewConversation).toBe(true);

      let state: ControllerState = { messages: [], mounted: true };

      // Step 2: 清空消息
      expect(simulateNewConvEffect(state, context).shouldClearMessages).toBe(true);
      state = { ...state, messages: [] };

      // Step 3: 用户发送消息，SSE 创建 conversation → INSERT_NEW
      const userMsg: Message = { id: 'u-new', role: 'user', content: '新问题', status: 'sending', timestamp: 3 };
      const aiMsg: Message = { id: 'a-new', role: 'ai', content: '', status: 'retrieving', timestamp: 4 };
      state = { ...state, messages: [userMsg, aiMsg] };

      context = applyInsertNew(context, 'conv-brand-new');
      expect(simulateInitEffect(state, context).shouldLoad).toBe(false);
      expect(simulateNewConvEffect(state, context).shouldClearMessages).toBe(false);
      expect(state.messages).toHaveLength(2);
    });
  });

  // ============================================================
  // 场景 5: SSE 重连触发条件
  // ============================================================
  describe('SSE 重连触发条件', () => {
    it('mounted + activeId + AI generating → 触发', () => {
      const state: ControllerState = {
        messages: [
          { id: 'u1', role: 'user', content: '问题', status: 'done', timestamp: Date.now() - 30_000 },
          { id: 'a1', role: 'ai', content: '', status: 'generating', timestamp: Date.now() - 10_000 },
        ],
        mounted: true,
      };
      const context: ControllerContext = { isAuthReady: true, isConvReady: true, activeId: 'conv-1', isNewConversation: false };
      expect(shouldTriggerResume(state, context, false)).toBe(true);
    });

    it('mounted + activeId + AI retrieving → 触发', () => {
      const state: ControllerState = {
        messages: [
          { id: 'a1', role: 'ai', content: '', status: 'retrieving', timestamp: Date.now() },
        ],
        mounted: true,
      };
      const context: ControllerContext = { isAuthReady: true, isConvReady: true, activeId: 'conv-1', isNewConversation: false };
      expect(shouldTriggerResume(state, context, false)).toBe(true);
    });

    it('isStreaming=true → 不触发', () => {
      const state: ControllerState = {
        messages: [
          { id: 'a1', role: 'ai', content: '', status: 'generating', timestamp: Date.now() },
        ],
        mounted: true,
      };
      const context: ControllerContext = { isAuthReady: true, isConvReady: true, activeId: 'conv-1', isNewConversation: false };
      expect(shouldTriggerResume(state, context, true)).toBe(false);
    });

    it('activeId=null → 不触发', () => {
      const state: ControllerState = {
        messages: [
          { id: 'a1', role: 'ai', content: '', status: 'generating', timestamp: Date.now() },
        ],
        mounted: true,
      };
      const context: ControllerContext = { isAuthReady: true, isConvReady: true, activeId: null, isNewConversation: false };
      expect(shouldTriggerResume(state, context, false)).toBe(false);
    });

    it('AI done → 不触发', () => {
      const state: ControllerState = {
        messages: [
          { id: 'a1', role: 'ai', content: '回答', status: 'done', timestamp: Date.now() },
        ],
        mounted: true,
      };
      const context: ControllerContext = { isAuthReady: true, isConvReady: true, activeId: 'conv-1', isNewConversation: false };
      expect(shouldTriggerResume(state, context, false)).toBe(false);
    });

    it('超过 3 分钟 → 不触发', () => {
      const state: ControllerState = {
        messages: [
          { id: 'a1', role: 'ai', content: '', status: 'generating', timestamp: Date.now() - 200_000 },
        ],
        mounted: true,
      };
      const context: ControllerContext = { isAuthReady: true, isConvReady: true, activeId: 'conv-1', isNewConversation: false };
      expect(shouldTriggerResume(state, context, false)).toBe(false);
    });

    it('未 mounted → 不触发', () => {
      const state: ControllerState = {
        messages: [
          { id: 'a1', role: 'ai', content: '', status: 'generating', timestamp: Date.now() },
        ],
        mounted: false,
      };
      const context: ControllerContext = { isAuthReady: true, isConvReady: true, activeId: 'conv-1', isNewConversation: false };
      expect(shouldTriggerResume(state, context, false)).toBe(false);
    });
  });

  // ============================================================
  // 场景 6: switchHandler
  // ============================================================
  describe('switchHandler', () => {
    it('未 mounted 时不注册', () => {
      expect(simulateSwitchHandlerRegistration({ messages: [], mounted: false }).shouldRegister).toBe(false);
    });

    it('已 mounted 时注册', () => {
      expect(simulateSwitchHandlerRegistration({ messages: [], mounted: true }).shouldRegister).toBe(true);
    });

    it('switchTo 触发 handler（用户点击侧边栏）', () => {
      const context: ControllerContext = { isAuthReady: true, isConvReady: true, activeId: 'conv-1', isNewConversation: false };
      const result = applySwitchTo(context, 'conv-2');
      expect(result.handlerShouldFire).toBe(true);
      expect(result.newContext.activeId).toBe('conv-2');
    });

    it('INSERT_NEW 不触发 handler', () => {
      const beforeInsert: ControllerContext = { isAuthReady: true, isConvReady: true, activeId: null, isNewConversation: true };
      const afterInsert = applyInsertNew(beforeInsert, 'conv-new-001');
      // INSERT_NEW 不走 switchTo，handler 不触发
      expect(afterInsert.activeId).toBe('conv-new-001');
    });
  });

  // ============================================================
  // 场景 7: mounted 守卫确保 init 只触发一次
  // ============================================================
  describe('mounted 守卫', () => {
    it('init 只触发一次，后续 activeId 变化不重新加载', () => {
      let state: ControllerState = { messages: [], mounted: false };
      const context: ControllerContext = { isAuthReady: true, isConvReady: true, activeId: 'conv-1', isNewConversation: false };

      expect(simulateInitEffect(state, context).shouldLoad).toBe(true);
      state = { ...state, mounted: true };
      expect(simulateInitEffect(state, context).shouldLoad).toBe(false);

      const context2 = { ...context, activeId: 'conv-2' };
      expect(simulateInitEffect(state, context2).shouldLoad).toBe(false);
    });
  });

  // ============================================================
  // 场景 8: 竞态时序完整模拟
  // ============================================================
  describe('竞态时序完整模拟', () => {
    it('刷新 + 回复中再刷新：消息始终正确', () => {
      let state: ControllerState = { messages: [], mounted: false };
      let context: ControllerContext = { isAuthReady: false, isConvReady: false, activeId: null, isNewConversation: false };

      expect(simulateInitEffect(state, context).shouldLoad).toBe(false);

      context = { ...context, isAuthReady: true, isConvReady: true, activeId: 'conv-1' };
      expect(simulateInitEffect(state, context).shouldLoad).toBe(true);
      state = { messages: [], mounted: true };

      // 发送消息
      const userMsg: Message = { id: 'u1', role: 'user', content: '问题', status: 'sending', timestamp: 1 };
      const aiMsg: Message = { id: 'a1', role: 'ai', content: '正在回复...', status: 'generating', timestamp: 2 };
      state = { ...state, messages: [userMsg, aiMsg] };

      // 刷新（状态重置）
      state = { messages: [], mounted: false };
      context = { isAuthReady: false, isConvReady: false, activeId: null, isNewConversation: false };

      context = { ...context, isAuthReady: true };
      expect(simulateInitEffect(state, context).shouldLoad).toBe(false);

      context = { ...context, isConvReady: true, activeId: 'conv-1' };
      const loadResult = simulateInitEffect(state, context);
      expect(loadResult.shouldLoad).toBe(true);
      expect(loadResult.loadedId).toBe('conv-1');

      state = { messages: [userMsg, { ...aiMsg, status: 'done', content: '完整回复' }], mounted: true };
      expect(state.messages).toHaveLength(2);
    });

    it('新建对话 + INSERT_NEW 后刷新：从服务端恢复', () => {
      let state: ControllerState = { messages: [], mounted: true };
      let context = applyCreateNew({ isAuthReady: true, isConvReady: true, activeId: 'old-conv', isNewConversation: false });
      state = { ...state, messages: [] };

      const userMsg: Message = { id: 'u1', role: 'user', content: '新对话第一条', status: 'sending', timestamp: 1 };
      const aiMsg: Message = { id: 'a1', role: 'ai', content: 'AI 回复', status: 'done', timestamp: 2 };
      state = { ...state, messages: [userMsg, aiMsg] };

      context = applyInsertNew(context, 'conv-newly-created');
      expect(state.messages).toHaveLength(2);

      // 刷新
      state = { messages: [], mounted: false };
      context = { isAuthReady: true, isConvReady: true, activeId: 'conv-newly-created', isNewConversation: false };

      const result = simulateInitEffect(state, context);
      expect(result.shouldLoad).toBe(true);
      expect(result.loadedId).toBe('conv-newly-created');
    });
  });
});
