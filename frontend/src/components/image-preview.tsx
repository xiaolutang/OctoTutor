'use client';

import { Loader2, RotateCw, X } from 'lucide-react';

export type UploadStatus = 'uploading' | 'success' | 'error';

export interface ImageUploadItem {
  localId: string;
  file: File;
  status: UploadStatus;
  thumbnailUrl: string;
  imageId?: string;
  url?: string;
  abortController: AbortController;
}

interface ImagePreviewProps {
  item: ImageUploadItem;
  onRemove: (localId: string) => void;
  onRetry: (localId: string) => void;
}

export function ImagePreview({ item, onRemove, onRetry }: ImagePreviewProps) {
  return (
    <div className="relative group">
      <img
        src={item.thumbnailUrl}
        alt="预览"
        className={`h-20 w-20 rounded object-cover ${
          item.status === 'uploading' ? 'opacity-50' : ''
        } ${item.status === 'error' ? 'ring-2 ring-destructive' : ''}`}
      />

      {/* uploading: spinner */}
      {item.status === 'uploading' && (
        <div className="absolute inset-0 flex items-center justify-center">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      )}

      {/* error: overlay + retry */}
      {item.status === 'error' && (
        <div className="absolute inset-0 flex flex-col items-center justify-center rounded bg-destructive/20">
          <span className="text-[10px] text-destructive">上传失败</span>
          <button
            onClick={() => onRetry(item.localId)}
            className="mt-0.5 rounded p-0.5 text-destructive hover:bg-destructive/10"
          >
            <RotateCw className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

      {/* X 按钮 */}
      <button
        onClick={() => onRemove(item.localId)}
        className="absolute -right-1.5 -top-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-muted text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity hover:bg-destructive hover:text-white"
      >
        <X className="h-3 w-3" />
      </button>
    </div>
  );
}
