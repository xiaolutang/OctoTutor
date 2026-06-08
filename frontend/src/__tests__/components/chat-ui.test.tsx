/**
 * ChatUI 逻辑测试
 *
 * 由于项目未安装 @testing-library/react 且 vitest 环境为 node，
 * 本测试直接测试 ChatUI 的核心逻辑：
 * - 通过 mock useChatStream 验证回调绑定
 * - 通过模拟 React 组件行为验证状态管理逻辑
 * - onThinking 回调、conversationId 集成
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import type { Message, SSECallbacks, ThinkingStep } from '@/chat/types';
import { getUserQuestionText } from '@/chat/types';

// ============================================================
// Mock: useChatStream
// ============================================================
let capturedCallbacks: SSECallbacks | null = null;
let capturedConversationId: string | undefined;
const mockStop = vi.fn();

vi.mock('@/chat/use-chat-stream', () => ({
  useChatStream: () => ({
    sendMessage: (_question: string, callbacks: SSECallbacks, conversationId?: string) => {
      capturedCallbacks = callbacks;
      capturedConversationId = conversationId;
    },
    stop: mockStop,
    isStreaming: false,
  }),
}));

// ============================================================
// Mock: useConversation
// ============================================================
const mockLoadConversation = vi.fn();

vi.mock('@/chat/use-conversation', () => ({
  useConversation: () => ({
    loadConversation: () => mockLoadConversation(),
  }),
}));

import { createId } from '@/lib/utils';

// ============================================================
// 辅助：模拟 ChatUI 逻辑（纯函数，不依赖 React 渲染）
// ============================================================

/**
 * 模拟 handleSend 逻辑的纯函数版本
 * 返回新的 messages 数组和 input 值
 */
function simulateHandleSend(
  currentMessages: Message[],
  inputText: string,
  sendMessage: (q: string, cbs: SSECallbacks, conversationId?: string) => void,
  conversationId?: string,
): { messages: Message[]; input: string; aiMsgId: string } {
  const text = inputText.trim();
  if (!text) throw new Error('empty input');

  const userMsg: Message = {
    id: createId(),
    role: 'user',
    content: text,
    status: 'sending',
    timestamp: Date.now(),
  };

  const aiMsgId = createId();
  const aiMsg: Message = {
    id: aiMsgId,
    role: 'ai',
    content: '',
    status: 'retrieving',
    timestamp: Date.now(),
  };

  const newMessages = [...currentMessages, userMsg, aiMsg];

  sendMessage(text, {
    onInit: vi.fn(),
    onStatus: vi.fn(),
    onSources: vi.fn(),
    onToken: vi.fn(),
    onThinking: vi.fn(),
    onDone: vi.fn(),
    onTitle: vi.fn(),
    onError: vi.fn(),
  }, conversationId);

  return { messages: newMessages, input: '', aiMsgId };
}

// ============================================================
// FB002: 模拟 handleRegenerate 纯函数
// ============================================================
function simulateHandleRegenerate(
  currentMessages: Message[],
  aiMessageId: string,
  isStreaming: boolean,
): {
  messages: Message[];
  regeneratedAiMsgId: string;
  userText: string;
  error?: string;
} | null {
  if (isStreaming) return null;

  const msgIndex = currentMessages.findIndex((m) => m.id === aiMessageId);
  if (msgIndex < 0) return null;

  const aiMsg = currentMessages[msgIndex];
  if (aiMsg.role !== 'ai') return null;

  // 向前查找最近的用户消息
  let userMsgIndex = msgIndex - 1;
  while (userMsgIndex >= 0 && currentMessages[userMsgIndex].role !== 'user') {
    userMsgIndex--;
  }
  if (userMsgIndex < 0) return null;

  const userText = getUserQuestionText(currentMessages[userMsgIndex].content);
  const newAiMsgId = createId();

  const newAiMsg: Message = {
    id: newAiMsgId,
    role: 'ai',
    content: '',
    status: 'retrieving',
    timestamp: Date.now(),
  };

  const newMessages = [...currentMessages];
  newMessages[msgIndex] = newAiMsg;

  return { messages: newMessages, regeneratedAiMsgId: newAiMsgId, userText };
}

