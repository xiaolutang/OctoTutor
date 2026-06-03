import { useState, useEffect, useRef, useCallback } from 'react';
import { useChatStream } from './use-chat-stream';
import { useConversation } from './use-conversation';
import { useAuth } from '@/contexts/auth-context';
import { useConversationContext } from '@/contexts/conversation-context';
import type { Message, MessageStatus, ThinkingStep } from './types';

function createId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
}

/** AI 回复占位消息 ID 前缀，用于区分轮询占位和真实消息 */
const POLLING_PLACEHOLDER_PREFIX = '__polling__';

/** 检测消息列表是否以用户消息结尾（AI 回复待处理），且在 2 分钟内 */
function needsPollingPlaceholder(msgs: Message[]): boolean {
  if (msgs.length === 0) return false;
  const last = msgs[msgs.length - 1];
  return last.role === 'user' && Date.now() - last.timestamp < 120_000;
}

/** 为消息列表添加占位 AI 消息（显示"正在检索…"动画） */
function withPollingPlaceholder(msgs: Message[]): Message[] {
  return [
    ...msgs,
    {
      id: POLLING_PLACEHOLDER_PREFIX + createId(),
      role: 'ai',
      content: '',
      status: 'retrieving',
      timestamp: Date.now(),
    },
  ];
}

/** 加载消息后按需追加占位 AI 消息 */
function loadWithPlaceholder(msgs: Message[]): Message[] {
  return needsPollingPlaceholder(msgs) ? withPollingPlaceholder(msgs) : msgs;
}

