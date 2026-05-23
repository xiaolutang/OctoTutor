/**
 * FB001 ThinkingProcess 纯逻辑测试
 *
 * 测试 ThinkingProcess 的折叠/展开逻辑（纯函数模拟）
 * 以及 message-bubble 中条件渲染逻辑
 */
import { describe, it, expect } from 'vitest';
import type { ThinkingStep, Message } from '@/chat/types';

// ============================================================
// 模拟 ThinkingProcess 逻辑（纯函数）
// ============================================================

interface ThinkingProcessState {
  expanded: boolean;
  steps: ThinkingStep[];
  isStreaming: boolean;
}

function createThinkingProcessState(
  steps: ThinkingStep[],
  isStreaming = false,
): ThinkingProcessState {
  return { expanded: false, steps, isStreaming };
}

function toggleExpanded(state: ThinkingProcessState): ThinkingProcessState {
  return { ...state, expanded: !state.expanded };
}

function shouldRender(state: ThinkingProcessState): boolean {
  return state.steps.length > 0;
}

function getTitleText(state: ThinkingProcessState): string {
  if (state.isStreaming) return '思考中...';
  return `思考过程（${state.steps.length} 步）`;
}

// ============================================================
// 模拟 MessageBubble 条件渲染逻辑（纯函数）
// ============================================================

function shouldRenderThinkingInBubble(message: Message): boolean {
  return (
    message.role === 'ai' &&
    !!message.thinkingSteps &&
    message.thinkingSteps.length > 0
  );
}

// ============================================================
// 测试数据
// ============================================================

const mockSteps: ThinkingStep[] = [
  { text: '分析用户问题中的关键词', index: 0 },
  { text: '检索相关知识点', index: 1 },
  { text: '组织回答结构', index: 2 },
];

// ============================================================
// ThinkingProcess 折叠/展开测试
// ============================================================

describe('ThinkingProcess 逻辑', () => {
  it('should default to collapsed (expanded=false)', () => {
    const state = createThinkingProcessState(mockSteps);
    expect(state.expanded).toBe(false);
  });

  it('should expand on first toggle', () => {
    const state = createThinkingProcessState(mockSteps);
    const toggled = toggleExpanded(state);
    expect(toggled.expanded).toBe(true);
  });

  it('should collapse on second toggle', () => {
    const state = createThinkingProcessState(mockSteps);
    const expanded = toggleExpanded(state);
    const collapsed = toggleExpanded(expanded);
    expect(collapsed.expanded).toBe(false);
  });

  it('should render when steps exist', () => {
    const state = createThinkingProcessState(mockSteps);
    expect(shouldRender(state)).toBe(true);
  });

  it('should not render when steps empty', () => {
    const state = createThinkingProcessState([]);
    expect(shouldRender(state)).toBe(false);
  });

  it('should show streaming title when isStreaming=true', () => {
    const state = createThinkingProcessState(mockSteps, true);
    expect(getTitleText(state)).toBe('思考中...');
  });

  it('should show step count title when not streaming', () => {
    const state = createThinkingProcessState(mockSteps, false);
    expect(getTitleText(state)).toBe('思考过程（3 步）');
  });

  it('should preserve steps data through toggles', () => {
    const state = createThinkingProcessState(mockSteps);
    const toggled = toggleExpanded(state);
    expect(toggled.steps).toEqual(mockSteps);
    expect(toggled.steps).toHaveLength(3);
  });

  it('should handle single step correctly', () => {
    const singleStep = [mockSteps[0]];
    const state = createThinkingProcessState(singleStep);
    expect(getTitleText(state)).toBe('思考过程（1 步）');
    expect(shouldRender(state)).toBe(true);
  });
});

// ============================================================
// MessageBubble 条件渲染测试
// ============================================================

describe('MessageBubble 条件渲染 ThinkingProcess', () => {
  it('should render when AI message has thinkingSteps', () => {
    const message: Message = {
      id: 'm1',
      role: 'ai',
      content: '回答内容',
      status: 'done',
      thinkingSteps: mockSteps,
      timestamp: Date.now(),
    };
    expect(shouldRenderThinkingInBubble(message)).toBe(true);
  });

  it('should not render when AI message has no thinkingSteps', () => {
    const message: Message = {
      id: 'm2',
      role: 'ai',
      content: '回答内容',
      status: 'done',
      timestamp: Date.now(),
    };
    expect(shouldRenderThinkingInBubble(message)).toBe(false);
  });

  it('should not render when AI message has empty thinkingSteps', () => {
    const message: Message = {
      id: 'm3',
      role: 'ai',
      content: '回答内容',
      status: 'done',
      thinkingSteps: [],
      timestamp: Date.now(),
    };
    expect(shouldRenderThinkingInBubble(message)).toBe(false);
  });

  it('should not render for user message even with thinkingSteps', () => {
    const message: Message = {
      id: 'm4',
      role: 'user',
      content: '用户问题',
      status: 'done',
      thinkingSteps: mockSteps,
      timestamp: Date.now(),
    };
    expect(shouldRenderThinkingInBubble(message)).toBe(false);
  });
});
