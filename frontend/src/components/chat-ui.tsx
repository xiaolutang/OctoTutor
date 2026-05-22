'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { useChatStream } from '@/chat/use-chat-stream';
import { loadMessages, saveMessages } from '@/chat/use-chat-storage';
import type { Message, MessageStatus } from '@/chat/types';
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
  const [editingId, setEditingId] = useState<string | null>(null);
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

  const startSSE = useCallback(
    (question: string, aiMsgId: string) => {
      sendMessage(question, {
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
            setInput(question);
          } else {
            updateMsgAndSave(
              aiMsgId,
              { status: 'error', error },
              'error',
            );
          }
        },
      });
    },
    [sendMessage, updateMsgAndSave],
  );

  const handleSend = useCallback(() => {
    const text = input.trim();
    if (!text || isStreaming || editingId !== null) return;

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

    startSSE(text, aiMsgId);
  }, [input, isStreaming, editingId, messages, startSSE]);

  const handleStop = useCallback(() => {
    stop();
    const aiMsgId = aiMsgIdRef.current;
    if (aiMsgId) {
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
      saveMessages(newMessages);

      startSSE(userText, newAiMsgId);
    },
    [isStreaming, messages, startSSE],
  );

  /**
   * 编辑用户消息：进入原地编辑模式
   */
  const handleEdit = useCallback(
    (messageId: string) => {
      if (isStreaming) return;

      const msgIndex = messages.findIndex((m) => m.id === messageId);
      if (msgIndex < 0) return;

      const userMsg = messages[msgIndex];
      if (userMsg.role !== 'user') return;

      setEditingId(messageId);
    },
    [isStreaming, messages],
  );

  /**
   * 确认编辑：截断消息 + 重新发送
   */
  const handleEditConfirm = useCallback(
    (messageId: string, newContent: string) => {
      const trimmed = newContent.trim();
      if (!trimmed) {
        // 空文本视为取消
        setEditingId(null);
        return;
      }

      const msgIndex = messages.findIndex((m) => m.id === messageId);
      if (msgIndex < 0) {
        setEditingId(null);
        return;
      }

      // 截断到该消息之前
      const truncatedMessages = messages.slice(0, msgIndex);

      // 创建新的用户消息
      const newUserMsg: Message = {
        id: createId(),
        role: 'user',
        content: trimmed,
        status: 'sending',
        timestamp: Date.now(),
      };

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

      const updatedMessages = [...truncatedMessages, newUserMsg, newAiMsg];
      setMessages(updatedMessages);
      saveMessages(updatedMessages);
      setEditingId(null);

      startSSE(trimmed, newAiMsgId);
    },
    [messages, startSSE],
  );

  /**
   * 取消编辑
   */
  const handleEditCancel = useCallback(() => {
    setEditingId(null);
  }, []);

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
              isEditing={editingId === msg.id}
              onEdit={handleEdit}
              onEditConfirm={handleEditConfirm}
              onEditCancel={handleEditCancel}
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
        disabled={isStreaming || editingId !== null}
      />
    </div>
  );
}
