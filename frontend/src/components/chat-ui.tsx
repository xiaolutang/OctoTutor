'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { useChatStream } from '@/chat/use-chat-stream';
import { loadMessages, saveMessages } from '@/chat/use-chat-storage';
import type { Message, MessageStatus } from '@/chat/types';
import { ChatInput } from './chat-input';
import { MessageBubble } from './message-bubble';

function createId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
}

export function ChatUI() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [mounted, setMounted] = useState(false);
  const { sendMessage, stop, isStreaming } = useChatStream();
  const aiMsgIdRef = useRef<string>('');

  // 客户端加载历史
  useEffect(() => {
    setMessages(loadMessages());
    setMounted(true);
  }, []);

  // 使用 setMessages(prev => ...) 避免闭包旧值
  const updateMsgAndSave = useCallback(
    (id: string, patch: Partial<Message>, terminalStatus?: MessageStatus) => {
      setMessages((prev) => {
        const next = prev.map((m) => (m.id === id ? { ...m, ...patch } : m));
        if (terminalStatus) {
          // 终态时持久化
          saveMessages(next);
        }
        return next;
      });
    },
    [],
  );

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

    const newMessages = [...messages, userMsg, aiMsg];
    setMessages(newMessages);
    setInput('');
    saveMessages(newMessages);

    sendMessage(text, {
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
      onDone: () => {
        updateMsgAndSave(aiMsgId, { status: 'done' }, 'done');
      },
      onError: (error) => {
        if (error.code === '00000') {
          // 撤回最后 user+ai 消息，内容回填输入框
          setMessages((prev) => {
            const next = prev.slice(0, -2);
            saveMessages(next);
            return next;
          });
          setInput(text);
        } else {
          updateMsgAndSave(
            aiMsgId,
            { status: 'error', error },
            'error',
          );
        }
      },
    });
  }, [input, isStreaming, messages, sendMessage, updateMsgAndSave]);

  const handleStop = useCallback(() => {
    stop();
    const aiMsgId = aiMsgIdRef.current;
    if (aiMsgId) {
      updateMsgAndSave(aiMsgId, { status: 'stopped' }, 'stopped');
    }
  }, [stop, updateMsgAndSave]);

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
            <MessageBubble key={msg.id} message={msg} />
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
      />
    </div>
  );
}
