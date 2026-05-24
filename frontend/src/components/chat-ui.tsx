'use client';

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
