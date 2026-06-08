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

/** 图片引用 — 上传/历史消息中的图片 */
export interface ImageRef {
  url: string;       // /api/uploads/{user_id}/{uuid}.{ext}
  image_id: string;  // 服务端 UUID
}

/** content 数组中的文本块（后端 VLM 识别结果 + 用户问题分开存储） */
export interface ContentBlock {
  type: 'text';
  text: string;
}

/** 后端消息格式（role 为 human/ai） */
export interface ApiMessage {
  id: string;
  role: 'human' | 'ai';
  content: string | ContentBlock[];
  status: 'completed' | 'stopped' | 'error';
  sources?: SourceReference[];
  thinking_steps?: ThinkingStep[];
  images?: ImageRef[];
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

export type MessageStatus = 'sending' | 'retrieving' | 'recognizing' | 'generating' | 'done' | 'stopped' | 'error';

/** 将后端 ApiMessage 的 status 映射为前端 MessageStatus */
export function mapApiStatus(status: ApiMessage['status']): MessageStatus {
  switch (status) {
    case 'completed':
      return 'done';
    case 'stopped':
      return 'stopped';
    case 'error':
      return 'error';
    default:
      return 'done';
  }
}

/** 将后端 ApiMessage[] 转换为前端 Message[] */
export function convertApiMessages(apiMsgs: ApiMessage[]): Message[] {
  return apiMsgs.map((apiMsg) => ({
    id: apiMsg.id,
    role: apiMsg.role === 'human' ? ('user' as const) : ('ai' as const),
    content: apiMsg.content,
    status: mapApiStatus(apiMsg.status),
    sources: apiMsg.sources,
    thinkingSteps: apiMsg.thinking_steps,
    images: apiMsg.images,
    timestamp: apiMsg.created_at ? new Date(apiMsg.created_at).getTime() : Date.now(),
  }));
}

export interface Message {
  id: string;
  role: 'user' | 'ai';
  content: string | ContentBlock[];
  status: MessageStatus;
  sources?: SourceReference[];
  thinkingSteps?: ThinkingStep[];
  images?: ImageRef[];
  error?: { code: string; message: string; action: string };
  timestamp: number;
}

// ── 展示映射层 ──────────────────────────────────────────────

/**
 * 从 content 中提取纯文本（展示用）。
 * - string → 原样返回
 * - ContentBlock[] → 拼接所有 text block
 */
export function getDisplayText(content: string | ContentBlock[] | undefined): string {
  if (!content) return '';
  if (typeof content === 'string') return content;
  return content.filter((b) => b.type === 'text').map((b) => b.text).join('\n');
}

/**
 * 从 content 中提取用户问题文本（用户消息展示用）。
 * - string → 原样返回
 * - ContentBlock[] → 只取最后一个 text block（即用户原始输入，前面的 block 是 VLM 识别结果）
 */
export function getUserQuestionText(content: string | ContentBlock[] | undefined): string {
  if (!content) return '';
  if (typeof content === 'string') return content;
  const textBlocks = content.filter((b) => b.type === 'text');
  return textBlocks.length > 0 ? textBlocks[textBlocks.length - 1].text : '';
}
