/**
 * api-client.ts — 统一网络层
 *
 * 职责：token 注入 + 刷新锁（并发去重）+ 401 重试
 * 不依赖任何 React 组件或 AuthService，通过 registerGetToken 解耦
 */

const BASE_URL = '/api';

type GetTokenFn = () => Promise<string | null>;

/** token 获取函数，由 AuthProvider 初始化后注册 */
let getTokenFn: GetTokenFn | null = null;

/** 注册 token 获取函数 */
export function registerGetToken(fn: GetTokenFn): void {
  getTokenFn = fn;
}

/** 跳转登录页（通过事件解耦，不直接调用 AuthContext） */
function redirectToLogin(): void {
  window.dispatchEvent(new CustomEvent('auth:session-expired'));
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
  const token = getTokenFn ? await getTokenFn() : null;

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

  // 4. 401 处理：刷新 token + 重试一次
  if (response.status === 401 && !headers.has('X-Retry')) {
    const newToken = await refreshAndGetToken();

    if (newToken) {
      // 重试请求
      const retryHeaders = new Headers(init?.headers);
      retryHeaders.set('Authorization', `Bearer ${newToken}`);
      retryHeaders.set('X-Retry', 'true');
      if (init?.body && !retryHeaders.has('Content-Type')) {
        retryHeaders.set('Content-Type', 'application/json');
      }

      return fetch(fullURL, {
        ...init,
        headers: retryHeaders,
      });
    }
  }

  // 5. 重试仍 401 或刷新失败：触发 session-expired
  if (response.status === 401) {
    redirectToLogin();
  }

  return response;
}

/** 刷新锁：确保并发请求只刷新一次 */
let refreshPromise: Promise<string | null> | null = null;

/**
 * 刷新 token 并返回新的 access_token
 * 多个并发调用共享同一个刷新 Promise（去重）
 */
async function refreshAndGetToken(): Promise<string | null> {
  // 已有刷新进行中，复用同一个 Promise
  if (refreshPromise) {
    return refreshPromise;
  }

  // 发起刷新
  refreshPromise = (async () => {
    try {
      // 30s 超时保护
      const result = await Promise.race([
        getTokenFn ? getTokenFn() : Promise.resolve(null),
        new Promise<null>((_, reject) =>
          setTimeout(() => reject(new Error('Token refresh timeout')), 30_000),
        ),
      ]);
      return result;
    } catch {
      return null;
    } finally {
      // 无论成功失败，清空刷新锁
      refreshPromise = null;
    }
  })();

  return refreshPromise;
}

// ===== 测试辅助（仅用于单元测试重置状态）=====
export function _resetForTesting(): void {
  getTokenFn = null;
  refreshPromise = null;
}
