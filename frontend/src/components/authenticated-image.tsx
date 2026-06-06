'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { useAuth } from '@/contexts/auth-context';

interface AuthenticatedImageProps {
  src: string;
  alt: string;
  className?: string;
  onClick?: () => void;
}

/**
 * 带鉴权的图片组件。
 * <img> 标签无法携带 Authorization header，因此先用 fetch 加载再转为 blob URL。
 */
export function AuthenticatedImage({ src, alt, className, onClick }: AuthenticatedImageProps) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const { getAccessToken } = useAuth();
  const currentSrc = useRef(src);
  const blobUrlRef = useRef<string | null>(null);

  const revokeCurrentBlob = useCallback(() => {
    if (blobUrlRef.current) {
      URL.revokeObjectURL(blobUrlRef.current);
      blobUrlRef.current = null;
    }
  }, []);

  useEffect(() => {
    currentSrc.current = src;
    setFailed(false);
    let cancelled = false;

    (async () => {
      try {
        const token = await getAccessToken();
        if (cancelled || currentSrc.current !== src) return;
        const res = await fetch(src, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (!res.ok || cancelled || currentSrc.current !== src) {
          if (!cancelled) setFailed(true);
          return;
        }
        const blob = await res.blob();
        if (cancelled || currentSrc.current !== src) return;

        const newUrl = URL.createObjectURL(blob);
        revokeCurrentBlob();
        blobUrlRef.current = newUrl;
        setBlobUrl(newUrl);
      } catch {
        if (!cancelled) setFailed(true);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [src, getAccessToken, revokeCurrentBlob]);

  // 组件卸载时清理 blob URL
  useEffect(() => {
    return () => revokeCurrentBlob();
  }, [revokeCurrentBlob]);

  const placeholderClass = "flex h-20 w-20 items-center justify-center rounded text-xs";

  if (failed) {
    return (
      <div className={`${placeholderClass} bg-white/20`} onClick={onClick}>
        图片已过期
      </div>
    );
  }

  if (!blobUrl) {
    return (
      <div className={`${placeholderClass} bg-white/10 text-muted-foreground`} onClick={onClick}>
        加载中...
      </div>
    );
  }

  return <img src={blobUrl} alt={alt} className={className} onClick={onClick} />;
}
