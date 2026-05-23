import { describe, it, expect, beforeEach, vi } from "vitest"

// Mock @xlfoundry/auth-sdk-web（本地 symlink 测试环境不可用）
vi.mock("@xlfoundry/auth-sdk-web", () => ({
  AuthService: class {},
  TokenManager: class {
    getAccessToken() { return null }
    setConfig() {}
    refreshTokens() { return Promise.resolve(null) }
  },
}))

import { consumeReturnUrl } from "../contexts/auth-context"

/**
 * return URL 管理单元测试
 *
 * 验证登录前保存的来源页面在回调后能正确恢复：
 * - 保存后能正确读取
 * - 读取后 sessionStorage 被清除
 * - 未保存时返回默认值 "/"
 */

// sessionStorage mock（vitest 运行在 Node.js，无浏览器 API）
const store = new Map<string, string>()
vi.stubGlobal("sessionStorage", {
  getItem: (key: string) => store.get(key) ?? null,
  setItem: (key: string, value: string) => store.set(key, value),
  removeItem: (key: string) => store.delete(key),
  clear: () => store.clear(),
  get length() { return store.size },
  key: (_i: number) => null,
})

describe("return URL 管理", () => {
  const RETURN_URL_KEY = "xlfoundry_auth_return_url"

  beforeEach(() => {
    store.clear()
  })

  it("未保存时 consumeReturnUrl 返回默认值 /", () => {
    expect(consumeReturnUrl()).toBe("/")
  })

  it("保存后能正确读取", () => {
    sessionStorage.setItem(RETURN_URL_KEY, "/chat")
    expect(consumeReturnUrl()).toBe("/chat")
  })

  it("保存带 query 的路径能正确读取", () => {
    sessionStorage.setItem(RETURN_URL_KEY, "/chat?topic=math")
    expect(consumeReturnUrl()).toBe("/chat?topic=math")
  })

  it("读取后 sessionStorage 被清除", () => {
    sessionStorage.setItem(RETURN_URL_KEY, "/dev")
    consumeReturnUrl()
    expect(sessionStorage.getItem(RETURN_URL_KEY)).toBeNull()
  })
})
