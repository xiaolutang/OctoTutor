'use client';

import { useState, useCallback, memo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import type { Message } from '@/chat/types';
import { SourceCard } from './source-card';
import { ThinkingProcess } from './thinking-process';
import { AuthenticatedImage } from './authenticated-image';

interface MessageBubbleProps {
  message: Message;
  onRegenerate?: (messageId: string) => void;
}

const statusLabels: Record<string, string> = {
  sending: '发送中...',
  retrieving: '正在检索相关知识...',
  recognizing: '识别中...',
  generating: '正在生成回答...',
  done: '',
  stopped: '已停止',
  error: '',
};

const remarkPlugins = [remarkMath];
const rehypePlugins: [typeof rehypeKatex, { throwOnError: boolean }][] = [[rehypeKatex, { throwOnError: false }]];

export const MessageBubble = memo(function MessageBubble({
  message,
  onRegenerate,
}: MessageBubbleProps) {
  const isUser = message.role === 'user';
  const [copied, setCopied] = useState(false);
  const [lightboxUrl, setLightboxUrl] = useState<string | null>(null);

  const handleCopy = useCallback(async () => {
    if (!message.content) return;
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // clipboard API 不可用时静默失败
    }
  }, [message.content]);

  const isTerminal = message.status === 'done' || message.status === 'stopped' || message.status === 'error';

  const bubble = (
    <div className={`group flex items-start gap-1 ${isUser ? 'justify-end' : 'justify-start'} mb-4`}>
      <div className="max-w-[80%]">
        <div
          className={`rounded-lg px-4 py-2.5 ${
            isUser
              ? 'bg-primary text-primary-foreground'
              : 'bg-muted text-foreground'
          }`}
        >
          {/* AI 状态提示（仅活跃状态显示） */}
          {!isUser && !isTerminal && (
            <div className="text-xs text-muted-foreground mb-1">
              {statusLabels[message.status] || message.status}
            </div>
          )}

          {/* AI 思考过程 */}
          {!isUser && message.thinkingSteps && message.thinkingSteps.length > 0 && (
            <div className="mb-2">
              <ThinkingProcess
                steps={message.thinkingSteps}
                isStreaming={message.status === 'generating'}
              />
            </div>
          )}

          {/* 内容 */}
          {message.content && (
            <div className={`text-sm leading-relaxed prose prose-sm max-w-none ${isUser ? '' : 'dark:prose-invert'}`}>
              {isUser ? (
                <div className="whitespace-pre-wrap">{message.content}</div>
              ) : (
                <ReactMarkdown
                  remarkPlugins={remarkPlugins}
                  rehypePlugins={rehypePlugins}
                >
                  {message.content}
                </ReactMarkdown>
              )}
            </div>
          )}

          {/* 用户消息图片缩略图 */}
          {isUser && message.images && message.images.length > 0 && (
            <div className="mt-2 flex gap-2">
              {message.images.map((img, i) => (
                <AuthenticatedImage
                  key={i}
                  src={img.url}
                  alt={`图片 ${i + 1}`}
                  className="h-20 w-20 rounded object-cover cursor-pointer"
                  onClick={() => setLightboxUrl(img.url)}
                />
              ))}
            </div>
          )}

          {/* AI 正在生成时无内容则显示加载动画 */}
          {!isUser && !message.content && (message.status === 'recognizing' || message.status === 'retrieving' || message.status === 'generating') && (
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

          {/* AI 来源卡片 */}
          {!isUser && message.sources && message.sources.length > 0 && isTerminal && (
            <SourceCard sources={message.sources} />
          )}
        </div>
      </div>

      {/* AI 消息：操作按钮在右侧 */}
      {!isUser && isTerminal && (
        <div className="mt-1 flex shrink-0 items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          <button
            onClick={handleCopy}
            className="rounded p-1 text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
            title="复制"
          >
            {copied ? (
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
            ) : (
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
              </svg>
            )}
          </button>
          <button
            onClick={() => onRegenerate?.(message.id)}
            className="rounded p-1 text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
            title="重新生成"
          >
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </button>
        </div>
      )}
    </div>
  );

  return (
    <>
      {bubble}
      {lightboxUrl && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70"
          onClick={() => setLightboxUrl(null)}
        >
          <AuthenticatedImage
            src={lightboxUrl}
            alt="大图"
            className="max-h-[90vh] max-w-[90vw] rounded-lg cursor-default"
          />
        </div>
      )}
    </>
  );
});
