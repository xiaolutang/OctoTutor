/**
 * FB002 SourceCard 纯逻辑测试
 *
 * 测试 SourceCard 的展开/收起逻辑（纯函数模拟）
 */
import { describe, it, expect } from 'vitest';
import type { SourceReference } from '@/chat/types';

// ============================================================
// 模拟 SourceCard 逻辑（纯函数）
// ============================================================

interface SourceCardState {
  expanded: boolean;
  sources: SourceReference[];
}

function createSourceCardState(sources: SourceReference[]): SourceCardState {
  return { expanded: false, sources };
}

function toggleExpanded(state: SourceCardState): SourceCardState {
  return { ...state, expanded: !state.expanded };
}

function shouldRender(state: SourceCardState): boolean {
  return state.sources.length > 0;
}

function getToggleLabel(state: SourceCardState): string {
  return state.expanded ? '收起来源' : `查看来源 (${state.sources.length})`;
}

// ============================================================
// 测试数据
// ============================================================
const mockSources: SourceReference[] = [
  {
    chunk_id: 'c1',
    book: '高等数学',
    section: '第三章 微分',
    page_start: 45,
    page_end: 47,
  },
  {
    chunk_id: 'c2',
    book: '线性代数',
    section: '第二章 矩阵',
    page_start: 30,
    page_end: 30,
  },
];

// ============================================================
// 测试用例
// ============================================================
describe('SourceCard 逻辑', () => {
  it('should default to collapsed (expanded=false)', () => {
    const state = createSourceCardState(mockSources);
    expect(state.expanded).toBe(false);
  });

  it('should expand on toggle (expanded=true)', () => {
    const state = createSourceCardState(mockSources);
    const toggled = toggleExpanded(state);
    expect(toggled.expanded).toBe(true);
  });

  it('should collapse on second toggle', () => {
    const state = createSourceCardState(mockSources);
    const expanded = toggleExpanded(state);
    const collapsed = toggleExpanded(expanded);
    expect(collapsed.expanded).toBe(false);
  });

  it('should render when sources exist', () => {
    const state = createSourceCardState(mockSources);
    expect(shouldRender(state)).toBe(true);
  });

  it('should not render when sources empty', () => {
    const state = createSourceCardState([]);
    expect(shouldRender(state)).toBe(false);
  });

  it('should show correct label when collapsed', () => {
    const state = createSourceCardState(mockSources);
    expect(getToggleLabel(state)).toBe('查看来源 (2)');
  });

  it('should show correct label when expanded', () => {
    const state = toggleExpanded(createSourceCardState(mockSources));
    expect(getToggleLabel(state)).toBe('收起来源');
  });

  it('should preserve sources data through toggles', () => {
    const state = createSourceCardState(mockSources);
    const toggled = toggleExpanded(state);
    expect(toggled.sources).toEqual(mockSources);
    expect(toggled.sources).toHaveLength(2);
  });

  it('should handle single source correctly', () => {
    const singleSource = [mockSources[0]];
    const state = createSourceCardState(singleSource);
    expect(getToggleLabel(state)).toBe('查看来源 (1)');
    expect(shouldRender(state)).toBe(true);
  });
});
