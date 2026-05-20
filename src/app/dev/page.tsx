"use client"

import { useState } from "react"
import { useAuth } from "@/contexts/auth-context"
import { CelebrationOverlay } from "./celebration"

/**
 * 开发沙箱页面
 *
 * 仅在开发环境可访问（production 被 middleware 拦截）。
 * 用于快速测试独立组件、功能片段、API 调用等。
 */
export default function DevSandboxPage() {
  const [code, setCode] = useState(DEFAULT_CODE)
  const [output, setOutput] = useState("")
  const [showCelebration, setShowCelebration] = useState(false)
  const { isInitialized, isAuthenticated, user, login, logout } = useAuth()

  function handleRun() {
    try {
      const result = new Function("return " + code)()
      setOutput(String(result))
    } catch (err) {
      setOutput(`Error: ${err instanceof Error ? err.message : String(err)}`)
    }
  }

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

        {/* 代码输入区 */}
        <section className="border rounded-lg p-4">
          <h2 className="text-sm font-medium text-gray-600 mb-2">
            表达式求值
          </h2>
          <textarea
            value={code}
            onChange={(e) => setCode(e.target.value)}
            className="w-full h-32 p-3 font-mono text-sm border rounded bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-400"
            spellCheck={false}
          />
          <div className="flex items-center gap-3 mt-3">
            <button
              onClick={handleRun}
              className="px-4 py-1.5 bg-blue-600 text-white text-sm rounded hover:bg-blue-700"
            >
              运行
            </button>
            <button
              onClick={() => {
                setCode(DEFAULT_CODE)
                setOutput("")
              }}
              className="px-4 py-1.5 bg-gray-200 text-sm rounded hover:bg-gray-300"
            >
              重置
            </button>
          </div>
          {output && (
            <pre className="mt-3 p-3 bg-gray-900 text-green-400 rounded text-sm overflow-auto">
              {output}
            </pre>
          )}
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

const DEFAULT_CODE = `// 在此输入 JS 表达式
1 + 1`

const LINKS = [
  { label: "首页", href: "/" },
  { label: "对话页", href: "/chat" },
  { label: "OAuth 回调", href: "/callback" },
]