export function useChatController() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [mounted, setMounted] = useState(false);
  const { sendMessage, stop, isStreaming } = useChatStream();
  const { loadConversation } = useConversation();
  const { isInitialized: isAuthReady } = useAuth();
  const {
    activeId,
    isNewConversation,
    isInitialized: isConvReady,
    insertNewConversation,
    updateTitle,
    setIsStreaming: setContextStreaming,
    registerSwitchHandler,
  } = useConversationContext();
  const aiMsgIdRef = useRef<string>('');
  const messagesRef = useRef<Message[]>(messages);
  messagesRef.current = messages;

  // 同步 isStreaming 到 ConversationContext（供 sidebar 使用）
  useEffect(() => {
    setContextStreaming(isStreaming);
  }, [isStreaming, setContextStreaming]);

  // 等 Auth + 对话列表都初始化完成后再加载消息
  // 此时 activeId 已被 ConversationProvider 正确设置，不存在竞态
  useEffect(() => {
    if (!isAuthReady) return;
    if (!isConvReady) return;
    if (mounted) return;
    let cancelled = false;
    loadConversation(activeId).then(({ messages: loadedMessages }) => {
      if (!cancelled) {
        setMessages(loadWithPlaceholder(loadedMessages));
        setMounted(true);
      }
    });
    return () => { cancelled = true; };
  }, [isAuthReady, isConvReady, activeId, mounted, loadConversation]);

  // 新对话：清空消息
  useEffect(() => {
    if (!mounted) return;
    if (activeId === null && isNewConversation) {
      setMessages([]);
    }
  }, [activeId, isNewConversation, mounted]);

  // 注册 switchHandler：用户切换对话时主动调用 loadConversation
  useEffect(() => {
    if (!mounted) return;
    registerSwitchHandler(async (id: string) => {
      const loaded = (await loadConversation(id)).messages;
      setMessages(loadWithPlaceholder(loaded));
    });
    return () => registerSwitchHandler(null);
  }, [mounted, registerSwitchHandler, loadConversation]);

  // 轮询 AI 回复：刷新后 SSE 断裂，先轮询等待，超时则标记中断
  // 触发条件：消息列表最后一条是占位/正在生成的 AI 消息
  // 注意：不依赖 messages，通过 messagesRef 读取，避免轮询更新触发 effect 重建
  useEffect(() => {
    if (!mounted || !activeId || isStreaming) return;

    const currentMessages = messagesRef.current;
    if (currentMessages.length === 0) return;

    const lastMsg = currentMessages[currentMessages.length - 1];
    if (lastMsg.role !== 'ai' || !['generating', 'retrieving'].includes(lastMsg.status)) return;
    if (Date.now() - lastMsg.timestamp > 180_000) return;

    // 记住当前真实 AI 消息数量（排除占位），用于检测服务端新增
    const localRealAiCount = currentMessages.filter(
      (m) => m.role === 'ai' && !m.id.startsWith(POLLING_PLACEHOLDER_PREFIX),
    ).length;

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let pollsLeft = 10; // 10 × 3s = 30s 总超时

    const markAsInterrupted = () => {
      setMessages((prev) =>
        prev.map((m) =>
          m.id.startsWith(POLLING_PLACEHOLDER_PREFIX)
            ? {
                ...m,
                status: 'error',
                error: {
                  code: 'INTERRUPTED',
                  message: 'AI 回复因页面刷新而中断，请重新生成',
                  action: 'retry',
                },
              }
            : m,
        ),
      );
    };

    const scheduleNext = () => {
      if (cancelled) return;
      if (pollsLeft <= 0) {
        markAsInterrupted();
        return;
      }
      timer = setTimeout(async () => {
        if (cancelled) return;
        timer = null;
        pollsLeft--;
        try {
          const { messages: serverMessages, stale } = await loadConversation(activeId);
          if (cancelled || stale) { scheduleNext(); return; }

          const serverAiCount = serverMessages.filter((m) => m.role === 'ai').length;
          if (serverAiCount > localRealAiCount) {
            setMessages(serverMessages);
            const last = serverMessages[serverMessages.length - 1];
            if (last.role === 'ai' && ['done', 'error', 'stopped'].includes(last.status)) {
              return;
            }
          }
          scheduleNext();
        } catch {
          scheduleNext();
        }
      }, 3000);
    };

    scheduleNext();

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [mounted, isStreaming, activeId, loadConversation]);

  // 更新单条消息
  const updateMsg = useCallback(
    (id: string, patch: Partial<Message>) => {
      setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, ...patch } : m)));
    },
    [],
  );

  // SSE 流式启动
  const startSSE = useCallback(
    (question: string, aiMsgId: string) => {
      sendMessage(
        question,
        {
          onInit: (convId: string) => {
            if (isNewConversation) {
              insertNewConversation({
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
          onStatus: (stage: string, _message: string) => {
            if (stage === 'retrieving' || stage === 'generating') {
              updateMsg(aiMsgId, { status: stage as MessageStatus });
            }
          },
          onSources: (sources) => {
            updateMsg(aiMsgId, { sources });
          },
          onToken: (token: string) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === aiMsgId ? { ...m, content: m.content + token } : m,
              ),
            );
          },
          onThinking: (step: ThinkingStep) => {
            setMessages((prev) =>
              prev.map((m) => {
                if (m.id !== aiMsgId) return m;
                const existing = m.thinkingSteps ?? [];
                return { ...m, thinkingSteps: [...existing, step] };
              }),
            );
          },
          onDone: () => {
            updateMsg(aiMsgId, { status: 'done' });
          },
          onTitle: (convId: string, title: string) => {
            updateTitle(convId, title);
          },
          onError: (error) => {
            updateMsg(aiMsgId, { status: 'error', error });
            if (error.code === '00000') setInput(question);
          },
        },
        activeId ?? undefined,
      );
    },
    [sendMessage, updateMsg, activeId, isNewConversation, insertNewConversation, updateTitle],
  );

  // 发送消息
  const handleSend = useCallback(() => {
    const text = input.trim();
    if (!text || isStreaming) return;

    const userMsg: Message = {
      id: createId(),
      role: 'user',
      content: text,
      status: 'sending',
      timestamp: Date.now(),
    };

    const aiMsgId = createId();
    aiMsgIdRef.current = aiMsgId;

    const aiMsg: Message = {
      id: aiMsgId,
      role: 'ai',
      content: '',
      status: 'retrieving',
      timestamp: Date.now(),
    };

    setMessages((prev) => [...prev, userMsg, aiMsg]);
    setInput('');
    startSSE(text, aiMsgId);
  }, [input, isStreaming, startSSE]);

  // 停止生成
  const handleStop = useCallback(() => {
    stop();
    const aiMsgId = aiMsgIdRef.current;
    if (aiMsgId) {
      updateMsg(aiMsgId, { status: 'stopped' });
    }
  }, [stop, updateMsg]);

  // 重新生成
  const handleRegenerate = useCallback(
    (messageId: string) => {
      if (isStreaming) return;

      const currentMessages = messagesRef.current;
      const msgIndex = currentMessages.findIndex((m) => m.id === messageId);
      if (msgIndex < 0) return;

      const aiMsg = currentMessages[msgIndex];
      if (aiMsg.role !== 'ai') return;

      // 向前查找最近的用户消息
      let userMsgIndex = msgIndex - 1;
      while (userMsgIndex >= 0 && currentMessages[userMsgIndex].role !== 'user') {
        userMsgIndex--;
      }
      if (userMsgIndex < 0) return;

      const userText = currentMessages[userMsgIndex].content;
      const newAiMsgId = createId();
      aiMsgIdRef.current = newAiMsgId;

      const newAiMsg: Message = {
        id: newAiMsgId,
        role: 'ai',
        content: '',
        status: 'retrieving',
        timestamp: Date.now(),
      };

      const newMessages = [...currentMessages];
      newMessages[msgIndex] = newAiMsg;
      setMessages(newMessages);
      startSSE(userText, newAiMsgId);
    },
    [isStreaming, startSSE],
  );

  return {
    messages,
    input,
    mounted,
    isStreaming,
    setInput,
    handleSend,
    handleStop,
    handleRegenerate,
  };
}
