import { useState, useEffect, useRef, useCallback } from 'react';
import { useChatStream, resumeStream } from './use-chat-stream';
import type { ResumeCallbacks } from './use-chat-stream';
import { useConversation } from './use-conversation';
import { useAuth } from '@/contexts/auth-context';
import { useConversationContext } from '@/contexts/conversation-context';
import type { Message, MessageStatus, ThinkingStep, ImageRef } from './types';
import { getUserQuestionText } from './types';
import { createId } from '@/lib/utils';

/** 检测消息列表是否以用户消息结尾（AI 回复待处理），且在 2 分钟内 */
function needsResumePlaceholder(msgs: Message[]): boolean {
  if (msgs.length === 0) return false;
  const last = msgs[msgs.length - 1];
  return last.role === 'user' && Date.now() - last.timestamp < 120_000;
}

/** 处理加载的消息：如果最后一条是用户消息（2分钟内），追加占位 AI 消息 */
function processLoadedMessages(loadedMessages: Message[]): Message[] {
  return needsResumePlaceholder(loadedMessages)
    ? [
        ...loadedMessages,
        {
          id: createId(),
          role: 'ai' as const,
          content: '',
          status: 'retrieving' as const,
          timestamp: Date.now(),
        },
      ]
    : loadedMessages;
}

export function useChatController() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [mounted, setMounted] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
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

  // 更新单条消息
  const updateMsg = useCallback(
    (id: string, patch: Partial<Message>) => {
      setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, ...patch } : m)));
    },
    [],
  );

  // 追加 token 到指定消息（仅 AI 消息，content 始终为 string）
  const appendToken = useCallback(
    (id: string, token: string) => {
      setMessages((prev) =>
        prev.map((m) => {
          if (m.id !== id) return m;
          const text = typeof m.content === 'string' ? m.content : '';
          return { ...m, content: text + token };
        }),
      );
    },
    [],
  );

  // 追加 thinking step 到指定消息
  const appendThinking = useCallback(
    (id: string, step: ThinkingStep) => {
      setMessages((prev) =>
        prev.map((m) => {
          if (m.id !== id) return m;
          const existing = m.thinkingSteps ?? [];
          return { ...m, thinkingSteps: [...existing, step] };
        }),
      );
    },
    [],
  );

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
        setLoadError(null);
        setMessages(processLoadedMessages(loadedMessages));
        setMounted(true);
      }
    }).catch(() => {
      if (!cancelled) {
        setLoadError('加载对话失败');
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
      setMessages(loaded);
    });
    return () => registerSwitchHandler(null);
  }, [mounted, registerSwitchHandler, loadConversation]);

  // SSE 重连：刷新后检测到未完成 AI 回复 → 发起 GET /chat/stream/resume
  // 触发条件：消息列表最后一条是正在生成/检索的 AI 消息，且在 3 分钟内
  // 注意：不依赖 messages，通过 messagesRef 读取，避免更新触发 effect 重建
  useEffect(() => {
    if (!mounted || !activeId || isStreaming) return;

    const currentMessages = messagesRef.current;
    if (currentMessages.length === 0) return;

    const lastMsg = currentMessages[currentMessages.length - 1];
    if (lastMsg.role !== 'ai' || !['generating', 'retrieving', 'recognizing'].includes(lastMsg.status)) return;
    if (Date.now() - lastMsg.timestamp > 180_000) return;

    let cancelled = false;

    const callbacks: ResumeCallbacks = {
      onStatus: (stage) => {
        if (!cancelled && (stage === 'recognizing' || stage === 'retrieving' || stage === 'generating')) {
          updateMsg(lastMsg.id, { status: stage as MessageStatus });
        }
      },
      onToken: (token) => {
        if (!cancelled) appendToken(lastMsg.id, token);
      },
      onSources: (sources) => {
        if (!cancelled) updateMsg(lastMsg.id, { sources });
      },
      onThinking: (step) => {
        if (!cancelled) appendThinking(lastMsg.id, step);
      },
      onDone: () => {
        if (!cancelled) updateMsg(lastMsg.id, { status: 'done' });
      },
      onError: (error) => {
        if (!cancelled) updateMsg(lastMsg.id, { status: 'error', error });
      },
      onMessagesReady: (msgs) => {
        if (!cancelled) setMessages(msgs);
      },
    };

    resumeStream(activeId, callbacks);

    return () => { cancelled = true; };
  }, [mounted, isStreaming, activeId, updateMsg, appendToken, appendThinking]);

  // SSE 流式启动
  const startSSE = useCallback(
    (question: string, aiMsgId: string, images?: ImageRef[]) => {
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
            if (stage === 'recognizing' || stage === 'retrieving' || stage === 'generating') {
              updateMsg(aiMsgId, { status: stage as MessageStatus });
            }
          },
          onSources: (sources) => {
            updateMsg(aiMsgId, { sources });
          },
          onToken: (token: string) => {
            appendToken(aiMsgId, token);
          },
          onThinking: (step: ThinkingStep) => {
            appendThinking(aiMsgId, step);
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
        images,
      );
    },
    [sendMessage, updateMsg, activeId, isNewConversation, insertNewConversation, updateTitle],
  );

  // 发送消息
  const handleSend = useCallback((text: string, images?: ImageRef[]) => {
    if (!text || isStreaming) return;

    const userMsg: Message = {
      id: createId(),
      role: 'user',
      content: text,
      status: 'sending',
      images,
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
    startSSE(text, aiMsgId, images);
  }, [isStreaming, startSSE]);

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

      const userText = getUserQuestionText(currentMessages[userMsgIndex].content);
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

  // 重试加载对话
  const retryLoad = useCallback(() => {
    if (!activeId) return;
    setLoadError(null);
    setMounted(false);
    loadConversation(activeId).then(({ messages: loadedMessages }) => {
      setLoadError(null);
      setMessages(processLoadedMessages(loadedMessages));
      setMounted(true);
    }).catch(() => {
      setLoadError('加载对话失败');
    });
  }, [activeId, loadConversation]);

  return {
    messages,
    input,
    mounted,
    isStreaming,
    loadError,
    retryLoad,
    setInput,
    handleSend,
    handleStop,
    handleRegenerate,
  };
}
