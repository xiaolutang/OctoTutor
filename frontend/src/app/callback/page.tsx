"use client"

import { useEffect, useRef, useState } from "react"
import { useRouter } from "next/navigation"
import { useAuth, consumeReturnUrl } from "@/contexts/auth-context"

export default function CallbackPage() {
  const router = useRouter()
  const { isInitialized, handleCallback, login } = useAuth()
  const [error, setError] = useState<string | null>(null)
  const processedRef = useRef(false)

  useEffect(() => {
    if (!isInitialized || processedRef.current) return
    processedRef.current = true

    handleCallback()
      .then(() => {
        router.replace(consumeReturnUrl())
      })
      .catch((err) => {
        console.error("[Callback] 登录回调处理失败:", err)
        setError(err.message || "登录回调处理失败")
      })
  }, [isInitialized, handleCallback, router])

  if (error) {
    return (
      <div className="container mx-auto flex min-h-[calc(100vh-3.5rem)] items-center justify-center px-4">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-red-600">登录失败</h1>
          <p className="mt-2 text-muted-foreground">{error}</p>
          <button
            onClick={login}
            className="mt-4 inline-flex h-10 items-center justify-center rounded-md bg-primary px-8 text-sm font-medium text-primary-foreground"
          >
            重新登录
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="container mx-auto flex min-h-[calc(100vh-3.5rem)] items-center justify-center px-4">
      <div className="text-center">
        <h1 className="text-2xl font-bold">OAuth 回调</h1>
        <p className="mt-2 text-muted-foreground">
          正在处理登录回调...
        </p>
      </div>
    </div>
  )
}