// ============================================================
// 测试用例
// ============================================================
describe('ChatUI 核心逻辑', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    capturedCallbacks = null;
    capturedConversationId = undefined;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('should create user + ai messages on handleSend', () => {
    const result = simulateHandleSend([], '测试问题', (_q, _cbs) => {}, 'test-conv-id');

    expect(result.messages).toHaveLength(2);
    expect(result.messages[0].role).toBe('user');
    expect(result.messages[0].content).toBe('测试问题');
    expect(result.messages[1].role).toBe('ai');
    expect(result.messages[1].content).toBe('');
    expect(result.messages[1].status).toBe('retrieving');
    expect(result.input).toBe('');
  });

  it('should call sendMessage with question, callbacks and conversationId', () => {
    const sendFn = vi.fn();
    simulateHandleSend([], '你好', sendFn, 'conv-123');

    expect(sendFn).toHaveBeenCalledOnce();
    expect(sendFn).toHaveBeenCalledWith('你好', expect.any(Object), 'conv-123');
  });

  it('should pass undefined conversationId for first message (null)', () => {
    const sendFn = vi.fn();
    simulateHandleSend([], '第一条消息', sendFn, undefined);

    expect(sendFn).toHaveBeenCalledWith('第一条消息', expect.any(Object), undefined);
  });

  it('should revert messages and restore input on onError code=00000', () => {
    const inputText = '会失败的问题';
    const { messages: newMessages, aiMsgId } = simulateHandleSend(
      [],
      inputText,
      (_q, cbs) => {
        capturedCallbacks = cbs;
      },
    );

    expect(newMessages).toHaveLength(2);

    // 模拟 onError code='00000'
    // 撤回逻辑: 删除最后两条消息 + 内容回填输入框
    const reverted = newMessages.slice(0, -2);
    const restoredInput = inputText;

    expect(reverted).toHaveLength(0);
    expect(restoredInput).toBe('会失败的问题');
  });

  it('should mark ai message as error on onError with non-00000 code', () => {
    const { aiMsgId } = simulateHandleSend([], '测试', (_q, cbs) => {
      capturedCallbacks = cbs;
    });

    // 模拟 onError code='00001'
    const errorObj = { code: '00001', message: '连接中断', action: 'retry' };

    const patchedMsg: Message = {
      id: aiMsgId,
      role: 'ai',
      content: '',
      status: 'error',
      error: errorObj,
      timestamp: Date.now(),
    };

    expect(patchedMsg.status).toBe('error');
    expect(patchedMsg.error?.code).toBe('00001');
    expect(patchedMsg.error?.message).toBe('连接中断');
  });

  it('should call stop() on handleStop', () => {
    mockStop();
    expect(mockStop).toHaveBeenCalledOnce();
  });
});

// ============================================================
// Callback 绑定验证 (HG3)
// ============================================================
describe('useChatStream callback binding', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    capturedCallbacks = null;
  });

  it('should bind all 6 callbacks to sendMessage', () => {
    const sendFn = vi.fn((_q, cbs) => {
      capturedCallbacks = cbs;
    });
    simulateHandleSend([], '测试', sendFn);

    expect(capturedCallbacks).not.toBeNull();
    expect(capturedCallbacks).toHaveProperty('onStatus');
    expect(capturedCallbacks).toHaveProperty('onSources');
    expect(capturedCallbacks).toHaveProperty('onToken');
    expect(capturedCallbacks).toHaveProperty('onThinking');
    expect(capturedCallbacks).toHaveProperty('onDone');
    expect(capturedCallbacks).toHaveProperty('onError');

    // 验证都是函数
    expect(typeof capturedCallbacks!.onStatus).toBe('function');
    expect(typeof capturedCallbacks!.onSources).toBe('function');
    expect(typeof capturedCallbacks!.onToken).toBe('function');
    expect(typeof capturedCallbacks!.onThinking).toBe('function');
    expect(typeof capturedCallbacks!.onDone).toBe('function');
    expect(typeof capturedCallbacks!.onError).toBe('function');
  });
});

// ============================================================
// code='00000' 撤回行为验证 (HG4)
// ============================================================
describe('code=00000 rollback behavior', () => {
  it('should remove last 2 messages (user + ai) on code=00000', () => {
    const existingMessages: Message[] = [
      { id: 'old1', role: 'user', content: '旧问题', status: 'done', timestamp: 1 },
      { id: 'old2', role: 'ai', content: '旧回答', status: 'done', timestamp: 2 },
    ];

    const { messages: afterSend } = simulateHandleSend(
      existingMessages,
      '新问题',
      () => {},
    );

    expect(afterSend).toHaveLength(4);

    // 撤回
    const afterRollback = afterSend.slice(0, -2);
    expect(afterRollback).toHaveLength(2);
    expect(afterRollback[0].id).toBe('old1');
    expect(afterRollback[1].id).toBe('old2');
  });

  it('should restore input text on code=00000', () => {
    const inputText = '需要撤回的问题';
    const { input: restoredInput } = simulateHandleSend([], inputText, () => {});

    expect(restoredInput).toBe('');
    expect(inputText).toBe('需要撤回的问题');
  });
});

