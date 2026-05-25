'use client';

import { useRef, useCallback } from 'react';
import { Plus } from 'lucide-react';
import { useConversationContext } from '@/contexts/conversation-context';
import { ConversationItemCard } from '@/components/conversation-item-card';

export function ConversationSidebar() {
  const {
    items,
    activeId,
    hasMore,
    isStreaming,
    switchTo,
    createNew,
    loadMore,
    renameConversation,
    pinConversation,
    unpinConversation,
    deleteConversation,
  } = useConversationContext();

  const scrollRef = useRef<HTMLDivElement>(null);

  const handleScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    if (el.scrollTop + el.clientHeight >= el.scrollHeight - 50) {
      loadMore();
    }
  }, [loadMore]);

  const pinnedItems = items.filter((i) => i.pinned);
  const normalItems = items.filter((i) => !i.pinned);

  return (
    <div className="flex h-full flex-col">
      {/* 新建对话按钮 */}
      <div className="p-3">
        <button
          className="flex w-full items-center justify-center gap-2 rounded-md border px-3 py-2 text-sm font-medium hover:bg-accent/50 transition-colors"
          onClick={createNew}
        >
          <Plus className="h-4 w-4" />
          新建对话
        </button>
      </div>

      {/* 对话列表 */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto px-2"
        onScroll={handleScroll}
      >
        {items.length === 0 && (
          <div className="flex items-center justify-center py-8 text-sm text-muted-foreground">
            暂无对话
          </div>
        )}

        {/* 置顶区 */}
        {pinnedItems.length > 0 && (
          <div className="mb-2">
            <div className="px-2 py-1 text-xs font-medium text-muted-foreground">
              📌 已置顶
            </div>
            {pinnedItems.map((item) => (
              <ConversationItemCard
                key={item.id}
                item={item}
                isActive={activeId === item.id}
                onSelect={switchTo}
                onRename={renameConversation}
                onPin={pinConversation}
                onUnpin={unpinConversation}
                onDelete={deleteConversation}
                isStreaming={isStreaming}
              />
            ))}
          </div>
        )}

        {/* 普通区 */}
        {normalItems.map((item) => (
          <ConversationItemCard
            key={item.id}
            item={item}
            isActive={activeId === item.id}
            onSelect={switchTo}
            onRename={renameConversation}
            onPin={pinConversation}
            onUnpin={unpinConversation}
            onDelete={deleteConversation}
            isStreaming={isStreaming}
          />
        ))}

        {/* 加载更多 */}
        {hasMore && (
          <div className="flex items-center justify-center py-3 text-xs text-muted-foreground">
            滚动加载更多...
          </div>
        )}
      </div>
    </div>
  );
}
