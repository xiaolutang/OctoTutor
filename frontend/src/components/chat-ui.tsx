'use client';

import { useRef, useEffect } from 'react';
import { useChatController } from '@/chat/controller';
import { ChatInput } from './chat-input';
import { MessageBubble } from './message-bubble';
import 'katex/dist/katex.min.css';

export function ChatUI() {
  const {
    messages,
    input,
    mounted,
    isStreaming,
    setInput,
    handleSend,
    handleStop,
    handleRegenerate,
  } = useChatController();

  const messagesEndRef = useRef<HTMLDivElement>(null);

  // 自动滚动到底部
  // 新消息（长度变化）用 smooth，token 更新用 instant 避免卡顿
  const prevLenRef = useRef(0);
  useEffect(() => {
    const smooth = messages.length > prevLenRef.current;
    prevLenRef.current = messages.length;
    messagesEndRef.current?.scrollIntoView({ behavior: smooth ? 'smooth' : 'instant' });
  }, [messages]);

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
              onRegenerate={handleRegenerate}
            />
          ))
        )}
        <div ref={messagesEndRef} />
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
