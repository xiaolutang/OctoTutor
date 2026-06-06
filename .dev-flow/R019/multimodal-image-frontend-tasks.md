---
version: "1.0"
type: tasks
topic: multimodal-image-frontend
requirement_cycle: R019
workflow:
  evaluate_provider: direct
  mode: auto
status: planned
---

# 多模态图片识别 — 前端任务清单

基于 [analysis](analysis/2026-06-05--multimodal-image.md) 和 [frontend design](analysis/2026-06-05--multimodal-image-frontend.md)。

全局约束：
- 无新增 npm 依赖（lucide-react、sonner 已有）
- 上传用直接 fetch + Bearer token（不走 fetchWithAuth，避免自动 Content-Type）
- 删除用 fetchWithAuth
- api-client.ts 不改
- chat-ui.tsx 不改（只是透传 handleSend）
- 预览区在 textarea 上方（ChatGPT/Claude 模式）

---

## 执行顺序

1. ✅ R019-FF001 — types.ts 类型扩展（无依赖）
2. ✅ R019-FF002 — image-preview.tsx 图片预览组件（无依赖）
3. ✅ R019-FF003 — use-image-upload.ts 上传状态 Hook（依赖 FF001）
4. ✅ R019-FB001 — controller.ts 控制器扩展（依赖 FF001）
5. ✅ R019-FB002 — use-chat-stream.ts 流式请求扩展（依赖 FF001）
6. ✅ R019-FB003 — chat-input.tsx 输入组件扩展（依赖 FF002, FF003）
7. ✅ R019-FB004 — message-bubble.tsx 消息渲染扩展（依赖 FF001）

---

## R019-FF001：types.ts — 类型扩展 `✅ 已完成`

- 文件：`frontend/src/chat/types.ts`
- 改动类型：修改
- domain: ui
- task_layer: foundation
- depends_on: []
- priority: 5
- risk_tags: []
- smoke_required: false
- mode: direct
- status: pending
- acceptance_criteria:
  - ImageRef 接口定义（url + image_id）
  - ApiMessage 新增 images?: ImageRef[]
  - Message 新增 images?: ImageRef[]
  - MessageStatus 新增 'recognizing'（保持现有 sending/stopped 等）
  - convertApiMessages 透传 images 字段
  - TypeScript 编译通过（npx tsc --noEmit）
- test_tasks:
  - type: unit
    description: 类型定义和 convertApiMessages 测试
    scenarios: [convertApiMessages 透传 images, 无 images 时 images 字段不存在]
- contract_refs: []
- decision_refs: []
- blocked_files: []

### FF001.1 新增 ImageRef 接口 `⬜`

在 `ThinkingStep` 之后新增：

```typescript
/** 图片引用 — 上传/历史消息中的图片 */
export interface ImageRef {
  url: string;       // /api/uploads/{user_id}/{uuid}.{ext}
  image_id: string;  // 服务端 UUID
}
```

### FF001.2 ApiMessage 扩展 images `⬜`

在 `thinking_steps` 字段后新增：

```typescript
images?: ImageRef[];
```

### FF001.3 Message 扩展 images `⬜`

在 `thinkingSteps` 字段后新增：

```typescript
images?: ImageRef[];
```

### FF001.4 MessageStatus 新增 recognizing `⬜`

将：

```typescript
export type MessageStatus = 'sending' | 'retrieving' | 'generating' | 'done' | 'stopped' | 'error';
```

改为：

```typescript
export type MessageStatus = 'sending' | 'retrieving' | 'recognizing' | 'generating' | 'done' | 'stopped' | 'error';
```

### FF001.5 convertApiMessages 透传 images `⬜`

在 `convertApiMessages` 的 map 回调中，在 `thinkingSteps` 之后新增：

```typescript
images: apiMsg.images,
```

---

## R019-FF002：image-preview.tsx — 图片预览组件 `✅ 已完成`

- 文件：`frontend/src/components/image-preview.tsx`
- 改动类型：新建
- domain: ui
- task_layer: foundation
- depends_on: []
- priority: 4
- risk_tags: []
- smoke_required: false
- mode: direct
- status: pending
- acceptance_criteria:
  - uploading 状态：半透明缩略图 + loading spinner + X 按钮
  - success 状态：正常缩略图 + X 按钮
  - error 状态：红色遮罩 + "上传失败" + 重试按钮 + X 按钮
  - TypeScript 编译通过
- test_tasks:
  - type: unit
    description: 组件渲染测试
    scenarios: [uploading 渲染 spinner, success 渲染缩略图, error 渲染重试按钮]
