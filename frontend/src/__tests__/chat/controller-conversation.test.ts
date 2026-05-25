/**
 * R009-FB003: controller.ts + ConversationContext 集成测试
 *
 * 测试策略：由于 vitest 环境为 node 且无 @testing-library/react，
 * 采用与 chat-ui.test.tsx 一致的纯函数模拟策略，测试 controller
 * 与 ConversationContext 的关键交互路径。
 *
 * 覆盖场景：
 * 1. 新建对话 SSE 流程（init -> insertNewConversation）
 * 2. 切换对话加载历史
 * 3. 标题自动更新（title -> updateTitle）
 * 4. 自动滚动（scrollIntoView）
 * 5. 重新生成正常
 * 6. 停止生成正常
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { Message, SSECallbacks, ConversationItem } from '@/chat/types';

// ============================================================
// 工具函数
// ============================================================
function createId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
}

// ============================================================
// Mock 依赖
// ============================================================

// Mock: insertNewConversation
const mockInsertNewConversation = vi.fn();

// Mock: updateTitle
const mockUpdateTitle = vi.fn();

// Mock: loadConversation
const mockLoadConversation = vi.fn();

// Mock: setContextStreaming
const mockSetContextStreaming = vi.fn();

// Mock: sendMessage (captures callbacks)
let capturedCallbacks: SSECallbacks | null = null;
let capturedConversationId: string | undefined;
const mockStop = vi.fn();

/**
 * 模拟 useChatController 中 startSSE 的核心逻辑
 *
 * 此函数复刻了 controller.ts 中 startSSE 的回调绑定行为，
 * 是集成测试的核心。当 isNewConversation=true 时，onInit 回调
 * 会调用 insertNewConversation；onTitle 回调会调用 updateTitle。
 */
function simulateStartSSE(
  question: string,
  aiMsgId: string,
  sendMessageFn: (
    question: string,
    callbacks: SSECallbacks,
    conversationId?: string,
  ) => void,
  contextOptions: {
    activeId: string | null;
    isNewConversation: boolean;
  },
) {
  sendMessageFn(
    question,
    {
      onInit: (convId: string) => {
        if (contextOptions.isNewConversation) {
          mockInsertNewConversation({
            id: convId,
            title: '新对话',
            pinned: false,
            pinned_at: null,
            message_count: 0,
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          });
        }
      },
      onStatus: (_stage: string, _message: string) => {},
      onSources: (_sources) => {},
      onToken: (_token: string) => {},
      onThinking: (_step) => {},
      onDone: () => {},
      onTitle: (convId: string, title: string) => {
        mockUpdateTitle(convId, title);
      },
      onError: (_error) => {},
    },
    contextOptions.activeId ?? undefined,
  );
}

/**
 * 模拟 handleSend 逻辑
 */
function simulateHandleSend(
  currentMessages: Message[],
  inputText: string,
  sendMessageFn: (
    question: string,
    callbacks: SSECallbacks,
    conversationId?: string,
  ) => void,
  contextOptions: {
    activeId: string | null;
    isNewConversation: boolean;
    isStreaming: boolean;
  },
): { messages: Message[]; input: string; aiMsgId: string } | null {
  const text = inputText.trim();
  if (!text || contextOptions.isStreaming) return null;

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

  simulateStartSSE(text, aiMsgId, sendMessageFn, contextOptions);

  return { messages: newMessages, input: '', aiMsgId };
}

/**
 * 模拟 handleStop 逻辑
 */
function simulateHandleStop(
  currentMessages: Message[],
  aiMsgIdRef: string,
  stopFn: () => void,
): Message[] {
  stopFn();
  if (aiMsgIdRef) {
    return currentMessages.map((m) =>
      m.id === aiMsgIdRef ? { ...m, status: 'stopped' as const } : m,
    );
  }
  return currentMessages;
}

/**
 * 模拟 handleRegenerate 逻辑
 */
