import type { ConversationItem, ConversationListState } from '@/chat/types';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type ConversationAction =
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

// ---------------------------------------------------------------------------
// Storage helpers
// ---------------------------------------------------------------------------

const STORAGE_KEY = 'octotutor_active_conversation_id';

export function getStoredActiveId(): string | null {
  try {
    const v = sessionStorage.getItem(STORAGE_KEY);
    if (!v || v === 'undefined' || v === 'null') return null;
    return v;
  } catch {
    return null;
  }
}

export function storeActiveId(id: string | null): void {
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

// ---------------------------------------------------------------------------
// Initial state
// ---------------------------------------------------------------------------

export const initialState: ConversationListState = {
  items: [],
  cursor: null,
  hasMore: false,
  isLoading: false,
  isInitialized: false,
  activeId: null,
  isNewConversation: false,
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function partitionByPinned(items: ConversationItem[]) {
  const pinned: ConversationItem[] = [];
  const normal: ConversationItem[] = [];
  for (const item of items) {
    (item.pinned ? pinned : normal).push(item);
  }
  return { pinned, normal };
}

// ---------------------------------------------------------------------------
// Reducer
// ---------------------------------------------------------------------------

export function conversationReducer(
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
      storeActiveId(null);
      return { ...state, isNewConversation: action.payload, activeId: null };
    case 'INSERT_NEW':
      // 新对话 pinned=false，插入到普通区头部（置顶区之后）
      {
        storeActiveId(action.payload.id);
        const { pinned, normal } = partitionByPinned(state.items);
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
        const { pinned, normal } = partitionByPinned(rest);
        if (updated.pinned) {
          return { ...state, items: [updated, ...pinned, ...normal] };
        }
        return { ...state, items: [...pinned, updated, ...normal] };
      }
    default:
      return state;
  }
}