- contract_refs: []
- decision_refs: []
- blocked_files: []

### FF002.1 ImagePreview 组件 `⬜`

```typescript
import { ImageUploadItem } from '@/hooks/use-image-upload';

interface ImagePreviewProps {
  item: ImageUploadItem;
  onRemove: (localId: string) => void;
  onRetry: (localId: string) => void;
}

export function ImagePreview({ item, onRemove, onRetry }: ImagePreviewProps) {
  // 根据 item.status 渲染三种状态
  // 共用: <img src={item.thumbnailUrl} />
  // uploading: opacity-50 + spinner + X(调 onRemove → abort)
  // success: 正常 + X(调 onRemove → DELETE)
  // error: 红色遮罩 + "上传失败" + RotateCw 重试按钮 + X(调 onRemove)
}
```

图标使用 lucide-react：X（关闭）、RotateCw（重试）、Loader2（loading spinner）。

---

## R019-FF003：use-image-upload.ts — 上传状态 Hook `✅ 已完成`

- 文件：`frontend/src/hooks/use-image-upload.ts`
- 改动类型：新建
- domain: ui
- task_layer: foundation
- depends_on: [R019-FF001]
- priority: 4
- risk_tags: [network]
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - addImages 校验类型（jpg/png/webp）+ 大小（≤10MB）+ 数量（≤3），不合格 toast 提示
  - 上传用 fetch + FormData + AbortController，不走 fetchWithAuth
  - successImages 返回已成功的 ImageRef[]
  - removeImage：uploading→abort, success→DELETE API, error→直接移除
  - retryUpload：重新调上传 API（新 image_id）
  - clearAll：abort 所有 + DELETE 成功的 + 清空列表
  - isAllUploaded / isAnyUploading 计算属性正确
  - 组件卸载时 revokeObjectURL 所有 thumbnailUrl
- test_tasks:
  - type: unit
    description: Hook 逻辑测试
    scenarios: [addImages 校验拒绝, 上传成功→successImages更新, 上传失败→error状态, removeImage abort, retryUpload重新上传]
- contract_refs: []
- decision_refs: []
- blocked_files: []

### FF003.1 类型定义 `⬜`

```typescript
type UploadStatus = 'uploading' | 'success' | 'error';

interface ImageUploadItem {
  localId: string;            // crypto.randomUUID()
  file: File;
  status: UploadStatus;
  thumbnailUrl: string;       // URL.createObjectURL
  imageId?: string;           // 服务端 image_id
  url?: string;               // 服务端 URL
  abortController: AbortController;
}

interface UseImageUploadReturn {
  items: ImageUploadItem[];
  addImages: (files: File[]) => void;
  removeImage: (localId: string) => void;
  retryUpload: (localId: string) => void;
  clearAll: () => void;
  successImages: ImageRef[];
  isAllUploaded: boolean;
  isAnyUploading: boolean;
}
```

### FF003.2 useImageUpload Hook 实现 `⬜`

核心逻辑：
1. useState<ImageUploadItem[]>([]) 管理 items
2. addImages: 校验 → 创建 ImageUploadItem（status=uploading）→ 立即调 uploadImage → 成功更新 status/imageId/url，失败更新 status=error
3. uploadImage 函数：直接 fetch + Bearer token + FormData + signal
4. removeImage: 根据 status 执行不同操作（abort / DELETE / 直接移除）
5. retryUpload: 保留 file 引用，status 改回 uploading，重新调 uploadImage
6. clearAll: abort 所有 uploading + DELETE 所有 success + setItems([])
7. useEffect cleanup: revokeObjectURL 所有 thumbnailUrl

```typescript
async function uploadImage(file: File, signal: AbortSignal): Promise<{image_id: string, url: string}> {
  const token = authHandlers.getToken();
  const formData = new FormData();
  formData.append('file', file);
  const res = await fetch('/api/chat/upload', {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: formData,
    signal,
  });
  if (!res.ok) throw new Error('上传失败');
  return res.json();
}
```

token 获取参考现有 api-client.ts 的 `authHandlers.getToken()`。

---

## R019-FB001：controller.ts — 控制器扩展 `✅ 已完成`

- 文件：`frontend/src/chat/controller.ts`
- 改动类型：修改
- domain: ui
- task_layer: business
- depends_on: [R019-FF001]
- priority: 3
- risk_tags: []
- smoke_required: false
- mode: direct
- status: pending
- acceptance_criteria:
  - handleSend 接收 images?: ImageRef[] 参数
  - 用户消息设置 msg.images = images
  - onStatus 回调增加 `recognizing` stage 处理（含 resumeStream 的 onStatus）
  - chatStreamFetch 传递 images 参数
  - convertApiMessages 已在 FF001 中透传 images
