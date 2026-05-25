'use client';

import { useState, useRef, useEffect } from 'react';
import { MoreVertical } from 'lucide-react';
import { toast } from 'sonner';
import type { ConversationItem } from '@/chat/types';

interface ConversationItemCardProps {
  item: ConversationItem;
  isActive: boolean;
  onSelect: (id: string) => void;
  onRename: (id: string, title: string) => Promise<void>;
  onPin: (id: string) => Promise<void>;
  onUnpin: (id: string) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
  isStreaming: boolean;
}

function formatRelativeTime(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);

  if (diffMin < 1) return '刚刚';
  if (diffMin < 60) return `${diffMin}分钟前`;
  const diffHour = Math.floor(diffMin / 60);
  if (diffHour < 24) return `${diffHour}小时前`;
  const diffDay = Math.floor(diffHour / 24);
  if (diffDay < 30) return `${diffDay}天前`;
  return date.toLocaleDateString('zh-CN');
}

export function ConversationItemCard({
  item,
  isActive,
  onSelect,
  onRename,
  onPin,
  onUnpin,
  onDelete,
  isStreaming,
}: ConversationItemCardProps) {
  const [isRenaming, setIsRenaming] = useState(false);
  const [renameValue, setRenameValue] = useState(item.title);
  const [menuOpen, setMenuOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const renameRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isRenaming && renameRef.current) {
      renameRef.current.focus();
      renameRef.current.select();
    }
  }, [isRenaming]);

  const handleRenameSubmit = async () => {
    const trimmed = renameValue.trim();
    if (trimmed && trimmed !== item.title) {
      try {
        await onRename(item.id, trimmed);
      } catch (err) {
        const msg = err instanceof Error ? err.message : '重命名失败';
        toast.error(msg);
        setRenameValue(item.title);
      }
    } else if (!trimmed) {
      setRenameValue(item.title);
    }
    setIsRenaming(false);
  };

  const handleRenameKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleRenameSubmit();
    } else if (e.key === 'Escape') {
      setRenameValue(item.title);
      setIsRenaming(false);
    }
  };

  const handleDelete = async () => {
    setDeleteOpen(false);
    setMenuOpen(false);
    await onDelete(item.id);
  };

  return (
    <div
      className={`group flex items-center gap-2 rounded-md px-3 py-2 cursor-pointer text-sm transition-colors ${
        isActive
          ? 'bg-accent text-accent-foreground'
          : 'hover:bg-accent/50'
      }`}
      onClick={() => {
        if (isStreaming) {
          toast.warning('请等待当前回答完成');
          return;
        }
        onSelect(item.id);
      }}
    >
      <div className="flex-1 min-w-0">
        {isRenaming ? (
          <input
            ref={renameRef}
            value={renameValue}
            onChange={(e) => setRenameValue(e.target.value)}
            onBlur={handleRenameSubmit}
            onKeyDown={handleRenameKeyDown}
            className="w-full bg-background border rounded px-1 py-0.5 text-sm outline-none focus:ring-1 focus:ring-ring"
            onClick={(e) => e.stopPropagation()}
          />
        ) : (
          <>
            <div className="truncate font-medium">{item.title}</div>
            <div className="text-xs text-muted-foreground mt-0.5">
              {formatRelativeTime(item.updated_at)}
              {item.message_count > 0 && ` · ${item.message_count}条消息`}
            </div>
          </>
        )}
      </div>

      {/* 三点菜单按钮 */}
      {!isRenaming && (
        <div
          className="relative opacity-0 group-hover:opacity-100 transition-opacity shrink-0"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Menu toggle button */}
          <button
            className="p-1 rounded hover:bg-accent/80"
            onClick={() => setMenuOpen(!menuOpen)}
          >
            <MoreVertical className="h-4 w-4" />
          </button>

          {/* Dropdown menu */}
          {menuOpen && (
            <div className="absolute right-0 mt-1 w-36 bg-popover border rounded-md shadow-md z-50 py-1">
              <button
                className="w-full text-left px-3 py-1.5 text-sm hover:bg-accent/50"
                onClick={() => {
                  setMenuOpen(false);
                  setRenameValue(item.title);
                  setIsRenaming(true);
                }}
              >
                重命名
              </button>
              <button
                className="w-full text-left px-3 py-1.5 text-sm hover:bg-accent/50"
                onClick={async () => {
                  setMenuOpen(false);
                  try {
                    if (item.pinned) {
                      await onUnpin(item.id);
                    } else {
                      await onPin(item.id);
                    }
                  } catch (err) {
                    const msg = err instanceof Error ? err.message : (item.pinned ? '取消置顶失败' : '置顶失败');
                    toast.error(msg);
                  }
                }}
              >
                {item.pinned ? '取消置顶' : '置顶'}
              </button>
              <button
                className="w-full text-left px-3 py-1.5 text-sm text-destructive hover:bg-accent/50"
                onClick={() => {
                  setMenuOpen(false);
                  setDeleteOpen(true);
                }}
              >
                删除
              </button>
            </div>
          )}
        </div>
      )}

      {/* Delete confirmation dialog */}
      {deleteOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-background border rounded-lg shadow-lg p-6 max-w-sm mx-4">
            <h3 className="text-lg font-semibold mb-2">确定删除这条对话？</h3>
            <p className="text-sm text-muted-foreground mb-4">删除后不可恢复。</p>
            <div className="flex justify-end gap-2">
              <button
                className="px-4 py-2 text-sm rounded-md border hover:bg-accent/50"
                onClick={() => setDeleteOpen(false)}
              >
                取消
              </button>
              <button
                className="px-4 py-2 text-sm rounded-md bg-destructive text-white hover:bg-red-700"
                onClick={handleDelete}
              >
                确认删除
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
