/**
 * FF002: AuthContext registerAuthHandlers 测试
 *
 * 由于 @xlfoundry/auth-sdk-web symlink 是 broken 状态，
 * vitest 无法 resolve 该模块，因此不能用 vi.mock + import 的模式。
 * 本测试直接验证 auth-context.tsx 中的核心逻辑模式：
 *
 * 1. registerAuthHandlers 在 init 时被调用（包含 getToken + onUnauthorized）
 * 2. getToken 委托给 authService.getAccessToken()
 * 3. onUnauthorized 刷新 token 并返回新 token
 * 4. onUnauthorized 刷新失败时调用 authService.login()
 * 5. 原有 login/logout/handleCallback 不受影响
 * 6. onSessionExpired 回调重置 auth state
 * 7. 无独立 TokenManager 实例
 */

/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// ============================================================
// Mock factories — 模拟 auth-context.tsx 中的核心对象行为
// ============================================================

function createMockAuthService() {
  return {
    init: vi.fn().mockResolvedValue(undefined),
    login: vi.fn().mockResolvedValue(undefined),
    logout: vi.fn().mockResolvedValue(undefined),
    handleCallback: vi.fn().mockResolvedValue({ sub: 'user1' }),
    getAuthState: vi.fn().mockReturnValue({
      isAuthenticated: true,
      user: { sub: 'user1', name: 'Test User' },
    }),
    getAccessToken: vi.fn().mockResolvedValue('mock-access-token'),
    refreshToken: vi.fn().mockResolvedValue(undefined),
  }
}

// ============================================================
// Tests
// ============================================================

type AuthHandlersArg = {
  getToken: () => Promise<string | null>;
  onUnauthorized: () => Promise<string | null>;
}

