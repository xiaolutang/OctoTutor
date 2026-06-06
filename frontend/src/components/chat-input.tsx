'use client';

import { useRef, useEffect } from 'react';
import { Paperclip } from 'lucide-react';
import { useImageUpload } from '@/hooks/use-image-upload';
import { ImagePreview } from './image-preview';
import type { ImageRef } from '@/chat/types';

interface ChatInputProps {
  value: string;
  onChange: (value: string) => void;
  onSend: (text: string, images?: ImageRef[]) => void;
  onStop: () => void;
  isStreaming: boolean;
}

export function ChatInput({
  value,
  onChange,
  onSend,
  onStop,
  isStreaming,
}: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { items, addImages, removeImage, retryUpload, clearAll, successImages, isAllUploaded } = useImageUpload();

  // 自动调整高度
  useEffect(() => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = 'auto';
      el.style.height = Math.min(el.scrollHeight, 200) + 'px';
    }
  }, [value]);

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (!isStreaming && value.trim() && isAllUploaded) {
        handleSendClick();
      }
    }
  }

  function handleSendClick() {
    onSend(value.trim(), successImages.length > 0 ? successImages : undefined);
    clearAll();
  }

  return (
    <div className="border-t bg-background">
      {/* 图片预览区 */}
      {items.length > 0 && (
        <div className="flex gap-2 px-4 pt-3">
          {items.map((item) => (
            <ImagePreview
              key={item.localId}
              item={item}
              onRemove={removeImage}
              onRetry={retryUpload}
            />
          ))}
        </div>
      )}

      <div className="flex items-end gap-2 p-4">
        {/* 隐藏的文件选择器 */}
        <input
          ref={fileInputRef}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          multiple
          className="hidden"
          onChange={(e) => {
            if (e.target.files) addImages(Array.from(e.target.files));
            e.target.value = '';
          }}
        />

        {/* 附件按钮 */}
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={isStreaming}
          className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-input text-muted-foreground hover:bg-muted disabled:opacity-50"
          title="上传图片"
        >
          <Paperclip className="h-4 w-4" />
        </button>

        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
          onPaste={(e) => {
            const clipboardItems = e.clipboardData?.items;
            if (clipboardItems) {
              const imageFiles: File[] = [];
              for (const item of Array.from(clipboardItems)) {
                if (item.type.startsWith('image/')) {
                  const file = item.getAsFile();
                  if (file) imageFiles.push(file);
                }
              }
              if (imageFiles.length > 0) {
                addImages(imageFiles);
              }
            }
          }}
          placeholder="输入问题..."
          disabled={isStreaming}
          rows={1}
          className="flex-1 resize-none rounded-lg border border-input bg-background px-3 py-2 text-sm leading-relaxed placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
        />
        {isStreaming ? (
          <button
            onClick={onStop}
            className="inline-flex h-9 items-center justify-center rounded-lg bg-destructive px-4 text-sm font-medium text-white hover:bg-destructive/90"
          >
            停止
          </button>
        ) : (
          <button
            onClick={handleSendClick}
            disabled={isStreaming || !value.trim() || !isAllUploaded}
            className="inline-flex h-9 items-center justify-center rounded-lg bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            发送
          </button>
        )}
      </div>
    </div>
  );
}
