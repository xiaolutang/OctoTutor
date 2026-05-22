'use client';

import type { Message } from '@/chat/types';

interface MessageBubbleProps {
  message: Message;
}

const statusLabels: Record<string, string> = {
  sending: '发送中...',
  retrieving: '正在检索相关知识...',
  generating: '正在生成回答...',
  done: '',
  stopped: '已停止',
  error: '',
};

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === 'user';

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-4`}>
      <div
        className={`max-w-[80%] rounded-lg px-4 py-2.5 ${
          isUser
            ? 'bg-primary text-primary-foreground'
            : 'bg-muted text-foreground'
        }`}
      >
        {/* AI 状态提示 */}
        {!isUser && message.status !== 'done' && message.status !== 'error' && (
          <div className="text-xs text-muted-foreground mb-1">
            {statusLabels[message.status] || message.status}
          </div>
        )}

        {/* 内容 */}
        {message.content && (
          <div className="whitespace-pre-wrap text-sm leading-relaxed">
            {message.content}
          </div>
        )}

        {/* AI 正在生成时无内容则显示加载动画 */}
        {!isUser && !message.content && (message.status === 'retrieving' || message.status === 'generating') && (
          <div className="flex items-center gap-1 text-sm text-muted-foreground">
            <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-current" />
            <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-current [animation-delay:0.2s]" />
            <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-current [animation-delay:0.4s]" />
          </div>
        )}

        {/* 停止提示 */}
        {!isUser && message.status === 'stopped' && !message.content && (
          <div className="text-xs text-muted-foreground italic">已停止生成</div>
        )}

        {/* 错误提示 */}
        {!isUser && message.status === 'error' && message.error && (
          <div className="text-xs text-destructive mt-1">
            {message.error.message}
          </div>
        )}
      </div>
    </div>
  );
}
