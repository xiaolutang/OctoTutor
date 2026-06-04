'use client';

import React, {
  createContext,
  useContext,
  useReducer,
  useCallback,
  useEffect,
  useMemo,
  useRef,
} from 'react';
import type { ConversationItem, ConversationListState } from '@/chat/types';
import {
  conversationReducer,
  initialState,
  getStoredActiveId,
} from '@/chat/conversation-reducer';
import {
  fetchConversationList,
  patchConversation,
  deleteConversation as deleteConversationApi,
} from '@/chat/use-conversation-list';
import { useAuth } from '@/contexts/auth-context';

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

interface ConversationContextValue extends ConversationListState {
  isStreaming: boolean;
  setIsStreaming: (v: boolean) => void;
  switchTo: (id: string) => void;
  createNew: () => void;
  insertNewConversation: (item: ConversationItem) => void;
  updateTitle: (id: string, title: string) => void;
  loadMore: () => Promise<void>;
  removeConversation: (id: string) => void;
  renameConversation: (id: string, title: string) => Promise<void>;
  pinConversation: (id: string) => Promise<void>;
  unpinConversation: (id: string) => Promise<void>;
  deleteConversation: (id: string) => Promise<void>;
  registerSwitchHandler: (handler: ((id: string) => Promise<void>) | null) => void;
}

const ConversationContext = createContext<ConversationContextValue | null>(null);

export function useConversationContext(): ConversationContextValue {
  const ctx = useContext(ConversationContext);
  if (!ctx) {
    throw new Error('useConversationContext must be used within ConversationProvider');
  }
  return ctx;
}

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

export function ConversationProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(conversationReducer, {
    ...initialState,
    activeId: getStoredActiveId(),
  });
  const { isInitialized } = useAuth();
  const [isStreaming, setIsStreaming] = React.useState(false);
  const loadingMoreRef = useRef(false);
  const switchHandlerRef = useRef<((id: string) => Promise<void>) | null>(null);

  // 初始化加载对话列表
  useEffect(() => {
    if (!isInitialized) return;
    let cancelled = false;
    (async () => {
      dispatch({ type: 'SET_LOADING', payload: true });
      try {
        const result = await fetchConversationList(undefined, 20);
        if (!cancelled) {
          dispatch({ type: 'INIT_LIST', payload: result });
          const storedId = getStoredActiveId();
          if (storedId && result.items.some((i) => i.id === storedId)) {
            dispatch({ type: 'SET_ACTIVE', payload: storedId });
          } else if (result.items.length > 0) {
            dispatch({ type: 'SET_ACTIVE', payload: result.items[0].id });
          } else {
            dispatch({ type: 'SET_ACTIVE', payload: null });
          }
        }
      } catch {
        if (!cancelled) {
          dispatch({ type: 'INIT_LIST', payload: { items: [], cursor: null, hasMore: false } });
          dispatch({ type: 'SET_ACTIVE', payload: null });
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isInitialized]);

  const switchTo = useCallback((id: string) => {
    dispatch({ type: 'SET_ACTIVE', payload: id });
    switchHandlerRef.current?.(id);
  }, []);

  const createNew = useCallback(() => {
    dispatch({ type: 'SET_NEW_CONVERSATION', payload: true });
  }, []);

  const insertNewConversation = useCallback((item: ConversationItem) => {
    dispatch({ type: 'INSERT_NEW', payload: item });
  }, []);

  const updateTitle = useCallback((id: string, title: string) => {
    dispatch({ type: 'UPDATE_TITLE', payload: { id, title } });
  }, []);

  const loadMore = useCallback(async () => {
    if (loadingMoreRef.current || !state.hasMore || !state.cursor) return;
    loadingMoreRef.current = true;
    try {
      const result = await fetchConversationList(state.cursor, 20);
      dispatch({ type: 'APPEND_PAGE', payload: result });
    } catch {
      // silent
    } finally {
      loadingMoreRef.current = false;
    }
  }, [state.hasMore, state.cursor]);

  const removeConversation = useCallback((id: string) => {
    dispatch({ type: 'REMOVE_ITEM', payload: id });
  }, []);

  const renameConversation = useCallback(
    async (id: string, title: string) => {
      const updated = await patchConversation(id, { title });
      dispatch({ type: 'UPDATE_ITEM', payload: updated });
    },
    [],
  );

  const pinConversation = useCallback(async (id: string) => {
    const updated = await patchConversation(id, { pinned: true });
    dispatch({ type: 'UPDATE_ITEM', payload: updated });
  }, []);

  const unpinConversation = useCallback(async (id: string) => {
    const updated = await patchConversation(id, { pinned: false });
    dispatch({ type: 'UPDATE_ITEM', payload: updated });
  }, []);

  const deleteConversation = useCallback(async (id: string) => {
    await deleteConversationApi(id);
    dispatch({ type: 'REMOVE_ITEM', payload: id });
  }, []);

  const registerSwitchHandler = useCallback((handler: ((id: string) => Promise<void>) | null) => {
    switchHandlerRef.current = handler;
  }, []);

  const value: ConversationContextValue = useMemo(
    () => ({
      ...state,
      isStreaming,
      setIsStreaming,
      switchTo,
      createNew,
      insertNewConversation,
      updateTitle,
      loadMore,
      removeConversation,
      renameConversation,
      pinConversation,
      unpinConversation,
      deleteConversation,
      registerSwitchHandler,
    }),
    [state, isStreaming, switchTo, createNew, insertNewConversation, updateTitle, loadMore, removeConversation, renameConversation, pinConversation, unpinConversation, deleteConversation, registerSwitchHandler],
  );

  return (
    <ConversationContext.Provider value={value}>{children}</ConversationContext.Provider>
  );
}