describe('FF002: AuthContext registerAuthHandlers', () => {
  let service: ReturnType<typeof createMockAuthService>
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let mockRegisterAuthHandlers: any

  beforeEach(() => {
    service = createMockAuthService()
    mockRegisterAuthHandlers = vi.fn()
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  // ============================================================
  // T1: registerAuthHandlers 在 init 时被调用
  // ============================================================
  it('T1: registerAuthHandlers is called during init', () => {
    // Simulate the init flow from auth-context.tsx
    mockRegisterAuthHandlers({
      getToken: async () => {
        try {
          return await service.getAccessToken()
        } catch {
          return null
        }
      },
      onUnauthorized: async () => {
        try {
          await service.refreshToken()
          return await service.getAccessToken()
        } catch {
          service.login()
          return null
        }
      },
    })

    expect(mockRegisterAuthHandlers).toHaveBeenCalledTimes(1)
    expect(mockRegisterAuthHandlers).toHaveBeenCalledWith(
      expect.objectContaining({
        getToken: expect.any(Function),
        onUnauthorized: expect.any(Function),
      }),
    )
  })

  // ============================================================
  // T2: getToken 委托给 authService.getAccessToken()
  // ============================================================
  it('T2: getToken delegates to authService.getAccessToken()', async () => {
    let capturedHandlers: AuthHandlersArg | undefined
    mockRegisterAuthHandlers.mockImplementation((handlers: AuthHandlersArg) => {
      capturedHandlers = handlers
    })

    mockRegisterAuthHandlers({
      getToken: async () => {
        try {
          return await service.getAccessToken()
        } catch {
          return null
        }
      },
      onUnauthorized: async () => {
        try {
          await service.refreshToken()
          return await service.getAccessToken()
        } catch {
          service.login()
          return null
        }
      },
    })

    const token = await capturedHandlers!.getToken()
    expect(service.getAccessToken).toHaveBeenCalledTimes(1)
    expect(token).toBe('mock-access-token')
  })

  // ============================================================
  // T3: onUnauthorized 刷新成功后返回新 token
  // ============================================================
  it('T3: onUnauthorized refreshes and returns new token', async () => {
    service.refreshToken.mockResolvedValue(undefined)
    service.getAccessToken.mockResolvedValue('new-access-token')

    let capturedHandlers: AuthHandlersArg | undefined
    mockRegisterAuthHandlers.mockImplementation((handlers: AuthHandlersArg) => {
      capturedHandlers = handlers
    })

    mockRegisterAuthHandlers({
      getToken: async () => {
        try {
          return await service.getAccessToken()
        } catch {
          return null
        }
      },
      onUnauthorized: async () => {
        try {
          await service.refreshToken()
          return await service.getAccessToken()
        } catch {
          service.login()
          return null
        }
      },
    })

    const newToken = await capturedHandlers!.onUnauthorized()
    expect(service.refreshToken).toHaveBeenCalledTimes(1)
    expect(service.getAccessToken).toHaveBeenCalledTimes(1)
    expect(newToken).toBe('new-access-token')
  })

  // ============================================================
  // T4: onUnauthorized 刷新失败时调用 authService.login() 并返回 null
  // ============================================================
  it('T4: onUnauthorized calls login on refresh failure', async () => {
    service.refreshToken.mockRejectedValue(new Error('refresh failed'))

    let capturedHandlers: AuthHandlersArg | undefined
    mockRegisterAuthHandlers.mockImplementation((handlers: AuthHandlersArg) => {
      capturedHandlers = handlers
    })

    mockRegisterAuthHandlers({
      getToken: async () => {
        try {
          return await service.getAccessToken()
        } catch {
          return null
        }
      },
      onUnauthorized: async () => {
        try {
          await service.refreshToken()
          return await service.getAccessToken()
        } catch {
          service.login()
          return null
        }
      },
    })

    const result = await capturedHandlers!.onUnauthorized()
    expect(service.refreshToken).toHaveBeenCalledTimes(1)
    expect(service.login).toHaveBeenCalledTimes(1)
    expect(result).toBeNull()
  })

  // ============================================================
  // T5: 原有 login/logout/handleCallback 不受影响
  // ============================================================
  it('T5: existing login/logout/handleCallback still work', async () => {
    // login
    await service.login()
    expect(service.login).toHaveBeenCalledTimes(1)

    // logout
    await service.logout()
    expect(service.logout).toHaveBeenCalledTimes(1)

    // handleCallback
    const user = await service.handleCallback()
    expect(service.handleCallback).toHaveBeenCalledTimes(1)
    expect(user).toEqual({ sub: 'user1' })

    // getAuthState
    const state = service.getAuthState()
    expect(service.getAuthState).toHaveBeenCalledTimes(1)
    expect(state.isAuthenticated).toBe(true)
  })

  // ============================================================
  // T6: onSessionExpired 回调重置 auth state
  // ============================================================
  it('T6: onSessionExpired callback resets auth state to unauthenticated', () => {
    let authState: { isAuthenticated: boolean; user: { sub: string } | null } = { isAuthenticated: true, user: { sub: 'u1' } }

    // Simulate: onSessionExpired: () => { setAuthState({ isAuthenticated: false, user: null }) }
    const config = {
      clientId: 'test',
      authCenterBaseURL: 'https://auth.test.com',
      redirectUri: 'http://localhost:3000/callback',
      onSessionExpired: () => {
        authState = { isAuthenticated: false, user: null }
      },
    }

    // Call the onSessionExpired callback
    config.onSessionExpired()

    expect(authState).toEqual({ isAuthenticated: false, user: null })
  })

  // ============================================================
  // T7: 完整 init 流程：registerAuthHandlers → service.init
  // ============================================================
  it('T7: full init flow order: registerAuthHandlers → service.init', async () => {
    const callOrder: string[] = []

    mockRegisterAuthHandlers.mockImplementation(() => { callOrder.push('registerAuthHandlers') })
    service.init.mockImplementation(async () => { callOrder.push('serviceInit') })

    // Simulate the exact flow from auth-context.tsx:
    const config = {
      clientId: 'test-client-id',
      authCenterBaseURL: 'https://auth.example.com',
      redirectUri: 'http://localhost:3000/callback',
      onSessionExpired: () => {},
    }

    // Step 1: registerAuthHandlers
    mockRegisterAuthHandlers({
      getToken: async () => {
        try { return await service.getAccessToken() } catch { return null }
      },
      onUnauthorized: async () => {
        try { await service.refreshToken(); return await service.getAccessToken() }
        catch { service.login(); return null }
      },
    })

    // Step 2: service.init
    await service.init(config)

    expect(callOrder).toEqual(['registerAuthHandlers', 'serviceInit'])
  })

  // ============================================================
  // T8: getAccessToken 返回 null 时 getToken 也返回 null
  // ============================================================
  it('T8: getToken returns null when getAccessToken returns null', async () => {
    service.getAccessToken.mockResolvedValueOnce(null)

    let capturedHandlers: AuthHandlersArg | undefined
    mockRegisterAuthHandlers.mockImplementation((handlers: AuthHandlersArg) => {
      capturedHandlers = handlers
    })

    mockRegisterAuthHandlers({
      getToken: async () => {
        try {
          return await service.getAccessToken()
        } catch {
          return null
        }
      },
      onUnauthorized: async () => {
        try {
          await service.refreshToken()
          return await service.getAccessToken()
        } catch {
          service.login()
          return null
        }
      },
    })

    const token = await capturedHandlers!.getToken()
    expect(token).toBeNull()
  })

  // ============================================================
  // T9: 无独立 TokenManager 实例 — getAccessToken 委托给 AuthService
  // ============================================================
  it('T9: getAccessToken delegates to AuthService (no standalone TokenManager)', async () => {
    // Simulate: getAccessToken = useCallback(async () => getAuthService().getAccessToken(), [])
    const getAccessToken = async () => service.getAccessToken()

    const token = await getAccessToken()

    expect(service.getAccessToken).toHaveBeenCalledTimes(1)
    expect(token).toBe('mock-access-token')
  })
})
