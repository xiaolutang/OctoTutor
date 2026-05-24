import { useState, useEffect, useRef, useCallback } from 'react';
import { useChatStream } from './use-chat-stream';
import { useConversation, saveConversationId, loadConversationId } from './use-conversation';
import { useAuth } from '@/contexts/auth-context';
import type { Message, MessageStatus, ThinkingStep } from './types';

function createId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
}

export function useChatController() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [mounted, setMounted] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(loadConversationId());
  const { sendMessage, stop, isStreaming } = useChatStream();
  const { loadConversation } = useConversation();
  const { isInitialized } = useAuth();
  const aiMsgIdRef = useRef<string>('');

  // 等 Auth SDK 初始化完成后再加载对话历史，避免 token 未就绪导致 401
  useEffect(() => {
    if (!isInitialized) return;
    let cancelled = false;
    loadConversation().then(({ messages: loadedMessages }) => {
      if (!cancelled) {
        setMessages(loadedMessages);
        const storedId = loadConversationId();
        if (storedId) {
          setConversationId(storedId);
        }
        setMounted(true);
      }
    });
    return () => { cancelled = true; };
  }, [isInitialized, loadConversation]);

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
            setConversationId(convId);
            saveConversationId(convId);
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
          onError: (error) => {
            if (error.code === '00000') {
              // 保留用户消息，AI 标记 error + 回填输入框
              updateMsg(aiMsgId, { status: 'error', error });
              setInput(question);
            } else {
              updateMsg(aiMsgId, { status: 'error', error });
            }
          },
        },
        conversationId ?? undefined,
      );
    },
    [sendMessage, updateMsg, conversationId],
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

      const msgIndex = messages.findIndex((m) => m.id === messageId);
      if (msgIndex < 0) return;

      const aiMsg = messages[msgIndex];
      if (aiMsg.role !== 'ai') return;

      // 向前查找最近的用户消息
      let userMsgIndex = msgIndex - 1;
      while (userMsgIndex >= 0 && messages[userMsgIndex].role !== 'user') {
        userMsgIndex--;
      }
      if (userMsgIndex < 0) return;

      const userText = messages[userMsgIndex].content;
      const newAiMsgId = createId();
      aiMsgIdRef.current = newAiMsgId;

      const newAiMsg: Message = {
        id: newAiMsgId,
        role: 'ai',
        content: '',
        status: 'retrieving',
        timestamp: Date.now(),
      };

      const newMessages = [...messages];
      newMessages[msgIndex] = newAiMsg;
      setMessages(newMessages);
      startSSE(userText, newAiMsgId);
    },
    [isStreaming, messages, startSSE],
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
