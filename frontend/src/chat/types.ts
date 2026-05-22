export interface SourceReference {
  chunk_id: string;
  book: string;
  section: string;
  page_start: number;
  page_end: number;
}

export interface SSECallbacks {
  onStatus: (stage: string, message: string) => void;
  onSources: (sources: SourceReference[]) => void;
  onToken: (token: string) => void;
  onDone: () => void;
  onError: (error: { code: string; message: string; action: string }) => void;
}

export type MessageStatus = 'sending' | 'retrieving' | 'generating' | 'done' | 'stopped' | 'error';

export interface Message {
  id: string;
  role: 'user' | 'ai';
  content: string;
  status: MessageStatus;
  sources?: SourceReference[];
  error?: { code: string; message: string; action: string };
  timestamp: number;
}
