import { NextResponse } from "next/server"
import type { NextRequest } from "next/server"

/**
 * 生产环境拦截 /dev/* 路由，返回 404
 * 开发环境正常放行
 */
export function middleware(request: NextRequest) {
  if (
    process.env.NODE_ENV === "production" &&
    request.nextUrl.pathname.startsWith("/dev")
  ) {
    return NextResponse.rewrite(new URL("/not-found", request.url))
  }

  return NextResponse.next()
}

export const config = {
  matcher: ["/dev/:path*"],
}
