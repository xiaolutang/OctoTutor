"use client"

import Link from "next/link"
import { useAuth } from "@/contexts/auth-context"

export function Header() {
  const { isAuthenticated, user, login, logout, isInitialized } = useAuth()

  return (
    <header className="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="container mx-auto flex h-14 items-center px-4">
        <Link href="/" className="flex items-center space-x-2">
          <span className="text-xl font-bold">🐙</span>
          <span className="text-lg font-semibold">章鱼哥解题 OctoTutor</span>
        </Link>
        <nav className="ml-8 flex items-center space-x-6 text-sm font-medium">
          <Link
            href="/chat"
            className="text-muted-foreground transition-colors hover:text-foreground"
          >
            解题对话
          </Link>
        </nav>
        <div className="ml-auto flex items-center space-x-4">
          {!isInitialized ? (
            <span className="text-sm text-muted-foreground">加载中...</span>
          ) : isAuthenticated && user ? (
            <div className="flex items-center space-x-3">
              <span className="text-sm text-muted-foreground">
                {user.real_name || user.username}
              </span>
              <button
                onClick={logout}
                className="text-sm text-muted-foreground transition-colors hover:text-foreground"
              >
                退出
              </button>
            </div>
          ) : (
            <button
              onClick={login}
              className="inline-flex h-8 items-center justify-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground ring-offset-background transition-colors hover:bg-primary/90"
            >
              登录
            </button>
          )}
        </div>
      </div>
    </header>
  )
}
