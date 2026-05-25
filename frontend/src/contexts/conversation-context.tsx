'use client';

import React, {
  createContext,
  useContext,
  useReducer,
  useCallback,
  useEffect,
  useRef,
} from 'react';
import type { ConversationItem, ConversationListState } from '@/chat/types';
import {
  fetchConversationList,
  patchConversation,
  deleteConversation as deleteConversationApi,
} from '@/chat/use-conversation-list';
import { useAuth } from '@/contexts/auth-context';

// ---------------------------------------------------------------------------
// Reducer
// ---------------------------------------------------------------------------

type ConversationAction =
  | { type: 'SET_LOADING'; payload: boolean }
  | {
      type: 'INIT_LIST';
      payload: { items: ConversationItem[]; cursor: string | null; hasMore: boolean };
    }
  | { type: 'SET_ACTIVE'; payload: string | null }
  | { type: 'SET_NEW_CONVERSATION'; payload: boolean }
  | { type: 'INSERT_NEW'; payload: ConversationItem }
  | { type: 'UPDATE_TITLE'; payload: { id: string; title: string } }
  | {
      type: 'APPEND_PAGE';
      payload: { items: ConversationItem[]; cursor: string | null; hasMore: boolean };
    }
  | { type: 'REMOVE_ITEM'; payload: string }
  | { type: 'UPDATE_ITEM'; payload: ConversationItem };

const STORAGE_KEY = 'octotutor_active_conversation_id';

function getStoredActiveId(): string | null {
  try {
    const v = sessionStorage.getItem(STORAGE_KEY);
    if (!v || v === 'undefined' || v === 'null') return null;
    return v;
  } catch {
    return null;
  }
}

function storeActiveId(id: string | null): void {
  try {
    if (id) {
      sessionStorage.setItem(STORAGE_KEY, id);
    } else {
      sessionStorage.removeItem(STORAGE_KEY);
    }
  } catch {
    // ignore
  }
}

const initialState: ConversationListState = {
  items: [],
  cursor: null,
  hasMore: false,
  isLoading: false,
  isInitialized: false,
  activeId: null,
  isNewConversation: false,
};

function conversationReducer(
  state: ConversationListState,
  action: ConversationAction,
): ConversationListState {
  switch (action.type) {
    case 'SET_LOADING':
      return { ...state, isLoading: action.payload };
    case 'INIT_LIST':
      return {
        ...state,
        items: action.payload.items,
        cursor: action.payload.cursor,
        hasMore: action.payload.hasMore,
        isInitialized: true,
        isLoading: false,
      };
    case 'SET_ACTIVE':
      storeActiveId(action.payload);
      return { ...state, activeId: action.payload, isNewConversation: false };
    case 'SET_NEW_CONVERSATION':
      return { ...state, isNewConversation: action.payload, activeId: null };
    case 'INSERT_NEW':
      return {
        ...state,
        items: [action.payload, ...state.items],
        activeId: action.payload.id,
        isNewConversation: false,
      };
    case 'UPDATE_TITLE':
      return {
        ...state,
        items: state.items.map((item) =>
          item.id === action.payload.id
            ? { ...item, title: action.payload.title }
            : item,
        ),
      };
    case 'APPEND_PAGE':
      return {
        ...state,
        items: [...state.items, ...action.payload.items],
        cursor: action.payload.cursor,
        hasMore: action.payload.hasMore,
      };
    case 'REMOVE_ITEM':
      return {
        ...state,
        items: state.items.filter((item) => item.id !== action.payload),
      };
    case 'UPDATE_ITEM':
      return {
        ...state,
        items: state.items.map((item) =>
          item.id === action.payload.id ? action.payload : item,
        ),
      };
    default:
      return state;
  }
}

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
  const [isStreaming, setIsStreaming] = React.useState(false);
  const loadingMoreRef = useRef(false);

  // 初始化加载对话列表
  useEffect(() => {
    let cancelled = false;
    (async () => {
      dispatch({ type: 'SET_LOADING', payload: true });
      try {
        const result = await fetchConversationList(undefined, 20);
        if (!cancelled) {
          dispatch({ type: 'INIT_LIST', payload: result });
          // 如果存储的 activeId 不在列表中，清除它
          if (state.activeId && !result.items.some((i) => i.id === state.activeId)) {
            dispatch({ type: 'SET_ACTIVE', payload: null });
          }
        }
      } catch {
        if (!cancelled) {
          dispatch({ type: 'SET_LOADING', payload: false });
        }
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const switchTo = useCallback((id: string) => {
    dispatch({ type: 'SET_ACTIVE', payload: id });
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
    try {
      const updated = await patchConversation(id, { pinned: true });
      dispatch({ type: 'UPDATE_ITEM', payload: updated });
    } catch {
      // 错误已在 patchConversation 中抛出，调用方负责 toast
      throw new Error('置顶失败');
    }
  }, []);

  const unpinConversation = useCallback(async (id: string) => {
    try {
      const updated = await patchConversation(id, { pinned: false });
      dispatch({ type: 'UPDATE_ITEM', payload: updated });
    } catch {
      throw new Error('取消置顶失败');
    }
  }, []);

  const deleteConversation = useCallback(
    async (id: string) => {
      await deleteConversationApi(id);
      dispatch({ type: 'REMOVE_ITEM', payload: id });
      // 删除当前 activeId 对话后，自动切换到列表第一个
      if (state.activeId === id) {
        const remaining = state.items.filter((i) => i.id !== id);
        dispatch({
          type: 'SET_ACTIVE',
          payload: remaining.length > 0 ? remaining[0].id : null,
        });
      }
    },
    [state.activeId, state.items],
  );

  const value: ConversationContextValue = {
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
  };

  return (
    <ConversationContext.Provider value={value}>{children}</ConversationContext.Provider>
  );
}