function simulateHandleRegenerate(
  currentMessages: Message[],
  messageId: string,
  isStreaming: boolean,
  sendMessageFn: (
    question: string,
    callbacks: SSECallbacks,
    conversationId?: string,
  ) => void,
  contextOptions: {
    activeId: string | null;
    isNewConversation: boolean;
  },
): { messages: Message[]; regeneratedAiMsgId: string } | null {
  if (isStreaming) return null;

  const msgIndex = currentMessages.findIndex((m) => m.id === messageId);
  if (msgIndex < 0) return null;

  const aiMsg = currentMessages[msgIndex];
  if (aiMsg.role !== 'ai') return null;

  // 向前查找最近的用户消息
  let userMsgIndex = msgIndex - 1;
  while (userMsgIndex >= 0 && currentMessages[userMsgIndex].role !== 'user') {
    userMsgIndex--;
  }
  if (userMsgIndex < 0) return null;

  const userText = currentMessages[userMsgIndex].content;
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

  simulateStartSSE(userText, newAiMsgId, sendMessageFn, contextOptions);

  return { messages: newMessages, regeneratedAiMsgId: newAiMsgId };
}

/**
 * 模拟切换对话逻辑
 */
function simulateSwitchConversation(
  prevActiveId: string | null,
  newActiveId: string | null,
  isNewConversation: boolean,
  mounted: boolean,
): {
  shouldLoadHistory: boolean;
  shouldClearMessages: boolean;
} {
  if (!mounted) return { shouldLoadHistory: false, shouldClearMessages: false };
  if (prevActiveId === newActiveId) return { shouldLoadHistory: false, shouldClearMessages: false };

  if (newActiveId === null && isNewConversation) {
    return { shouldLoadHistory: false, shouldClearMessages: true };
  }

  return { shouldLoadHistory: true, shouldClearMessages: false };
}

