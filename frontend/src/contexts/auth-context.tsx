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
import { usePathname } from "next/navigation"
import { AuthService, TokenManager, type UserInfo, type AuthState } from "@xlfoundry/auth-sdk-web"
import { SharedTokenManager } from "./shared-token-manager"
import { registerAuthHandlers } from "../lib/api-client"

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
  /** 获取有效的 access_token */
  getAccessToken: () => Promise<string | null>
}

const AuthContext = createContext<AuthContextValue | null>(null)

const RETURN_URL_KEY = "xlfoundry_auth_return_url"

/** 路径白名单：不需要登录的页面 */
const AUTH_WHITELIST = ["/", "/callback"]

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

/** 并发安全的 Token 管理器 */
let sharedTM: SharedTokenManager | null = null

function getAuthService(): AuthService {
  if (!authService) {
    authService = new AuthService()
    sharedTM = new SharedTokenManager(new TokenManager())
  }
  return authService
}

/**
 * AuthProvider：在客户端 useEffect 中加载配置并初始化 SDK
 *
 * 职责：
 * - 管理 SDK 初始化和认证状态
 * - 未登录且不在白名单时自动跳转登录
 * - 通过 registerAuthHandlers 将 token 读/刷新注入 api-client
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [isInitialized, setIsInitialized] = useState(false)
  const [initError, setInitError] = useState<string | null>(null)
  const [authState, setAuthState] = useState<AuthState>({
    isAuthenticated: false,
    user: null,
  })
  const initRef = useRef(false)
  const pathname = usePathname()

  // ── SDK 初始化 ──
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
        const sdkConfig = {
          clientId: config.clientId,
          authCenterBaseURL: config.authCenterBaseURL,
          redirectUri: window.location.origin + "/callback",
          onSessionExpired: () => {
            setAuthState({ isAuthenticated: false, user: null })
          },
        }

        // 注册鉴权处理器到 api-client
        const tm = sharedTM!
        tm.setConfig(sdkConfig)
        registerAuthHandlers({
          getToken: async () => {
            try {
              return tm.getAccessToken()
            } catch {
              return null
            }
          },
          onUnauthorized: async () => {
            try {
              const result = await tm.refreshTokens()
              return result?.access_token ?? null
            } catch {
              // 刷新失败：通知 AuthContext 用户已失效，触发自动跳转
              setAuthState({ isAuthenticated: false, user: null })
              return null
            }
          },
        })

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

  // ── 自动跳转：未登录 + 不在白名单 → login() ──
  useEffect(() => {
    if (!isInitialized) return
    if (authState.isAuthenticated) return
    if (AUTH_WHITELIST.includes(pathname)) return
    login()
  }, [isInitialized, authState.isAuthenticated, pathname])

  const login = useCallback(async () => {
    saveReturnUrl()
    const service = getAuthService()
    await service.login()
  }, [])

  const logout = useCallback(async () => {
    const service = getAuthService()
    await service.logout()
    setAuthState({ isAuthenticated: false, user: null })
    // 主动登出 → 跳转首页，不触发自动登录跳转
    window.location.href = "/"
  }, [])

  const handleCallback = useCallback(async () => {
    const service = getAuthService()
    const user = await service.handleCallback()
    const state = service.getAuthState()
    setAuthState(state)
    return user
  }, [])

  const getAccessToken = useCallback(async () => {
    return sharedTM?.getAccessToken() ?? null
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
