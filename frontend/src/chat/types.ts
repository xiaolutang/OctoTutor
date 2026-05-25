export interface SourceReference {
  chunk_id: string;
  book: string;
  section: string;
  page_start: number;
  page_end: number;
}

/** 思考步骤 — SSE thinking 事件携带 */
export interface ThinkingStep {
  text: string;
  index: number;
}

/** 后端消息格式（role 为 human/ai） */
export interface ApiMessage {
  id: string;
  role: 'human' | 'ai';
  content: string;
  status: 'completed' | 'stopped' | 'error';
  sources?: SourceReference[];
  thinking_steps?: ThinkingStep[];
  created_at: string;
}

/** GET /api/conversations/current 响应体 */
export interface ConversationResponse {
  conversation_id: string;
  messages: ApiMessage[];
}

/** 对话列表项（对应后端 GET /api/conversations 响应，保持 snake_case） */
export interface ConversationItem {
  id: string;
  title: string;
  pinned: boolean;
  pinned_at: string | null;
  message_count: number;
  created_at: string;
  updated_at: string;
}

/** 对话列表状态 */
export interface ConversationListState {
  items: ConversationItem[];
  cursor: string | null;
  hasMore: boolean;
  isLoading: boolean;
  isInitialized: boolean;
  activeId: string | null;
  isNewConversation: boolean;
}

export interface SSECallbacks {
  onInit: (conversationId: string) => void;
  onStatus: (stage: string, message: string) => void;
  onSources: (sources: SourceReference[]) => void;
  onToken: (token: string) => void;
  onThinking: (step: ThinkingStep) => void;
  onDone: () => void;
  onTitle: (conversationId: string, title: string) => void;
  onError: (error: { code: string; message: string; action: string }) => void;
}

export type MessageStatus = 'sending' | 'retrieving' | 'generating' | 'done' | 'stopped' | 'error';

export interface Message {
  id: string;
  role: 'user' | 'ai';
  content: string;
  status: MessageStatus;
  sources?: SourceReference[];
  thinkingSteps?: ThinkingStep[];
  error?: { code: string; message: string; action: string };
  timestamp: number;
}
