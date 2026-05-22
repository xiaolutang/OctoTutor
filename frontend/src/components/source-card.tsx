'use client';

import { useState } from 'react';
import type { SourceReference } from '@/chat/types';

interface SourceCardProps {
  sources: SourceReference[];
}

export function SourceCard({ sources }: SourceCardProps) {
  const [expanded, setExpanded] = useState(false);

  if (!sources || sources.length === 0) return null;

  return (
    <div className="mt-2 border-t border-border/50 pt-2">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
      >
        <svg
          className={`h-3 w-3 transition-transform ${expanded ? 'rotate-90' : ''}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
        </svg>
        <span>查看来源 ({sources.length})</span>
      </button>

      {expanded && (
        <div className="mt-1.5 space-y-1">
          {sources.map((src, i) => (
            <div
              key={src.chunk_id || i}
              className="rounded bg-background/50 px-2 py-1 text-xs text-muted-foreground"
            >
              <span className="font-medium text-foreground">{src.book}</span>
              {' - '}
              <span>{src.section}</span>
              {' (p.'}
              {src.page_start === src.page_end
                ? src.page_start
                : `${src.page_start}-${src.page_end}`}
              {')'}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
