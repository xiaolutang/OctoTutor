'use client';

import { useState } from 'react';
import { ChevronDown, ChevronRight, Loader2 } from 'lucide-react';
import type { ThinkingStep } from '@/chat/types';

interface ThinkingProcessProps {
  steps: ThinkingStep[];
  isStreaming?: boolean;
}

export function ThinkingProcess({ steps, isStreaming = false }: ThinkingProcessProps) {
  const [expanded, setExpanded] = useState(false);

  const stepCount = steps.length;
  const titleText = isStreaming ? '思考中...' : `思考过程（${stepCount} 步）`;

  return (
    <div className="rounded-lg border border-border bg-muted/50">
      {/* 标题栏 — 点击切换折叠 */}
      <button
        onClick={() => setExpanded((prev) => !prev)}
        className="flex w-full items-center gap-1.5 px-3 py-2 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
      >
        {expanded ? (
          <ChevronDown className="h-3.5 w-3.5 shrink-0" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 shrink-0" />
        )}
        {isStreaming && (
          <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" />
        )}
        <span>{titleText}</span>
      </button>

      {/* 内容区 — 展开时显示步骤列表 */}
      {expanded && (
        <div className="border-t border-border px-4 py-2">
          <ol className="space-y-1.5">
            {steps.map((step) => (
              <li key={step.index} className="flex items-start gap-2 text-xs text-muted-foreground">
                <span className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[10px] font-semibold text-primary">
                  {step.index + 1}
                </span>
                <span className="leading-relaxed">{step.text}</span>
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}