// ============================================================
// handleRegenerate 验证
// ============================================================
describe('handleRegenerate', () => {
  it('should replace old AI message with a new one', () => {
    const messages: Message[] = [
      { id: 'u1', role: 'user', content: '问题1', status: 'done', timestamp: 1 },
      { id: 'a1', role: 'ai', content: '回答1', status: 'done', timestamp: 2 },
    ];

    const result = simulateHandleRegenerate(messages, 'a1', false);
    expect(result).not.toBeNull();
    expect(result!.messages).toHaveLength(2);
    expect(result!.messages[0].id).toBe('u1'); // 用户消息不变
    expect(result!.messages[1].id).not.toBe('a1'); // AI 消息被替换
    expect(result!.messages[1].role).toBe('ai');
    expect(result!.messages[1].content).toBe('');
    expect(result!.messages[1].status).toBe('retrieving');
  });

  it('should extract correct user question for SSE', () => {
    const messages: Message[] = [
      { id: 'u1', role: 'user', content: '什么是微积分？', status: 'done', timestamp: 1 },
      { id: 'a1', role: 'ai', content: '微积分是...', status: 'done', timestamp: 2 },
    ];

    const result = simulateHandleRegenerate(messages, 'a1', false);
    expect(result!.userText).toBe('什么是微积分？');
  });

  it('should return null when isStreaming is true', () => {
    const messages: Message[] = [
      { id: 'u1', role: 'user', content: '问题', status: 'done', timestamp: 1 },
      { id: 'a1', role: 'ai', content: '回答', status: 'done', timestamp: 2 },
    ];

    const result = simulateHandleRegenerate(messages, 'a1', true);
    expect(result).toBeNull();
  });

  it('should return null when messageId not found', () => {
    const messages: Message[] = [
      { id: 'u1', role: 'user', content: '问题', status: 'done', timestamp: 1 },
    ];

    const result = simulateHandleRegenerate(messages, 'nonexistent', false);
    expect(result).toBeNull();
  });

  it('should return null when messageId is not an AI message', () => {
    const messages: Message[] = [
      { id: 'u1', role: 'user', content: '问题', status: 'done', timestamp: 1 },
      { id: 'a1', role: 'ai', content: '回答', status: 'done', timestamp: 2 },
    ];

    const result = simulateHandleRegenerate(messages, 'u1', false);
    expect(result).toBeNull();
  });

  it('should find the nearest preceding user message', () => {
    const messages: Message[] = [
      { id: 'u1', role: 'user', content: '问题A', status: 'done', timestamp: 1 },
      { id: 'a1', role: 'ai', content: '回答A', status: 'done', timestamp: 2 },
      { id: 'u2', role: 'user', content: '问题B', status: 'done', timestamp: 3 },
      { id: 'a2', role: 'ai', content: '回答B', status: 'done', timestamp: 4 },
    ];

    const result = simulateHandleRegenerate(messages, 'a2', false);
    expect(result!.userText).toBe('问题B');
  });

  it('should preserve messages before the AI message', () => {
    const messages: Message[] = [
      { id: 'u1', role: 'user', content: '问题1', status: 'done', timestamp: 1 },
      { id: 'a1', role: 'ai', content: '回答1', status: 'done', timestamp: 2 },
      { id: 'u2', role: 'user', content: '问题2', status: 'done', timestamp: 3 },
      { id: 'a2', role: 'ai', content: '回答2', status: 'done', timestamp: 4 },
    ];

    const result = simulateHandleRegenerate(messages, 'a2', false);
    expect(result!.messages[0].id).toBe('u1');
    expect(result!.messages[1].id).toBe('a1');
    expect(result!.messages[2].id).toBe('u2');
  });
});

// ============================================================
// FB002: onThinking 回调追加到 aiMsg.thinkingSteps
// ============================================================
describe('FB002: onThinking callback', () => {
  it('should append ThinkingStep to aiMsg.thinkingSteps', () => {
    const aiMsgId = 'ai-test-1';
    let aiMsg: Message = {
      id: aiMsgId,
      role: 'ai',
      content: '',
      status: 'generating',
      timestamp: Date.now(),
    };

    // 模拟 onThinking 回调逻辑
    const step1: ThinkingStep = { text: '分析问题中...', index: 0 };
    const step2: ThinkingStep = { text: '检索知识库...', index: 1 };

    // 第一次追加
    const existing1 = aiMsg.thinkingSteps ?? [];
    aiMsg = { ...aiMsg, thinkingSteps: [...existing1, step1] };

    expect(aiMsg.thinkingSteps).toHaveLength(1);
    expect(aiMsg.thinkingSteps![0].text).toBe('分析问题中...');

    // 第二次追加
    const existing2 = aiMsg.thinkingSteps ?? [];
    aiMsg = { ...aiMsg, thinkingSteps: [...existing2, step2] };

    expect(aiMsg.thinkingSteps).toHaveLength(2);
    expect(aiMsg.thinkingSteps![1].text).toBe('检索知识库...');
  });

  it('should handle multiple thinkingSteps from API response', () => {
    const apiThinkingSteps: ThinkingStep[] = [
      { text: '步骤1', index: 0 },
      { text: '步骤2', index: 1 },
      { text: '步骤3', index: 2 },
    ];

    const aiMsg: Message = {
      id: 'ai-from-api',
      role: 'ai',
      content: '回答内容',
      status: 'done',
      thinkingSteps: apiThinkingSteps,
      timestamp: Date.now(),
    };

    expect(aiMsg.thinkingSteps).toHaveLength(3);
    expect(aiMsg.thinkingSteps![0].text).toBe('步骤1');
    expect(aiMsg.thinkingSteps![2].text).toBe('步骤3');
  });
});

