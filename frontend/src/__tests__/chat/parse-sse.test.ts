import { describe, it, expect } from 'vitest';
import { parseSSEEvents } from '../../chat/parse-sse';

describe('parseSSEEvents', () => {
  it('完整事件解析', () => {
    const chunk = 'event: status\ndata: {"stage":"retrieving","message":"..."}\n\n';
    const { events, remaining } = parseSSEEvents(chunk, '');
    expect(events).toHaveLength(1);
    expect(events[0].type).toBe('status');
    expect(events[0].data).toEqual({ stage: 'retrieving', message: '...' });
    expect(remaining).toBe('');
  });

  it('不完整 chunk 保留', () => {
    const chunk = 'event: status\n';
    const { events, remaining } = parseSSEEvents(chunk, '');
    expect(events).toHaveLength(0);
    expect(remaining).toBe('event: status\n');
  });

  it('多事件合并解析', () => {
    const chunk =
      'event: status\ndata: {"stage":"retrieving","message":"..."}\n\n' +
      'event: token\ndata: {"token":"hello"}\n\n';
    const { events, remaining } = parseSSEEvents(chunk, '');
    expect(events).toHaveLength(2);
    expect(events[0].type).toBe('status');
    expect(events[1].type).toBe('token');
    expect(events[1].data).toEqual({ token: 'hello' });
    expect(remaining).toBe('');
  });

  it('data=null 处理', () => {
    const chunk = 'event: done\ndata: null\n\n';
    const { events } = parseSSEEvents(chunk, '');
    expect(events).toHaveLength(1);
    expect(events[0].data).toBeNull();
  });
});
