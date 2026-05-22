import { describe, it, expect, beforeEach, vi } from 'vitest';
import { loadMessages, saveMessages } from '../../chat/use-chat-storage';
import type { Message } from '../../chat/types';

// localStorage mock for Vitest node environment
const store: Record<string, string> = {};

beforeEach(() => {
  // Reset store and stub localStorage
  Object.keys(store).forEach((k) => delete store[k]);
  const ls = {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => {
      store[key] = value;
    },
    removeItem: (key: string) => {
      delete store[key];
    },
    clear: () => {
      Object.keys(store).forEach((k) => delete store[k]);
    },
    get length() {
      return Object.keys(store).length;
    },
    key: (_index: number) => null,
  };
  vi.stubGlobal('localStorage', ls);
});

describe('use-chat-storage', () => {
  it('读写正常', () => {
    const messages: Message[] = [
      {
        id: '1',
        role: 'user',
        content: 'hello',
        status: 'done',
        timestamp: 1000,
      },
      {
        id: '2',
        role: 'ai',
        content: 'world',
        status: 'done',
        sources: [
          {
            chunk_id: 'c1',
            book: 'book1',
            section: 's1',
            page_start: 1,
            page_end: 5,
          },
        ],
        timestamp: 1001,
      },
    ];

    saveMessages(messages);
    const loaded = loadMessages();
    expect(loaded).toEqual(messages);
  });

  it('数据损坏返回空', () => {
    localStorage.setItem('octotutor-chat-messages', '{invalid json!!!');
    const loaded = loadMessages();
    expect(loaded).toEqual([]);
  });
});
