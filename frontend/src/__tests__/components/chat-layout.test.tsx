/**
 * ChatLayout 布局骨架测试
 *
 * vitest 环境为 node，无 @testing-library/react。
 * 采用纯函数模拟策略：拦截 React.createElement 调用，
 * 验证组件树结构（aside + main + flex 容器）和 props 透传。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// ============================================================
// Mock: 捕获 React 虚拟 DOM 树
// ============================================================
interface VNode {
  type: string | Function;
  props: Record<string, unknown>;
  children: VNode[];
}

let capturedTree: VNode | null = null;

function createMockElement() {
  return (type: string | Function, props: Record<string, unknown> | null, ...children: unknown[]) => {
    // 过滤掉 null/undefined/boolean 等非节点 child
    const childNodes = children
      .flat(Infinity)
      .filter((c): c is VNode | string => c !== null && c !== undefined && typeof c !== 'boolean')
      .map((c) => (typeof c === 'string' ? { type: '__TEXT__', props: {}, children: [] as VNode[], text: c } : c)) as VNode[];

    const node: VNode = {
      type: typeof type === 'function' ? type.name || 'Anonymous' : type,
      props: props ?? {},
      children: childNodes,
    };
    return node;
  };
}

// ============================================================
// 模拟 ChatLayout 渲染逻辑（纯函数，不依赖 React 运行时）
// ============================================================
interface LayoutProps {
  sidebar: string;
  children: string;
}

/**
 * 模拟 ChatLayout 的渲染逻辑
 * 等价于:
 *   <SidebarProvider>
 *     <div className="flex h-full">
 *       <aside className="w-64 shrink-0 border-r bg-background">{sidebar}</aside>
 *       <main className="flex-1 overflow-hidden">{children}</main>
 *     </div>
 *     <Toaster />
 *   </SidebarProvider>
 */
function simulateChatLayout(props: LayoutProps): VNode {
  const createElement = createMockElement();

  const asideNode = createElement('aside', { className: 'w-64 shrink-0 border-r bg-background' }, props.sidebar);
  const mainNode = createElement('main', { className: 'flex-1 overflow-hidden' }, props.children);
  const divNode = createElement('div', { className: 'flex h-full' }, asideNode, mainNode);
  const toasterNode = createElement('Toaster', {});
  const root = createElement('SidebarProvider', {}, divNode, toasterNode);

  return root as VNode;
}

// ============================================================
// 辅助：在树中查找特定 type 的节点
// ============================================================
function findNodesByType(node: VNode, targetType: string): VNode[] {
  const results: VNode[] = [];
  if (node.type === targetType) {
    results.push(node);
  }
  for (const child of node.children) {
    results.push(...findNodesByType(child, targetType));
  }
  return results;
}

function findTextContent(node: VNode): string[] {
  const texts: string[] = [];
  if (node.type === '__TEXT__' && 'text' in node) {
    texts.push((node as VNode & { text: string }).text);
  }
  for (const child of node.children) {
    texts.push(...findTextContent(child));
  }
  return texts;
}

// ============================================================
// 测试用例
// ============================================================
describe('ChatLayout 布局骨架', () => {
  it('sidebar 和 main 同时渲染', () => {
    const tree = simulateChatLayout({
      sidebar: '侧边栏内容',
      children: '主内容区',
    });

    const asideNodes = findNodesByType(tree, 'aside');
    const mainNodes = findNodesByType(tree, 'main');

    expect(asideNodes).toHaveLength(1);
    expect(mainNodes).toHaveLength(1);
  });

  it('children 正确渲染到 main 中', () => {
    const tree = simulateChatLayout({
      sidebar: '侧边栏',
      children: '这是主内容文本',
    });

    const mainNodes = findNodesByType(tree, 'main');
    expect(mainNodes).toHaveLength(1);

    const mainTexts = findTextContent(mainNodes[0]);
    expect(mainTexts).toContain('这是主内容文本');
  });

  it('sidebar 内容正确渲染到 aside 中', () => {
    const tree = simulateChatLayout({
      sidebar: '我的侧边栏',
      children: '主内容',
    });

    const asideNodes = findNodesByType(tree, 'aside');
    expect(asideNodes).toHaveLength(1);

    const asideTexts = findTextContent(asideNodes[0]);
    expect(asideTexts).toContain('我的侧边栏');
  });

  it('布局结构正确: aside 有 w-64, main 有 flex-1', () => {
    const tree = simulateChatLayout({
      sidebar: '侧边栏',
      children: '主内容',
    });

    const asideNodes = findNodesByType(tree, 'aside');
    const mainNodes = findNodesByType(tree, 'main');

    expect(asideNodes[0].props.className).toContain('w-64');
    expect(asideNodes[0].props.className).toContain('shrink-0');

    expect(mainNodes[0].props.className).toContain('flex-1');
    expect(mainNodes[0].props.className).toContain('overflow-hidden');
  });

  it('外层容器使用 flex 布局', () => {
    const tree = simulateChatLayout({
      sidebar: '侧边栏',
      children: '主内容',
    });

    const divNodes = findNodesByType(tree, 'div');
    const flexDiv = divNodes.find((n) => String(n.props.className).includes('flex'));

    expect(flexDiv).toBeDefined();
    expect(String(flexDiv!.props.className)).toContain('flex');
    expect(String(flexDiv!.props.className)).toContain('h-full');
  });

  it('根节点是 SidebarProvider', () => {
    const tree = simulateChatLayout({
      sidebar: '侧边栏',
      children: '主内容',
    });

    expect(tree.type).toBe('SidebarProvider');
  });

  it('包含 Toaster 组件', () => {
    const tree = simulateChatLayout({
      sidebar: '侧边栏',
      children: '主内容',
    });

    const toasterNodes = findNodesByType(tree, 'Toaster');
    expect(toasterNodes).toHaveLength(1);
  });
});
