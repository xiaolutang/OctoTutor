'use client';

import { useState, useEffect, useRef } from 'react';
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

  useEffect(() => {
    currentSrc.current = src;
    setFailed(false);
    let objectUrl: string | null = null;

    (async () => {
      try {
        const token = await getAccessToken();
        const res = await fetch(src, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (!res.ok || currentSrc.current !== src) {
          setFailed(true);
          return;
        }
        const blob = await res.blob();
        objectUrl = URL.createObjectURL(blob);
        if (currentSrc.current === src) {
          setBlobUrl(objectUrl);
        } else {
          URL.revokeObjectURL(objectUrl);
        }
      } catch {
        setFailed(true);
      }
    })();

    return () => {
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [src, getAccessToken]);

  if (failed) {
    return (
      <div
        className="flex h-20 w-20 items-center justify-center rounded bg-white/20 text-xs"
        onClick={onClick}
      >
        图片已过期
      </div>
    );
  }

  if (!blobUrl) {
    return (
      <div
        className="flex h-20 w-20 items-center justify-center rounded bg-white/10 text-xs text-muted-foreground"
        onClick={onClick}
      >
        加载中...
      </div>
    );
  }

  return <img src={blobUrl} alt={alt} className={className} onClick={onClick} />;
}
