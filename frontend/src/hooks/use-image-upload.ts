'use client';

import { useState, useCallback, useEffect, useRef } from 'react';
import { toast } from 'sonner';
import { useAuth } from '@/contexts/auth-context';
import type { ImageRef } from '@/chat/types';

type UploadStatus = 'uploading' | 'success' | 'error';

export interface ImageUploadItem {
  localId: string;
  file: File;
  status: UploadStatus;
  thumbnailUrl: string;
  imageId?: string;
  url?: string;
  abortController: AbortController;
}

const ALLOWED_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp']);
const MAX_SIZE = 10 * 1024 * 1024; // 10MB
const MAX_COUNT = 3;

async function uploadImage(
  file: File,
  signal: AbortSignal,
  getToken: () => Promise<string | null>,
): Promise<{ image_id: string; url: string }> {
  const token = await getToken();
  const formData = new FormData();
  formData.append('file', file);
  const res = await fetch('/api/chat/upload', {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: formData,
    signal,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(text || '上传失败');
  }
  return res.json();
}

export function useImageUpload() {
  const [items, setItems] = useState<ImageUploadItem[]>([]);
  const itemsRef = useRef(items);
  itemsRef.current = items;
  const { getAccessToken } = useAuth();

  // 组件卸载时 revokeObjectURL
  useEffect(() => {
    return () => {
      for (const item of itemsRef.current) {
        URL.revokeObjectURL(item.thumbnailUrl);
      }
    };
  }, []);

  const addImages = useCallback((files: File[]) => {
    // 校验类型 + 大小
    const valid: File[] = [];
    for (const f of files) {
      if (!ALLOWED_TYPES.has(f.type)) {
        toast.error(`不支持的文件类型: ${f.type}，仅支持 jpg/png/webp`);
        continue;
      }
      if (f.size > MAX_SIZE) {
        toast.error(`文件 ${f.name} 超过 10MB 限制`);
        continue;
      }
      valid.push(f);
    }
    if (valid.length === 0) return;

    setItems((prev) => {
      const remaining = MAX_COUNT - prev.length;
      if (remaining <= 0) {
        toast.error('最多上传 3 张图片');
        return prev;
      }
      const toAdd = valid.slice(0, remaining);
      if (toAdd.length < valid.length) {
        toast.error(`仅添加前 ${toAdd.length} 张，最多 3 张`);
      }

      const newItems: ImageUploadItem[] = toAdd.map((file) => ({
        localId: crypto.randomUUID(),
        file,
        status: 'uploading' as const,
        thumbnailUrl: URL.createObjectURL(file),
        abortController: new AbortController(),
      }));

      // 触发上传
      for (const item of newItems) {
        uploadImage(item.file, item.abortController.signal, getAccessToken)
          .then(({ image_id, url }) => {
            setItems((prev) =>
              prev.map((i) =>
                i.localId === item.localId
                  ? { ...i, status: 'success', imageId: image_id, url }
                  : i,
              ),
            );
          })
          .catch(() => {
            setItems((prev) =>
              prev.map((i) =>
                i.localId === item.localId ? { ...i, status: 'error' } : i,
              ),
            );
          });
      }

      return [...prev, ...newItems];
    });
  }, []);

  const removeImage = useCallback((localId: string) => {
    setItems((prev) => {
      const item = prev.find((i) => i.localId === localId);
      if (!item) return prev;

      if (item.status === 'uploading') {
        item.abortController.abort();
      } else if (item.status === 'success' && item.imageId) {
        // fire-and-forget DELETE
        (async () => {
          try {
            const token = await getAccessToken();
            await fetch(`/api/chat/upload/${item.imageId}`, {
              method: 'DELETE',
              headers: token ? { Authorization: `Bearer ${token}` } : {},
            });
          } catch {
            // 静默失败
          }
        })();
      }

      URL.revokeObjectURL(item.thumbnailUrl);
      return prev.filter((i) => i.localId !== localId);
    });
  }, []);

  const retryUpload = useCallback((localId: string) => {
    setItems((prev) => {
      const item = prev.find((i) => i.localId === localId);
      if (!item || item.status !== 'error') return prev;

      const newController = new AbortController();
      uploadImage(item.file, newController.signal, getAccessToken)
        .then(({ image_id, url }) => {
          setItems((prev) =>
            prev.map((i) =>
              i.localId === localId
                ? { ...i, status: 'success', imageId: image_id, url, abortController: newController }
                : i,
            ),
          );
        })
        .catch(() => {
          setItems((prev) =>
            prev.map((i) =>
              i.localId === localId
                ? { ...i, status: 'error', abortController: newController }
                : i,
            ),
          );
        });

      return prev.map((i) =>
        i.localId === localId
          ? { ...i, status: 'uploading', abortController: newController }
          : i,
      );
    });
  }, []);

  const clearAll = useCallback(() => {
    setItems((prev) => {
      for (const item of prev) {
        if (item.status === 'uploading') {
          item.abortController.abort();
        }
        URL.revokeObjectURL(item.thumbnailUrl);
      }
      // DELETE 成功的
      for (const item of prev) {
        if (item.status === 'success' && item.imageId) {
          (async () => {
            try {
              const token = await getAccessToken();
              await fetch(`/api/chat/upload/${item.imageId}`, {
                method: 'DELETE',
                headers: token ? { Authorization: `Bearer ${token}` } : {},
              });
            } catch {
              // 静默
            }
          })();
        }
      }
      return [];
    });
  }, []);

  const successImages: ImageRef[] = items
    .filter((i) => i.status === 'success' && i.url && i.imageId)
    .map((i) => ({ url: i.url!, image_id: i.imageId! }));

  const isAllUploaded = items.length === 0 || items.every((i) => i.status !== 'uploading');
  const isAnyUploading = items.some((i) => i.status === 'uploading');

  return {
    items,
    addImages,
    removeImage,
    retryUpload,
    clearAll,
    successImages,
    isAllUploaded,
    isAnyUploading,
  };
}
