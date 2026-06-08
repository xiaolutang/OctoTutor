/**
 * getDisplayText / getUserQuestionText 单元测试
 *
 * 覆盖 string / ContentBlock[] / undefined 三种输入的边界场景。
 */
import { describe, it, expect } from 'vitest';
import { getDisplayText, getUserQuestionText } from '@/chat/types';
import type { ContentBlock } from '@/chat/types';

describe('getDisplayText', () => {
  it('should return empty string for undefined', () => {
    expect(getDisplayText(undefined)).toBe('');
  });

  it('should pass through string content', () => {
    expect(getDisplayText('hello world')).toBe('hello world');
  });

  it('should join all text blocks with newline', () => {
    const blocks: ContentBlock[] = [
      { type: 'text', text: '识别结果' },
      { type: 'text', text: '用户问题' },
    ];
    expect(getDisplayText(blocks)).toBe('识别结果\n用户问题');
  });

  it('should filter non-text blocks', () => {
    const blocks = [
      { type: 'image_url' as const, image_url: { url: 'data:...' } },
      { type: 'text' as const, text: '可见文本' },
    ] as ContentBlock[];
    expect(getDisplayText(blocks)).toBe('可见文本');
  });

  it('should return empty string for empty array', () => {
    expect(getDisplayText([])).toBe('');
  });

  it('should return empty string for array with no text blocks', () => {
    const blocks = [
      { type: 'image_url' as const, image_url: { url: 'data:...' } },
    ] as ContentBlock[];
    expect(getDisplayText(blocks)).toBe('');
  });
});

describe('getUserQuestionText', () => {
  it('should return empty string for undefined', () => {
    expect(getUserQuestionText(undefined)).toBe('');
  });

  it('should pass through string content', () => {
    expect(getUserQuestionText('用户问题')).toBe('用户问题');
  });

  it('should return only the last text block', () => {
    const blocks: ContentBlock[] = [
      { type: 'text', text: '以下是用户上传图片的自动识别结果：\n图片内容' },
      { type: 'text', text: '用户原始问题' },
    ];
    expect(getUserQuestionText(blocks)).toBe('用户原始问题');
  });

  it('should return single text block content', () => {
    const blocks: ContentBlock[] = [
      { type: 'text', text: '唯一文本' },
    ];
    expect(getUserQuestionText(blocks)).toBe('唯一文本');
  });

  it('should return empty string for empty array', () => {
    expect(getUserQuestionText([])).toBe('');
  });

  it('should skip non-text blocks when finding last', () => {
    const blocks = [
      { type: 'text' as const, text: '识别文本' },
      { type: 'image_url' as const, image_url: { url: 'data:...' } },
      { type: 'text' as const, text: '用户问题' },
    ] as ContentBlock[];
    expect(getUserQuestionText(blocks)).toBe('用户问题');
  });
});
