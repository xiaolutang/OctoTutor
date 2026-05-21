import { NextResponse } from "next/server"

/**
 * 线上环境拦截 /dev 路由，返回 404
 * 本地 Docker 设置 ENABLE_DEV_SANDBOX=true 放行
 */
export function middleware() {
  if (process.env.ENABLE_DEV_SANDBOX !== "true") {
    return NextResponse.rewrite(new URL("/not-found", "http://localhost"))
  }

  return NextResponse.next()
}

export const config = {
  matcher: ["/dev", "/dev/:path*"],
}
