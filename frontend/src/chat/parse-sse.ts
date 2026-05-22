export interface SSEEvent {
  type: string;
  data: unknown;
}

export function parseSSEEvents(
  chunk: string,
  remaining: string,
): { events: SSEEvent[]; remaining: string } {
  const buffer = remaining + chunk;
  const parts = buffer.split('\n\n');
  const events: SSEEvent[] = [];
  const newRemaining = parts.pop() || '';

  for (const part of parts) {
    if (!part.trim()) continue;
    let type = '';
    let data = '';
    for (const line of part.split('\n')) {
      if (line.startsWith('event: ')) type = line.slice(7);
      else if (line.startsWith('data: ')) data = line.slice(6);
    }
    if (type) {
      events.push({
        type,
        data: data === 'null' ? null : JSON.parse(data),
      });
    }
  }
  return { events, remaining: newRemaining };
}