- test_tasks:
  - type: unit
    description: handleSend images 传递测试
    scenarios: [handleSend 带 images → userMsg.images 不为空, handleSend 无 images → userMsg.images undefined]
- contract_refs: []
- decision_refs: []
- blocked_files: []

### FB001.1 handleSend 签名变更 + images 传递 `⬜`

将 `handleSend` 的签名从无参数改为：

```typescript
const handleSend = useCallback(async (text: string, images?: ImageRef[]) => {
  // 构造 userMsg 时新增:
  images,  // 可能为 undefined，纯文字消息时
  // 调用 chatStreamFetch / sendMessage 时传递 images
}, [...]);
```

### FB001.2 onStatus 回调扩展 `⬜`

将 startSSE 中的 onStatus（约 line 195-198）：

```typescript
if (stage === 'retrieving' || stage === 'generating') {
```

改为：

```typescript
if (stage === 'recognizing' || stage === 'retrieving' || stage === 'generating') {
```

同样修改 resumeStream 中的 onStatus 回调。

### FB001.3 chatStreamFetch 传递 images `⬜`

调用 chatStreamFetch / sendMessage 时，传递 images 参数：

```typescript
// 在 startSSE / resumeStream 中:
chatStreamFetch(text, callbacks, abortController.signal, conversationId, images);
```

---

## R019-FB002：use-chat-stream.ts — 流式请求扩展 `✅ 已完成`

- 文件：`frontend/src/chat/use-chat-stream.ts`
- 改动类型：修改
- domain: ui
- task_layer: business
- depends_on: [R019-FF001]
- priority: 3
- risk_tags: []
- smoke_required: false
- mode: direct
- status: pending
- acceptance_criteria:
  - sendMessage / chatStreamFetch 接收 images?: ImageRef[] 参数
  - body 新增 images 字段（有图片时）
  - 无 images 时行为与现有一致
- test_tasks:
  - type: unit
    description: chatStreamFetch body 测试
    scenarios: [有 images → body 包含 images 字段, 无 images → body 不含 images]
- contract_refs: []
- decision_refs: []
- blocked_files: []

### FB002.1 sendMessage 签名扩展 `⬜`

```typescript
// UseChatStreamReturn.sendMessage 签名扩展:
sendMessage: (question: string, callbacks: SSECallbacks, conversationId?: string, images?: ImageRef[]) => void;
```

### FB002.2 chatStreamFetch body 扩展 `⬜`

在 chatStreamFetch 中构造 body 时：

```typescript
const body: Record<string, unknown> = {
  question,
  conversation_id: conversationId,
  top_k: 10,
};
if (images && images.length > 0) {
  body.images = images;
}
```

---

## R019-FB003：chat-input.tsx — 输入组件扩展 `✅ 已完成`

- 文件：`frontend/src/components/chat-input.tsx`
- 改动类型：修改
- domain: ui
- task_layer: business
- depends_on: [R019-FF002, R019-FF003]
- priority: 3
- risk_tags: []
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - 附件按钮（Paperclip 图标）可见，点击弹出文件选择器
  - Ctrl+V 粘贴图片触发 addImages
  - 预览区在 textarea 上方，渲染 ImagePreview 组件
  - 发送按钮：!isAllUploaded 时 disabled
  - onSend(text, images) 回调携带 successImages
  - 发送后调 clearAll()
  - 切换对话时 clearAll（由 controller 的 switchConversation 触发）
  - TypeScript 编译通过
- test_tasks:
  - type: unit
    description: ChatInput 交互测试
    scenarios: [附件按钮触发文件选择, Ctrl+V 触发 addImages, 上传中发送按钮禁用, 发送时传递 images]
- contract_refs: []
- decision_refs: []
- blocked_files: [frontend/src/lib/api-client.ts, frontend/src/components/chat-ui.tsx]

### FB003.1 Props 扩展 + Hook 集成 `⬜`

```typescript
interface ChatInputProps {
  value: string;
  onChange: (value: string) => void;
  onSend: (text: string, images?: ImageRef[]) => void;  // 签名变更
  onStop: () => void;
  isStreaming: boolean;
}
```

组件内新增：
```typescript
const { items, addImages, removeImage, retryUpload, clearAll, successImages, isAllUploaded } = useImageUpload();
const fileInputRef = useRef<HTMLInputElement>(null);
```

### FB003.2 隐藏 file input + 附件按钮 `⬜`

