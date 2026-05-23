'use client'

import { type ReactNode } from 'react'
import { useAuth } from '@/contexts/auth-context'

/**
 * RouteGuard：包裹需要登录的页面路由。
 *
 * - 未初始化时显示 loading
 * - 未登录时返回 null（auth-context 统一管理跳转）
 * - 已登录时渲染 children
 */
export function RouteGuard({ children }: { children: ReactNode }) {
  const { isInitialized, isAuthenticated } = useAuth()

  if (!isInitialized) {
    return (
      <div className="flex min-h-[calc(100vh-3.5rem)] items-center justify-center">
        <span className="text-sm text-muted-foreground">加载中...</span>
      </div>
    )
  }

  if (!isAuthenticated) {
    return null  // auth-context 统一管理跳转
  }

  return <>{children}</>
}
