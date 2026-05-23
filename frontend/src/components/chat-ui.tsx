'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { useChatStream } from '@/chat/use-chat-stream';
import { saveMessages } from '@/chat/use-chat-storage';
import { useConversation } from '@/chat/use-conversation';
import type { Message, MessageStatus, ThinkingStep } from '@/chat/types';
import { ChatInput } from './chat-input';
import { MessageBubble } from './message-bubble';
import 'katex/dist/katex.min.css';

function createId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
}

export function ChatUI() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [mounted, setMounted] = useState(false);
  const { sendMessage, stop, isStreaming } = useChatStream();
  const { conversationId, loadConversation } = useConversation();
  const aiMsgIdRef = useRef<string>('');

  // 加载对话历史（优先 API，降级 localStorage）
  useEffect(() => {
    let cancelled = false;
    loadConversation().then(({ messages: loadedMessages }) => {
      if (!cancelled) {
        setMessages(loadedMessages);
        setMounted(true);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [loadConversation]);

  // 使用 setMessages(prev => ...) 避免闭包旧值
  // terminalStatus 存在时才调用 saveMessages（部分回答兜底）
  const updateMsgAndSave = useCallback(
    (id: string, patch: Partial<Message>, terminalStatus?: MessageStatus) => {
      setMessages((prev) => {
        const next = prev.map((m) => (m.id === id ? { ...m, ...patch } : m));
        if (terminalStatus) {
          saveMessages(next);
        }
        return next;
      });
    },
    [],
  );

  const startSSE = useCallback(
    (question: string, aiMsgId: string) => {
      sendMessage(
        question,
        {
          onStatus: (stage: string, _message: string) => {
            if (stage === 'retrieving' || stage === 'generating') {
              updateMsgAndSave(aiMsgId, { status: stage as MessageStatus });
            }
          },
          onSources: (sources) => {
            updateMsgAndSave(aiMsgId, { sources });
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
            // onDone 不调用 saveMessages
            updateMsgAndSave(aiMsgId, { status: 'done' });
          },
          onError: (error) => {
            if (error.code === '00000') {
              // 撤回最后 user+ai 消息，内容回填输入框，保留 saveMessages
              setMessages((prev) => {
                const next = prev.slice(0, -2);
                saveMessages(next);
                return next;
              });
              setInput(question);
            } else {
              updateMsgAndSave(aiMsgId, { status: 'error', error }, 'error');
            }
          },
        },
        conversationId ?? undefined,
      );
    },
    [sendMessage, updateMsgAndSave, conversationId],
  );

  const appendAndSend = useCallback(
    (baseMessages: Message[], questionText: string) => {
      const userMsg: Message = {
        id: createId(),
        role: 'user',
        content: questionText,
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

      const newMessages = [...baseMessages, userMsg, aiMsg];
      setMessages(newMessages);
      // 发送时不调用 saveMessages

      startSSE(questionText, aiMsgId);
    },
    [startSSE],
  );

  const handleSend = useCallback(() => {
    const text = input.trim();
    if (!text || isStreaming) return;

    appendAndSend(messages, text);
    setInput('');
  }, [input, isStreaming, messages, appendAndSend]);

  const handleStop = useCallback(() => {
    stop();
    const aiMsgId = aiMsgIdRef.current;
    if (aiMsgId) {
      // handleStop 保留 saveMessages（部分回答兜底）
      updateMsgAndSave(aiMsgId, { status: 'stopped' }, 'stopped');
    }
  }, [stop, updateMsgAndSave]);

  /**
   * 重新生成：删除旧的 AI 消息，创建新的 AI 消息，重新发起 SSE
   */
  const handleRegenerate = useCallback(
    (messageId: string) => {
      if (isStreaming) return;

      // 找到 AI 消息及其前一条用户消息
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

      // 创建新的 AI 消息
      const newAiMsgId = createId();
      aiMsgIdRef.current = newAiMsgId;

      const newAiMsg: Message = {
        id: newAiMsgId,
        role: 'ai',
        content: '',
        status: 'retrieving',
        timestamp: Date.now(),
      };

      // 删除旧 AI 消息，替换为新 AI 消息
      const newMessages = [...messages];
      newMessages[msgIndex] = newAiMsg;
      setMessages(newMessages);
      // handleRegenerate 不调用 saveMessages

      startSSE(userText, newAiMsgId);
    },
    [isStreaming, messages, startSSE],
  );

  if (!mounted) {
    return (
      <div className="flex h-full items-center justify-center text-muted-foreground">
        加载中...
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      {/* 消息列表 */}
      <div className="flex-1 overflow-y-auto px-4 py-6">
        {messages.length === 0 ? (
          <div className="flex h-full items-center justify-center text-muted-foreground">
            <p>输入问题开始对话</p>
          </div>
        ) : (
          messages.map((msg) => (
            <MessageBubble
              key={msg.id}
              message={msg}
              isStreaming={isStreaming}
              onRegenerate={handleRegenerate}
            />
          ))
        )}
      </div>

      {/* 输入区 */}
      <ChatInput
        value={input}
        onChange={setInput}
        onSend={handleSend}
        onStop={handleStop}
        isStreaming={isStreaming}
        disabled={isStreaming}
      />
    </div>
  );
}