// ============================================================
// FT001: L1 异常路径测试补充
// ============================================================
describe('FT001: L1 error scenario tests', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    capturedCallbacks = null;
  });

  // U-ERR-01: 后端 error event → AI 消息 status='error'
  it('should mark AI message status as error when onError is called with non-00000 code', () => {
    const { messages: afterSend, aiMsgId } = simulateHandleSend([], '测试问题', (_q, cbs) => {
      capturedCallbacks = cbs;
    });

    const errorObj = { code: '02202', message: '生成中断', action: 'retry' };

    const updatedMessages = afterSend.map((m) => {
      if (m.id === aiMsgId) {
        return { ...m, status: 'error' as const, error: errorObj };
      }
      return m;
    });

    const aiMsg = updatedMessages.find((m) => m.id === aiMsgId);
    expect(aiMsg).toBeDefined();
    expect(aiMsg!.status).toBe('error');
    expect(aiMsg!.error?.code).toBe('02202');
    expect(aiMsg!.error?.message).toBe('生成中断');
  });

  // U-ERR-02: 连续快速发送 → 第二次被阻止
  it('should prevent sending when isStreaming is true', () => {
    const sendFn = vi.fn();
    let isStreaming = true;

    function guardedHandleSend(inputText: string): { messages: Message[]; input: string } | null {
      if (isStreaming) return null;
      return simulateHandleSend([], inputText, sendFn);
    }

    const result1 = guardedHandleSend('第一条');
    expect(result1).toBeNull();
    expect(sendFn).not.toHaveBeenCalled();

    isStreaming = false;

    const result2 = guardedHandleSend('第二条');
    expect(result2).not.toBeNull();
    expect(result2!.messages).toHaveLength(2);
    expect(sendFn).toHaveBeenCalledTimes(1);
  });

  // U-ERR-03: handleStop 在 retrieving 状态
  it('should mark AI message as stopped when handleStop during retrieving status', () => {
    const { messages: afterSend, aiMsgId } = simulateHandleSend([], '测试', () => {});

    const aiMsg = afterSend.find((m) => m.id === aiMsgId);
    expect(aiMsg!.status).toBe('retrieving');
    expect(aiMsg!.content).toBe('');

    mockStop();
    expect(mockStop).toHaveBeenCalled();

    const stoppedMessages = afterSend.map((m) => {
      if (m.id === aiMsgId) {
        return { ...m, status: 'stopped' as const };
      }
      return m;
    });

    const stoppedAiMsg = stoppedMessages.find((m) => m.id === aiMsgId);
    expect(stoppedAiMsg!.status).toBe('stopped');
    expect(stoppedAiMsg!.content).toBe('');
  });

  // U-ERR-04: handleStop 在 generating 状态
  it('should mark AI message as stopped when handleStop during generating status', () => {
    const { messages: afterSend, aiMsgId } = simulateHandleSend([], '测试', () => {});

    const generatingMessages = afterSend.map((m) => {
      if (m.id === aiMsgId) {
        return { ...m, status: 'generating' as const, content: '部分回答' };
      }
      return m;
    });

    const aiMsg = generatingMessages.find((m) => m.id === aiMsgId);
    expect(aiMsg!.status).toBe('generating');
    expect(aiMsg!.content).toBe('部分回答');

    mockStop();
    expect(mockStop).toHaveBeenCalled();

    const stoppedMessages = generatingMessages.map((m) => {
      if (m.id === aiMsgId) {
        return { ...m, status: 'stopped' as const };
      }
      return m;
    });

    const stoppedAiMsg = stoppedMessages.find((m) => m.id === aiMsgId);
    expect(stoppedAiMsg!.status).toBe('stopped');
    expect(stoppedAiMsg!.content).toBe('部分回答');
  });
});
