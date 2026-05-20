import { describe, it, expect, afterEach } from "vitest"
import { middleware } from "../middleware"

/**
 * middleware 单元测试
 *
 * 验证 /dev 路由的环境守卫逻辑：
 * - ENABLE_DEV_SANDBOX=true：放行（本地 Docker 开发）
 * - ENABLE_DEV_SANDBOX 未设置：rewrite 到 /not-found（线上）
 */
describe("dev sandbox middleware", () => {
  const originalEnableDev = process.env.ENABLE_DEV_SANDBOX

  afterEach(() => {
    if (originalEnableDev !== undefined) {
      process.env.ENABLE_DEV_SANDBOX = originalEnableDev
    } else {
      delete process.env.ENABLE_DEV_SANDBOX
    }
  })

  it("ENABLE_DEV_SANDBOX=true 放行", () => {
    process.env.ENABLE_DEV_SANDBOX = "true"
    const res = middleware()
    expect(res.headers.get("x-middleware-rewrite")).toBeNull()
  })

  it("未设置时拦截，rewrite 到 /not-found", () => {
    delete process.env.ENABLE_DEV_SANDBOX
    const res = middleware()
    expect(res.headers.get("x-middleware-rewrite")).toContain("not-found")
  })

  it("ENABLE_DEV_SANDBOX=false 仍然拦截", () => {
    process.env.ENABLE_DEV_SANDBOX = "false"
    const res = middleware()
    expect(res.headers.get("x-middleware-rewrite")).toContain("not-found")
  })

  it("ENABLE_DEV_SANDBOX 为空字符串时拦截", () => {
    process.env.ENABLE_DEV_SANDBOX = ""
    const res = middleware()
    expect(res.headers.get("x-middleware-rewrite")).toContain("not-found")
  })
})