```tsx
<input
  ref={fileInputRef}
  type="file"
  accept="image/jpeg,image/png,image/webp"
  multiple
  className="hidden"
  onChange={(e) => {
    if (e.target.files) addImages(Array.from(e.target.files));
    e.target.value = '';  // 重置以允许重复选择同一文件
  }}
/>
<button onClick={() => fileInputRef.current?.click()}>
  <Paperclip className="h-5 w-5" />
</button>
```

### FB003.3 Ctrl+V 粘贴监听 `⬜`

textarea 的 onPaste 事件：

```typescript
onPaste={(e) => {
  const items = e.clipboardData?.items;
  if (items) {
    const imageFiles: File[] = [];
    for (const item of Array.from(items)) {
      if (item.type.startsWith('image/')) {
        const file = item.getAsFile();
        if (file) imageFiles.push(file);
      }
    }
    if (imageFiles.length > 0) {
      addImages(imageFiles);
      // 不阻止默认行为：如果剪贴板同时有文本，正常粘贴文本
    }
  }
}}
```

### FB003.4 预览区渲染 `⬜`

在 textarea 上方渲染预览区：

```tsx
{items.length > 0 && (
  <div className="flex gap-2 px-3 pt-3">
    {items.map((item) => (
      <ImagePreview
        key={item.localId}
        item={item}
        onRemove={removeImage}
        onRetry={retryUpload}
      />
    ))}
  </div>
)}
```

### FB003.5 发送按钮逻辑 `⬜`

发送按钮 disabled 条件：

```typescript
disabled={!value.trim() || !isAllUploaded || isStreaming}
```

发送回调：

```typescript
onClick={() => {
  onSend(value.trim(), successImages.length > 0 ? successImages : undefined);
  clearAll();
}}
```

---

## R019-FB004：message-bubble.tsx — 消息渲染扩展 `✅ 已完成`

- 文件：`frontend/src/components/message-bubble.tsx`
- 改动类型：修改
- domain: ui
- task_layer: business
- depends_on: [R019-FF001]
- priority: 3
- risk_tags: []
- smoke_required: false
- mode: direct
- status: pending
- acceptance_criteria:
  - 用户消息含 images 时渲染缩略图
  - 点击缩略图显示大图（CSS overlay）
  - 图片加载失败显示"图片已过期"占位符（onerror 处理）
  - statusLabels 新增 recognizing: '识别中...'
  - loading 动画条件扩展包含 recognizing
  - React.memo 不被破坏
  - TypeScript 编译通过
- test_tasks:
  - type: unit
    description: MessageBubble 图片渲染测试
    scenarios: [用户消息含图片渲染缩略图, 点击缩略图显示大图, 图片 404 显示过期占位, recognizing 状态显示 loading]
- contract_refs: []
- decision_refs: []
- blocked_files: []

### FB004.1 statusLabels 新增 recognizing `⬜`

在现有 statusLabels 对象中新增：

```typescript
recognizing: '识别中...',
```

### FB004.2 loading 动画条件扩展 `⬜`

将 loading 动画的显示条件从：

```typescript
message.status === 'retrieving' || message.status === 'generating'
```

改为：

```typescript
message.status === 'recognizing' || message.status === 'retrieving' || message.status === 'generating'
```

### FB004.3 用户消息图片渲染 `⬜`

在用户消息内容渲染区域，文字之后新增图片缩略图：

```tsx
{message.images && message.images.length > 0 && (
  <div className="mt-2 flex gap-2">
    {message.images.map((img, i) => (
      <div key={i} className="relative cursor-pointer" onClick={() => setLightboxUrl(img.url)}>
        <img
          src={img.url}
          alt={`图片 ${i + 1}`}
          className="h-20 w-20 rounded object-cover"
          onError={(e) => {
            (e.target as HTMLImageElement).src = '';  // 或替换为占位符
            (e.target as HTMLImageElement).alt = '图片已过期';
            (e.target as HTMLImageElement).className = 'h-20 w-20 rounded bg-gray-200 flex items-center justify-center text-xs text-gray-500';
          }}
        />
      </div>
    ))}
  </div>
)}
```

### FB004.4 大图 overlay `⬜`

新增 state + overlay 渲染：

```typescript
const [lightboxUrl, setLightboxUrl] = useState<string | null>(null);

{lightboxUrl && (
  <div
    className="fixed inset-0 z-50 flex items-center justify-center bg-black/70"
    onClick={() => setLightboxUrl(null)}
  >
    <img src={lightboxUrl} className="max-h-[90vh] max-w-[90vw] rounded-lg" />
  </div>
)}
```
