import { describe, it, expect, afterEach } from "vitest"

/**
 * /api/config route 单元测试
 *
 * 验证运行时配置 API 的行为：
 * - 环境变量齐全时返回 200 + 正确 JSON
 * - 缺少环境变量时返回 500 + error JSON
 */
describe("/api/config route", () => {
  const originalClientId = process.env.AUTH_CLIENT_ID
  const originalBaseUrl = process.env.AUTH_BASE_URL

  afterEach(() => {
    if (originalClientId !== undefined) {
      process.env.AUTH_CLIENT_ID = originalClientId
    } else {
      delete process.env.AUTH_CLIENT_ID
    }
    if (originalBaseUrl !== undefined) {
      process.env.AUTH_BASE_URL = originalBaseUrl
    } else {
      delete process.env.AUTH_BASE_URL
    }
  })

  async function callRoute() {
    // 动态导入以响应环境变量变化
    const mod = await import("../app/api/config/route")
    return mod.GET()
  }

  it("环境变量齐全时返回 200 + 正确 JSON", async () => {
    process.env.AUTH_CLIENT_ID = "test-client-id"
    process.env.AUTH_BASE_URL = "https://auth.example.com"

    const res = await callRoute()

    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body).toEqual({
      clientId: "test-client-id",
      authCenterBaseURL: "https://auth.example.com",
    })
  })

  it("缺少 AUTH_CLIENT_ID 时返回 500", async () => {
    delete process.env.AUTH_CLIENT_ID
    process.env.AUTH_BASE_URL = "https://auth.example.com"

    const res = await callRoute()

    expect(res.status).toBe(500)
    const body = await res.json()
    expect(body.error).toBeDefined()
  })

  it("缺少 AUTH_BASE_URL 时返回 500", async () => {
    process.env.AUTH_CLIENT_ID = "test-client-id"
    delete process.env.AUTH_BASE_URL

    const res = await callRoute()

    expect(res.status).toBe(500)
    const body = await res.json()
    expect(body.error).toBeDefined()
  })

  it("两个环境变量都缺失时返回 500", async () => {
    delete process.env.AUTH_CLIENT_ID
    delete process.env.AUTH_BASE_URL

    const res = await callRoute()

    expect(res.status).toBe(500)
  })
})
