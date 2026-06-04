---
version: "1.0"
type: tasks
topic: sidebar-ux-polish
requirement_cycle: R014
workflow:
  evaluate_provider: local
  mode: auto
status: archived
---

# 侧边栏体验修复 — 任务清单

全局约束：纯前端改动，只修改 `conversation-item-card.tsx` 一个文件，不涉及后端。

---

## 执行顺序

1. ✅ FF001 — scrollIntoView 滚动到选中项（无依赖）
2. ✅ FF002 — 菜单碰撞检测自动上翻（无依赖）

---

## R014-FF001：scrollIntoView 滚动到选中项 `✅ 已完成`

- 文件：`frontend/src/components/conversation-item-card.tsx`（修改）
- 改动类型：修改
- domain: ui
- task_layer: foundation
- depends_on: []
- priority: 4
- risk_tags: []
- smoke_required: false
- mode: direct
- status: pending
- acceptance_criteria:
  - 刷新页面后，侧边栏自动滚动到当前选中的对话项（高亮可见）
  - 切换对话时，侧边栏 smooth 滚动到目标项
  - 初始化阶段使用 instant 滚动（无动画）
  - 不影响现有功能（点击选择、流式阻止等）
- test_tasks:
  - type: unit
    description: 验证 scrollIntoView 调用时机和参数
    scenarios: ["isActive=true 首次触发 scrollIntoView", "isActive 不变不重复触发"]
- contract_refs: []
- decision_refs: []
- blocked_files: []

### FF001.1 添加 ref 和 scrollIntoView useEffect `⬜`

给 `ConversationItemCard` 根元素添加 ref，用 useEffect 监听 `isActive`：

```typescript
const cardRef = useRef<HTMLDivElement>(null);

// 初始化：instant 滚动到选中项
// 切换：smooth 滚动
useEffect(() => {
  if (!isActive || !cardRef.current) return;
  cardRef.current.scrollIntoView({ block: 'nearest', behavior: 'instant' });
}, [isActive]);
```

注意：先用 `instant` 实现基本功能，后续如需切换时 smooth 滚动可改为根据 mounted 状态区分。

### FF001.2 根元素绑定 ref `⬜`

```tsx
<div ref={cardRef} className={`group flex items-center ...`}>
```

---

## R014-FF002：菜单碰撞检测自动上翻 `✅ 已完成`

- 文件：`frontend/src/components/conversation-item-card.tsx`（修改）
- 改动类型：修改
- domain: ui
- task_layer: foundation
- depends_on: []
- priority: 3
- risk_tags: []
- smoke_required: false
- mode: direct
- status: pending
- acceptance_criteria:
  - 对话项在列表下半部分时，菜单向上展开，完整可见
  - 对话项在列表上半部分时，菜单向下展开（默认行为不变）
  - 菜单项（重命名/置顶/删除）始终完全可见，不被裁剪
- test_tasks:
  - type: unit
    description: 验证碰撞检测逻辑
    scenarios: ["底部项 → 向上展开", "顶部项 → 向下展开"]
- contract_refs: []
- decision_refs: []
- blocked_files: []

### FF002.1 添加 menuDirection state 和碰撞检测 `⬜`

```typescript
const [menuDirection, setMenuDirection] = useState<'down' | 'up'>('down');

useLayoutEffect(() => {
  if (!menuOpen || !cardRef.current) return;
  const cardRect = cardRef.current.getBoundingClientRect();
  // 找到滚动容器（overflow-y-auto 的父元素）
  const container = cardRef.current.closest('[class*="overflow-y-auto"]');
  if (!container) return;
  const containerRect = container.getBoundingClientRect();
  // 菜单高度约 120px（3 项），判断是否超出容器底部
  const menuHeight = 120;
  const wouldOverflow = cardRect.bottom + menuHeight > containerRect.bottom;
  setMenuDirection(wouldOverflow ? 'up' : 'down');
}, [menuOpen]);
```

### FF002.2 菜单 CSS 根据方向切换 `⬜`

将菜单容器的 className 从固定 `mt-1` 改为动态：

```tsx
<div className={`absolute right-0 z-50 w-36 bg-popover border rounded-md shadow-md py-1 ${
  menuDirection === 'down' ? 'top-full mt-1' : 'bottom-full mb-1'
}`}>
```

### FF002.3 点击外部关闭菜单 `⬜`

当前菜单只能通过点击菜单项关闭。添加点击外部关闭逻辑，避免菜单常驻：

```typescript
useEffect(() => {
  if (!menuOpen) return;
  const handleClickOutside = (e: MouseEvent) => {
    if (cardRef.current && !cardRef.current.contains(e.target as Node)) {
      setMenuOpen(false);
    }
  };
  document.addEventListener('mousedown', handleClickOutside);
  return () => document.removeEventListener('mousedown', handleClickOutside);
}, [menuOpen]);
```
