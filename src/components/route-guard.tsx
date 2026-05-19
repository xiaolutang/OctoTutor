'use client'

import { useEffect, type ReactNode } from 'react'
import { useAuth } from '@/contexts/auth-context'

/**
 * RouteGuard：包裹需要登录的页面路由。
 *
 * - 未初始化时显示 loading
 * - 未登录时调用 login() 跳转认证中心
 * - 已登录时渲染 children
 */
export function RouteGuard({ children }: { children: ReactNode }) {
  const { isInitialized, isAuthenticated, login } = useAuth()

  useEffect(() => {
    if (isInitialized && !isAuthenticated) {
      login()
    }
  }, [isInitialized, isAuthenticated, login])

  if (!isInitialized) {
    return (
      <div className="flex min-h-[calc(100vh-3.5rem)] items-center justify-center">
        <span className="text-sm text-muted-foreground">加载中...</span>
      </div>
    )
  }

  if (!isAuthenticated) {
    return null
  }

  return <>{children}</>
}