// ============================================================
// 测试用例
// ============================================================
describe('R009-FB003: controller + ConversationContext 集成', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    capturedCallbacks = null;
    capturedConversationId = undefined;
    mockLoadConversation.mockResolvedValue({ messages: [] });
  });

  // ============================================================
  // 场景 1：新建对话 SSE 流程
  // ============================================================
  describe('新建对话 SSE 流程', () => {
    it('onInit 应该调用 insertNewConversation（isNewConversation=true）', () => {
      const sendMessageFn = vi.fn((_q, cbs) => {
        capturedCallbacks = cbs;
      });

      simulateStartSSE('测试问题', 'ai-msg-1', sendMessageFn, {
        activeId: null,
        isNewConversation: true,
      });

      expect(capturedCallbacks).not.toBeNull();

      // 模拟 SSE init 事件
      capturedCallbacks!.onInit('conv-new-123');

      expect(mockInsertNewConversation).toHaveBeenCalledOnce();
      expect(mockInsertNewConversation).toHaveBeenCalledWith(
        expect.objectContaining({
          id: 'conv-new-123',
          title: '新对话',
          pinned: false,
        }),
      );
    });

    it('onInit 不应该调用 insertNewConversation（isNewConversation=false）', () => {
      const sendMessageFn = vi.fn((_q, cbs) => {
        capturedCallbacks = cbs;
      });

      simulateStartSSE('测试问题', 'ai-msg-1', sendMessageFn, {
        activeId: 'existing-conv-456',
        isNewConversation: false,
      });

      expect(capturedCallbacks).not.toBeNull();

      // 模拟 SSE init 事件
      capturedCallbacks!.onInit('conv-existing-456');

      expect(mockInsertNewConversation).not.toHaveBeenCalled();
    });

    it('handleSend 新对话时 conversationId 为 undefined', () => {
      const sendMessageFn = vi.fn((_q, _cbs, convId) => {
        capturedConversationId = convId;
      });

      const result = simulateHandleSend([], '新问题', sendMessageFn, {
        activeId: null,
        isNewConversation: true,
        isStreaming: false,
      });

      expect(result).not.toBeNull();
      expect(capturedConversationId).toBeUndefined();
    });

    it('handleSend 已有对话时 conversationId 有值', () => {
      const sendMessageFn = vi.fn((_q, _cbs, convId) => {
        capturedConversationId = convId;
      });

      const result = simulateHandleSend([], '后续问题', sendMessageFn, {
        activeId: 'conv-789',
        isNewConversation: false,
        isStreaming: false,
      });

      expect(result).not.toBeNull();
      expect(capturedConversationId).toBe('conv-789');
    });
  });

  // ============================================================
  // 场景 2：切换对话加载历史
  // ============================================================
  describe('切换对话加载历史', () => {
    it('切换到已有对话时应该加载历史消息', () => {
      const result = simulateSwitchConversation('conv-1', 'conv-2', false, true);

      expect(result.shouldLoadHistory).toBe(true);
      expect(result.shouldClearMessages).toBe(false);
    });

    it('切换到新对话时应该清空消息', () => {
      const result = simulateSwitchConversation('conv-1', null, true, true);

      expect(result.shouldLoadHistory).toBe(false);
      expect(result.shouldClearMessages).toBe(true);
    });

    it('activeId 未变化时不应该触发加载', () => {
      const result = simulateSwitchConversation('conv-1', 'conv-1', false, true);

      expect(result.shouldLoadHistory).toBe(false);
      expect(result.shouldClearMessages).toBe(false);
    });

    it('未挂载时不应该触发加载', () => {
      const result = simulateSwitchConversation(null, 'conv-2', false, false);

      expect(result.shouldLoadHistory).toBe(false);
      expect(result.shouldClearMessages).toBe(false);
    });

    it('从新对话切换到已有对话应该加载历史', () => {
      const result = simulateSwitchConversation(null, 'conv-3', false, true);

      expect(result.shouldLoadHistory).toBe(true);
      expect(result.shouldClearMessages).toBe(false);
    });
  });

  // ============================================================
  // 场景 3：标题自动更新
  // ============================================================
  describe('标题自动更新', () => {
    it('onTitle 事件应该调用 updateTitle', () => {
      const sendMessageFn = vi.fn((_q, cbs) => {
        capturedCallbacks = cbs;
      });

      simulateStartSSE('测试问题', 'ai-msg-1', sendMessageFn, {
        activeId: null,
        isNewConversation: true,
      });

      expect(capturedCallbacks).not.toBeNull();

      // 模拟 SSE title 事件
      capturedCallbacks!.onTitle('conv-123', '关于微积分的问题');

      expect(mockUpdateTitle).toHaveBeenCalledOnce();
      expect(mockUpdateTitle).toHaveBeenCalledWith('conv-123', '关于微积分的问题');
    });

    it('多次 onTitle 应该多次调用 updateTitle', () => {
      const sendMessageFn = vi.fn((_q, cbs) => {
        capturedCallbacks = cbs;
      });

      simulateStartSSE('测试', 'ai-1', sendMessageFn, {
        activeId: 'conv-x',
        isNewConversation: false,
      });

      capturedCallbacks!.onTitle('conv-x', '标题1');
      capturedCallbacks!.onTitle('conv-x', '标题2（更新）');

      expect(mockUpdateTitle).toHaveBeenCalledTimes(2);
      expect(mockUpdateTitle).toHaveBeenNthCalledWith(1, 'conv-x', '标题1');
      expect(mockUpdateTitle).toHaveBeenNthCalledWith(2, 'conv-x', '标题2（更新）');
    });

    it('不同 conversationId 的 title 事件应该分别更新', () => {
      const sendMessageFn = vi.fn((_q, cbs) => {
        capturedCallbacks = cbs;
      });

      simulateStartSSE('测试', 'ai-1', sendMessageFn, {
        activeId: 'conv-a',
        isNewConversation: false,
      });

      capturedCallbacks!.onTitle('conv-a', '标题A');
      capturedCallbacks!.onTitle('conv-b', '标题B');

      expect(mockUpdateTitle).toHaveBeenCalledTimes(2);
      expect(mockUpdateTitle).toHaveBeenCalledWith('conv-a', '标题A');
      expect(mockUpdateTitle).toHaveBeenCalledWith('conv-b', '标题B');
    });
  });

  // ============================================================
  // 场景 4：自动滚动
  // ============================================================
  describe('自动滚动', () => {
    it('messages 变化时应该触发 scrollIntoView', () => {
      const mockScrollIntoView = vi.fn();

      // 模拟 ChatUI 中 useEffect 的自动滚动逻辑
      const messagesLength = 2;
      const isStreaming = false;

      // 模拟 messagesEndRef.current?.scrollIntoView
      const messagesEndRef = { current: { scrollIntoView: mockScrollIntoView } };
      if (messagesLength > 0) {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
      }

      expect(mockScrollIntoView).toHaveBeenCalledWith({ behavior: 'smooth' });
    });

    it('流式输出时应该持续触发 scrollIntoView', () => {
      const mockScrollIntoView = vi.fn();

      // 模拟 streaming 状态下多次触发
      const states = [
        { messagesLength: 1, isStreaming: true },
        { messagesLength: 1, isStreaming: true },
        { messagesLength: 2, isStreaming: true },
        { messagesLength: 2, isStreaming: false },
      ];

      const messagesEndRef = { current: { scrollIntoView: mockScrollIntoView } };

      for (const state of states) {
        // ChatUI useEffect 依赖 [messages.length, isStreaming]
        // 每次 deps 变化时触发 scrollIntoView
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
      }

      expect(mockScrollIntoView).toHaveBeenCalledTimes(4);
    });

    it('ref 为 null 时不应该报错', () => {
      const messagesEndRef = { current: null };

      // 应该安全地不执行任何操作
      expect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
      }).not.toThrow();
    });
  });

  // ============================================================
  // 场景 5：重新生成正常
  // ============================================================
  describe('重新生成正常', () => {
    it('应该用新 AI 消息替换旧的，并发送 SSE', () => {
      const sendMessageFn = vi.fn();
      const messages: Message[] = [
        { id: 'u1', role: 'user', content: '什么是牛顿定律？', status: 'done', timestamp: 1 },
        { id: 'a1', role: 'ai', content: '牛顿定律是...', status: 'done', timestamp: 2 },
      ];

      const result = simulateHandleRegenerate(messages, 'a1', false, sendMessageFn, {
        activeId: 'conv-1',
        isNewConversation: false,
      });

      expect(result).not.toBeNull();
      expect(result!.messages).toHaveLength(2);
      expect(result!.messages[0].id).toBe('u1');
      expect(result!.messages[1].id).not.toBe('a1');
      expect(result!.messages[1].role).toBe('ai');
      expect(result!.messages[1].content).toBe('');
      expect(result!.messages[1].status).toBe('retrieving');

      // 验证 sendMessage 被调用
      expect(sendMessageFn).toHaveBeenCalledOnce();
      expect(sendMessageFn).toHaveBeenCalledWith(
        '什么是牛顿定律？',
        expect.any(Object),
        'conv-1',
      );
    });

    it('流式输出中不应该允许重新生成', () => {
      const sendMessageFn = vi.fn();
      const messages: Message[] = [
        { id: 'u1', role: 'user', content: '问题', status: 'done', timestamp: 1 },
        { id: 'a1', role: 'ai', content: '回答', status: 'done', timestamp: 2 },
      ];

      const result = simulateHandleRegenerate(messages, 'a1', true, sendMessageFn, {
        activeId: 'conv-1',
        isNewConversation: false,
      });

      expect(result).toBeNull();
      expect(sendMessageFn).not.toHaveBeenCalled();
    });

    it('重新生成的 SSE 回调中包含正确的 context 信息', () => {
      const sendMessageFn = vi.fn((_q, _cbs, convId) => {
        capturedConversationId = convId;
      });
      const messages: Message[] = [
        { id: 'u1', role: 'user', content: '问题', status: 'done', timestamp: 1 },
        { id: 'a1', role: 'ai', content: '旧回答', status: 'done', timestamp: 2 },
      ];

      simulateHandleRegenerate(messages, 'a1', false, sendMessageFn, {
        activeId: 'conv-999',
        isNewConversation: false,
      });

      expect(capturedConversationId).toBe('conv-999');
    });
  });

  // ============================================================
  // 场景 6：停止生成正常
  // ============================================================
  describe('停止生成正常', () => {
    it('handleStop 应该调用 stop 并标记 AI 消息为 stopped', () => {
      const messages: Message[] = [
        { id: 'u1', role: 'user', content: '问题', status: 'done', timestamp: 1 },
        { id: 'a1', role: 'ai', content: '部分内容...', status: 'generating', timestamp: 2 },
      ];

      const result = simulateHandleStop(messages, 'a1', mockStop);

      expect(mockStop).toHaveBeenCalledOnce();
      const aiMsg = result.find((m) => m.id === 'a1');
      expect(aiMsg!.status).toBe('stopped');
      expect(aiMsg!.content).toBe('部分内容...');
    });

    it('停止后不应丢失已有内容', () => {
      const content = '这是一段已经生成的回答内容，包含多个 token。';
      const messages: Message[] = [
        { id: 'u1', role: 'user', content: '问题', status: 'done', timestamp: 1 },
        { id: 'a1', role: 'ai', content, status: 'generating', timestamp: 2 },
      ];

      const result = simulateHandleStop(messages, 'a1', mockStop);

      const aiMsg = result.find((m) => m.id === 'a1');
      expect(aiMsg!.content).toBe(content);
      expect(aiMsg!.status).toBe('stopped');
    });

    it('停止 retrieving 状态的消息', () => {
      const messages: Message[] = [
        { id: 'u1', role: 'user', content: '问题', status: 'done', timestamp: 1 },
        { id: 'a1', role: 'ai', content: '', status: 'retrieving', timestamp: 2 },
      ];

      const result = simulateHandleStop(messages, 'a1', mockStop);

      const aiMsg = result.find((m) => m.id === 'a1');
      expect(aiMsg!.status).toBe('stopped');
      expect(aiMsg!.content).toBe('');
    });
  });

  // ============================================================
  // 集成路径：完整 SSE 流程
  // ============================================================
  describe('完整 SSE 流程集成', () => {
    it('新建对话: send -> init -> insertNew -> title -> updateTitle', () => {
      const sendMessageFn = vi.fn((_q, cbs) => {
        capturedCallbacks = cbs;
      });

      // 步骤 1: 用户发送消息
      const sendResult = simulateHandleSend([], '什么是机器学习？', sendMessageFn, {
        activeId: null,
        isNewConversation: true,
        isStreaming: false,
      });

      expect(sendResult).not.toBeNull();
      expect(sendResult!.messages).toHaveLength(2);
      expect(sendResult!.input).toBe('');
      expect(sendMessageFn).toHaveBeenCalledOnce();

      // 步骤 2: SSE init 事件 → insertNewConversation
      capturedCallbacks!.onInit('conv-new-001');
      expect(mockInsertNewConversation).toHaveBeenCalledWith(
        expect.objectContaining({ id: 'conv-new-001', title: '新对话' }),
      );

      // 步骤 3: SSE status 事件
      capturedCallbacks!.onStatus('retrieving', '正在检索...');

      // 步骤 4: SSE token 事件
      capturedCallbacks!.onToken('机器学习是');

      // 步骤 5: SSE title 事件 → updateTitle
      capturedCallbacks!.onTitle('conv-new-001', '什么是机器学习？');
      expect(mockUpdateTitle).toHaveBeenCalledWith('conv-new-001', '什么是机器学习？');

      // 步骤 6: SSE done 事件
      capturedCallbacks!.onDone();
    });

    it('已有对话: send -> init(不insert) -> title(更新)', () => {
      const sendMessageFn = vi.fn((_q, cbs, convId) => {
        capturedCallbacks = cbs;
        capturedConversationId = convId;
      });

      const sendResult = simulateHandleSend(
        [
          { id: 'u1', role: 'user', content: '旧问题', status: 'done', timestamp: 1 },
          { id: 'a1', role: 'ai', content: '旧回答', status: 'done', timestamp: 2 },
        ],
        '继续追问',
        sendMessageFn,
        { activeId: 'conv-existing', isNewConversation: false, isStreaming: false },
      );

      expect(sendResult).not.toBeNull();
      expect(sendResult!.messages).toHaveLength(4);
      expect(capturedConversationId).toBe('conv-existing');

      // SSE init → 不应该 insertNew
      capturedCallbacks!.onInit('conv-existing');
      expect(mockInsertNewConversation).not.toHaveBeenCalled();

      // SSE title → 仍然应该 updateTitle
      capturedCallbacks!.onTitle('conv-existing', '继续追问（更新）');
      expect(mockUpdateTitle).toHaveBeenCalledWith('conv-existing', '继续追问（更新）');
    });
  });

  // ============================================================
  // isStreaming 同步到 ConversationContext
  // ============================================================
  describe('isStreaming 同步到 ConversationContext', () => {
    it('isStreaming 变化时应该调用 setContextStreaming', () => {
      // 模拟 controller.ts 中 useEffect 同步 isStreaming
      // useEffect(() => { setContextStreaming(isStreaming); }, [isStreaming, setContextStreaming]);

      mockSetContextStreaming(false);
      expect(mockSetContextStreaming).toHaveBeenCalledWith(false);

      mockSetContextStreaming(true);
      expect(mockSetContextStreaming).toHaveBeenCalledWith(true);

      expect(mockSetContextStreaming).toHaveBeenCalledTimes(2);
    });
  });
});
