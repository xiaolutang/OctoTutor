'use client';

import { useState, useCallback, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import type { Message } from '@/chat/types';
import { SourceCard } from './source-card';

interface MessageBubbleProps {
  message: Message;
  isStreaming: boolean;
  isEditing: boolean;
  onEdit?: (messageId: string) => void;
  onEditConfirm?: (messageId: string, newContent: string) => void;
  onEditCancel?: () => void;
  onRegenerate?: (messageId: string) => void;
}

const statusLabels: Record<string, string> = {
  sending: '发送中...',
  retrieving: '正在检索相关知识...',
  generating: '正在生成回答...',
  done: '',
  stopped: '已停止',
  error: '',
};

const remarkPlugins = [remarkMath];
const rehypePlugins = [[rehypeKatex, { throwOnError: false }]];

function EditArea({
  initialContent,
  onConfirm,
  onCancel,
}: {
  initialContent: string;
  onConfirm: (content: string) => void;
  onCancel: () => void;
}) {
  const [editText, setEditText] = useState(initialContent);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = textareaRef.current;
    if (el) {
      el.focus();
      // 光标移到末尾
      el.setSelectionRange(el.value.length, el.value.length);
    }
  }, []);

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      onConfirm(editText);
    } else if (e.key === 'Escape') {
      e.preventDefault();
      onCancel();
    }
  }

  return (
    <div className="max-w-[80%]">
      <textarea
        ref={textareaRef}
        value={editText}
        onChange={(e) => setEditText(e.target.value)}
        onKeyDown={handleKeyDown}
        rows={3}
        className="w-full resize-none rounded-lg border border-input bg-background px-3 py-2 text-sm leading-relaxed text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
      />
      <div className="mt-1 flex gap-2">
        <button
          onClick={() => onConfirm(editText)}
          className="rounded-lg bg-primary px-3 py-1 text-xs font-medium text-primary-foreground hover:bg-primary/90"
        >
          确认
        </button>
        <button
          onClick={onCancel}
          className="rounded-lg bg-muted px-3 py-1 text-xs font-medium text-muted-foreground hover:bg-muted/80"
        >
          取消
        </button>
      </div>
    </div>
  );
}

export function MessageBubble({
  message,
  isStreaming,
  isEditing,
  onEdit,
  onEditConfirm,
  onEditCancel,
  onRegenerate,
}: MessageBubbleProps) {
  const isUser = message.role === 'user';
  const [copied, setCopied] = useState(false);

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

  return (
    <div className={`group flex items-start gap-1 ${isUser ? 'justify-end' : 'justify-start'} mb-4`}>
      {/* 用户消息：编辑按钮 — 非流式且非编辑态时显示 */}
      {isUser && !isStreaming && !isEditing && (
        <button
          onClick={() => onEdit?.(message.id)}
          className="mt-1 shrink-0 rounded p-1 text-muted-foreground opacity-0 group-hover:opacity-100 hover:text-foreground hover:bg-muted transition-opacity"
          title="编辑"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
          </svg>
        </button>
      )}

      {/* 用户消息：编辑态渲染 textarea */}
      {isUser && isEditing ? (
        <EditArea
          initialContent={message.content}
          onConfirm={(newContent) => onEditConfirm?.(message.id, newContent)}
          onCancel={() => onEditCancel?.()}
        />
      ) : (
        <div className="max-w-[80%]">
          <div
            className={`rounded-lg px-4 py-2.5 ${
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

            {/* AI 来源卡片 */}
            {!isUser && message.sources && message.sources.length > 0 && isTerminal && (
              <SourceCard sources={message.sources} />
            )}
          </div>
        </div>
      )}

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
}
