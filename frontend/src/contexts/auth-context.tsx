"use client"

import {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  useRef,
  type ReactNode,
} from "react"
import { AuthService, TokenManager, type UserInfo, type AuthState } from "@xlfoundry/auth-sdk-web"
import { registerGetToken } from "../lib/api-client"

/** 运行时配置，从 /api/config 加载 */
export interface RuntimeConfig {
  clientId: string
  authCenterBaseURL: string
}

/** useAuth() 返回的认证上下文 */
export interface AuthContextValue {
  /** 是否已认证 */
  isAuthenticated: boolean
  /** 当前用户信息 */
  user: UserInfo | null
  /** 跳转认证中心登录 */
  login: () => Promise<void>
  /** 登出 */
  logout: () => Promise<void>
  /** 处理 OAuth 回调 */
  handleCallback: () => Promise<UserInfo | null>
  /** SDK 是否初始化完成 */
  isInitialized: boolean
  /** 初始化错误信息 */
  initError: string | null
  /** 获取有效的 access_token（过期自动刷新） */
  getAccessToken: () => Promise<string | null>
}

const AuthContext = createContext<AuthContextValue | null>(null)

const RETURN_URL_KEY = "xlfoundry_auth_return_url"

function saveReturnUrl() {
  sessionStorage.setItem(RETURN_URL_KEY, window.location.pathname + window.location.search)
}

export function consumeReturnUrl(): string {
  const url = sessionStorage.getItem(RETURN_URL_KEY) || "/"
  sessionStorage.removeItem(RETURN_URL_KEY)
  return url
}

/** 单例 AuthService 实例 */
let authService: AuthService | null = null

function getAuthService(): AuthService {
  if (!authService) {
    authService = new AuthService()
  }
  return authService
}

/** 独立 TokenManager 实例（与 AuthService 内部的 TokenManager 共享 localStorage） */
let tokenManager: TokenManager | null = null

function getTokenManager(): TokenManager {
  if (!tokenManager) {
    tokenManager = new TokenManager()
  }
  return tokenManager
}

/**
 * AuthProvider：在客户端 useEffect 中加载配置并初始化 SDK
 *
 * - 必须在 'use client' 组件中使用
 * - SDK 依赖 localStorage/window/sessionStorage，因此初始化放在 useEffect 中
 * - 配置通过 fetch('/api/config') 从服务端环境变量加载
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [isInitialized, setIsInitialized] = useState(false)
  const [initError, setInitError] = useState<string | null>(null)
  const [authState, setAuthState] = useState<AuthState>({
    isAuthenticated: false,
    user: null,
  })
  const initRef = useRef(false)

  useEffect(() => {
    if (initRef.current) return
    initRef.current = true

    const service = getAuthService()

    fetch("/api/config")
      .then((res) => {
        if (!res.ok)
          throw new Error(`配置加载失败: ${res.status}`)
        return res.json()
      })
      .then((config: RuntimeConfig) => {
        // 共享的 SDK 配置（TokenManager 和 AuthService 使用相同参数）
        const sdkConfig = {
          clientId: config.clientId,
          authCenterBaseURL: config.authCenterBaseURL,
          redirectUri: window.location.origin + "/callback",
          onSessionExpired: () => {
            setAuthState({ isAuthenticated: false, user: null })
          },
        }

        // 初始化独立 TokenManager 实例
        const tm = getTokenManager()
        tm.setConfig(sdkConfig)

        // 注册 getAccessToken 到 apiClient
        registerGetToken(() => tm.ensureValidToken())

        return service.init(sdkConfig)
      })
      .then(() => {
        const state = service.getAuthState()
        setAuthState(state)
        setIsInitialized(true)
      })
      .catch((err) => {
        console.error("[AuthContext] SDK 初始化失败:", err)
        setInitError(err.message || "认证初始化失败")
      })
  }, [])

  // 监听 api-client 触发的 session-expired 事件，跳转登录
  useEffect(() => {
    const handleSessionExpired = () => {
      const service = getAuthService()
      service.login()
    }
    window.addEventListener("auth:session-expired", handleSessionExpired)
    return () => window.removeEventListener("auth:session-expired", handleSessionExpired)
  }, [])

  const login = useCallback(async () => {
    saveReturnUrl()
    const service = getAuthService()
    await service.login()
  }, [])

  const logout = useCallback(async () => {
    const service = getAuthService()
    await service.logout()
    setAuthState({ isAuthenticated: false, user: null })
  }, [])

  const handleCallback = useCallback(async () => {
    const service = getAuthService()
    const user = await service.handleCallback()
    const state = service.getAuthState()
    setAuthState(state)
    return user
  }, [])

  const getAccessToken = useCallback(async () => {
    return getTokenManager().ensureValidToken()
  }, [])

  const value: AuthContextValue = {
    isAuthenticated: authState.isAuthenticated,
    user: authState.user,
    login,
    logout,
    handleCallback,
    isInitialized,
    initError,
    getAccessToken,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

/**
 * useAuth hook：获取认证上下文
 *
 * 必须在 AuthProvider 内部使用
 */
export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) {
    throw new Error("useAuth 必须在 AuthProvider 内部使用")
  }
  return ctx
}
