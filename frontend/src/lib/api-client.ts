/**
 * api-client.ts — 统一网络层
 *
 * 职责：token 注入 + 401 重试（通过 onUnauthorized 回调）
 * 不依赖任何 React 组件或 AuthService，通过 registerAuthHandlers 解耦
 */

const BASE_URL = '/api';

type AuthHandlers = {
  getToken: () => Promise<string | null>;
  onUnauthorized: () => Promise<string | null>;
};

/** 鉴权处理器，由 AuthProvider 初始化后注册 */
let authHandlers: AuthHandlers | null = null;

/** 注册鉴权处理器（getToken + onUnauthorized） */
export function registerAuthHandlers(handlers: AuthHandlers): void {
  authHandlers = handlers;
}

/**
 * 统一 fetch：自动附加 Bearer token + 401 重试
 * 返回值与原生 fetch 完全一致（Response），支持 SSE ReadableStream
 */
export async function fetchWithAuth(
  url: string,
  init?: RequestInit,
): Promise<Response> {
  const fullURL = url.startsWith('http') ? url : `${BASE_URL}${url}`;

  // 1. 获取 token
  const token = authHandlers ? await authHandlers.getToken() : null;

  // 2. 构建 headers
  const headers = new Headers(init?.headers);
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  // 如果没有显式设置 Content-Type 且有 body，默认 JSON
  if (init?.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  // 3. 发送请求
  const response = await fetch(fullURL, {
    ...init,
    headers,
  });

  // 4. 401 处理：通过 onUnauthorized 获取新 token 并重试一次
  if (response.status === 401 && !headers.has('X-Retry') && authHandlers) {
    const newToken = await authHandlers.onUnauthorized();
    if (newToken) {
      const retryHeaders = new Headers(init?.headers);
      retryHeaders.set('Authorization', `Bearer ${newToken}`);
      retryHeaders.set('X-Retry', 'true');
      if (init?.body && !retryHeaders.has('Content-Type')) {
        retryHeaders.set('Content-Type', 'application/json');
      }
      return fetch(fullURL, { ...init, headers: retryHeaders });
    }
  }

  return response;
}

// ===== 测试辅助（仅用于单元测试重置状态）=====
export function _resetForTesting(): void {
  authHandlers = null;
}
