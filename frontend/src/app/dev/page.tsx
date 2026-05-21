"use client"

import { useState } from "react"
import { useAuth } from "@/contexts/auth-context"
import { CelebrationOverlay } from "./celebration"

const LINKS = [
  { label: "首页", href: "/" },
  { label: "对话页", href: "/chat" },
]

/**
 * 开发沙箱页面
 *
 * 仅在开发环境可访问（production 被 middleware 拦截）。
 * 用于快速测试独立组件、功能片段、API 调用等。
 */
export default function DevSandboxPage() {
  const [showCelebration, setShowCelebration] = useState(false)
  const { isInitialized, isAuthenticated, user, login, logout } = useAuth()

  return (
    <div className="min-h-screen p-6 max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold mb-2">Dev Sandbox</h1>
      <p className="text-sm text-gray-500 mb-6">
        仅开发环境可用 · 测试组件、逻辑、API 调用
      </p>

      <div className="grid gap-6">
        {/* 登录状态区 */}
        <section className="border rounded-lg p-4">
          <h2 className="text-sm font-medium text-gray-600 mb-3">
            认证状态
          </h2>
          {!isInitialized ? (
            <span className="text-sm text-gray-400">加载中...</span>
          ) : isAuthenticated && user ? (
            <div className="flex items-center gap-3">
              <span className="text-sm">
                已登录：<strong>{user.real_name || user.username}</strong>
              </span>
              <button
                onClick={logout}
                className="px-3 py-1 bg-gray-200 text-sm rounded hover:bg-gray-300"
              >
                退出
              </button>
            </div>
          ) : (
            <button
              onClick={login}
              className="px-4 py-1.5 bg-blue-600 text-white text-sm rounded hover:bg-blue-700"
            >
              登录
            </button>
          )}
        </section>

        {/* 庆祝入口 */}
        <section className="border rounded-lg p-4">
          <h2 className="text-sm font-medium text-gray-600 mb-3">
            里程碑庆祝
          </h2>
          <button
            onClick={() => setShowCelebration(true)}
            className="px-4 py-2 bg-gradient-to-r from-orange-500 to-red-600 text-white text-sm font-medium rounded-lg hover:from-orange-600 hover:to-red-700 transition-all"
          >
            庆祝基础架构搭建完成
          </button>
        </section>

        {/* 快捷入口 */}
        <section className="border rounded-lg p-4">
          <h2 className="text-sm font-medium text-gray-600 mb-3">
            页面快捷入口
          </h2>
          <div className="flex flex-wrap gap-2">
            {LINKS.map((link) => (
              <a
                key={link.href}
                href={link.href}
                className="px-3 py-1.5 border rounded text-sm hover:bg-gray-50"
              >
                {link.label}
              </a>
            ))}
          </div>
        </section>
      </div>

      {/* 庆祝动效 Overlay */}
      {showCelebration && (
        <CelebrationOverlay onClose={() => setShowCelebration(false)} />
      )}
    </div>
  )
}
