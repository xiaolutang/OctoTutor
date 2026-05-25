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
      // 新对话 pinned=false，插入到普通区头部（置顶区之后）
      {
        const pinned = state.items.filter((i) => i.pinned);
        const normal = state.items.filter((i) => !i.pinned);
        return {
          ...state,
          items: [...pinned, action.payload, ...normal],
          activeId: action.payload.id,
          isNewConversation: false,
        };
      }
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
      {
        const remaining = state.items.filter((item) => item.id !== action.payload);
        const newActiveId = state.activeId === action.payload
          ? (remaining.length > 0 ? remaining[0].id : null)
          : state.activeId;
        if (newActiveId !== state.activeId) {
          storeActiveId(newActiveId);
        }
        return { ...state, items: remaining, activeId: newActiveId, isNewConversation: newActiveId ? false : state.isNewConversation };
      }
    case 'UPDATE_ITEM':
      // 更新后重新排序：置顶的移到置顶区顶部，普通的移到普通区顶部
      {
        const updated = action.payload;
        const rest = state.items.filter((item) => item.id !== updated.id);
        if (updated.pinned) {
          const pinned = rest.filter((i) => i.pinned);
          const normal = rest.filter((i) => !i.pinned);
          return { ...state, items: [updated, ...pinned, ...normal] };
        }
        const pinned = rest.filter((i) => i.pinned);
        const normal = rest.filter((i) => !i.pinned);
        return { ...state, items: [...pinned, updated, ...normal] };
      }
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
