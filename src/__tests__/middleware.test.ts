import { describe, it, expect, afterEach } from "vitest"
import { NextRequest } from "next/server"
import { middleware } from "../middleware"

/**
 * middleware 单元测试
 *
 * 验证 /dev/* 路由的环境守卫逻辑：
 * - development：放行
 * - production：rewrite 到 /not-found
 */
describe("dev sandbox middleware", () => {
  const originalEnv = process.env.NODE_ENV

  afterEach(() => {
    process.env.NODE_ENV = originalEnv
  })

  function makeRequest(pathname: string) {
    return new NextRequest(new URL(pathname, "http://localhost:3000"))
  }

  it("开发环境放行 /dev", () => {
    process.env.NODE_ENV = "development"
    const res = middleware(makeRequest("/dev"))
    // NextResponse.next() 不设置 rewrite header
    expect(res.headers.get("x-middleware-rewrite")).toBeNull()
  })

  it("生产环境拦截 /dev，rewrite 到 /not-found", () => {
    process.env.NODE_ENV = "production"
    const res = middleware(makeRequest("/dev"))
    expect(res.headers.get("x-middleware-rewrite")).toContain("not-found")
  })

  it("生产环境放行非 /dev 路由", () => {
    process.env.NODE_ENV = "production"
    const res = middleware(makeRequest("/"))
    expect(res.headers.get("x-middleware-rewrite")).toBeNull()
  })

  it("生产环境拦截 /dev 子路径", () => {
    process.env.NODE_ENV = "production"
    const res = middleware(makeRequest("/dev/some-test"))
    expect(res.headers.get("x-middleware-rewrite")).toContain("not-found")
  })
})
