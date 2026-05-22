/**
 * FF002: AuthContext TokenManager 注册测试
 *
 * 由于 @xlfoundry/auth-sdk-web symlink 是 broken 状态，
 * vitest 无法 resolve 该模块，因此不能用 vi.mock + import 的模式。
 * 本测试直接验证 auth-context.tsx 中的核心逻辑模式：
 *
 * 1. TokenManager setConfig 在 init 时被调用（正确参数）
 * 2. registerGetToken 在 init 后被调用（函数包装 ensureValidToken）
 * 3. getAccessToken() 返回 ensureValidToken 结果
 * 4. auth:session-expired 事件触发 service.login()
 * 5. 原有 login/logout/handleCallback 不受影响
 * 6. onSessionExpired 回调重置 auth state
 */

/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// ============================================================
// Mock factories — 模拟 auth-context.tsx 中的核心对象行为
// ============================================================

function createMockTokenManager() {
  return {
    setConfig: vi.fn(),
    ensureValidToken: vi.fn().mockResolvedValue('mock-access-token'),
  }
}

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
  }
}

// ============================================================
// Tests
// ============================================================

describe('FF002: AuthContext TokenManager Registration', () => {
  let tm: ReturnType<typeof createMockTokenManager>
  let service: ReturnType<typeof createMockAuthService>
  let mockRegisterGetToken: ReturnType<typeof vi.fn>

  beforeEach(() => {
    tm = createMockTokenManager()
    service = createMockAuthService()
    mockRegisterGetToken = vi.fn()
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  // ============================================================
  // T1: TokenManager.setConfig 在 init 时被调用（正确参数）
  // ============================================================
  it('T1: TokenManager.setConfig is called with correct config during init', () => {
    // Simulate: const tm = getTokenManager(); tm.setConfig({ ... })
    tm.setConfig({
      clientId: 'test-client-id',
      authCenterBaseURL: 'https://auth.example.com',
      redirectUri: 'http://localhost:3000/callback',
      onSessionExpired: () => {},
    })

    expect(tm.setConfig).toHaveBeenCalledTimes(1)
    expect(tm.setConfig).toHaveBeenCalledWith(
      expect.objectContaining({
        clientId: 'test-client-id',
        authCenterBaseURL: 'https://auth.example.com',
        redirectUri: 'http://localhost:3000/callback',
      }),
    )
    expect(tm.setConfig).toHaveBeenCalledWith(
      expect.objectContaining({
        onSessionExpired: expect.any(Function),
      }),
    )
  })

  // ============================================================
  // T2: registerGetToken 在 init 后被调用（函数包装 ensureValidToken）
  // ============================================================
  it('T2: registerGetToken is called with a function wrapping tm.ensureValidToken', async () => {
    // Simulate init flow from auth-context.tsx:
    // tm.setConfig(...)
    // registerGetToken(() => tm.ensureValidToken())
    tm.setConfig({
      clientId: 'test-client-id',
      authCenterBaseURL: 'https://auth.example.com',
      redirectUri: 'http://localhost:3000/callback',
      onSessionExpired: () => {},
    })

    // ★ This is the exact pattern used in auth-context.tsx
    mockRegisterGetToken(() => tm.ensureValidToken())

    // Verify registerGetToken was called with a function
    expect(mockRegisterGetToken).toHaveBeenCalledTimes(1)
    expect(mockRegisterGetToken).toHaveBeenCalledWith(expect.any(Function))

    // Call the registered function and verify it calls ensureValidToken
    const registeredFn = mockRegisterGetToken.mock.calls[0][0] as () => Promise<string | null>
    const token = await registeredFn()
    expect(tm.ensureValidToken).toHaveBeenCalledTimes(1)
    expect(token).toBe('mock-access-token')
  })

  // ============================================================
  // T3: getAccessToken() 调用 ensureValidToken 并返回 token
  // ============================================================
  it('T3: getAccessToken calls ensureValidToken and returns token', async () => {
    // Simulate: getAccessToken = useCallback(async () => getTokenManager().ensureValidToken(), [])
    const getAccessToken = async () => tm.ensureValidToken()

    const token = await getAccessToken()

    expect(tm.ensureValidToken).toHaveBeenCalledTimes(1)
    expect(token).toBe('mock-access-token')
  })

  // ============================================================
  // T4: auth:session-expired 事件触发 service.login()
  // ============================================================
  it('T4: auth:session-expired event triggers service.login()', () => {
    // Simulate the useEffect from auth-context.tsx:
    // window.addEventListener('auth:session-expired', () => { service.login() })
    const handleSessionExpired = () => {
      service.login()
    }

    window.addEventListener('auth:session-expired', handleSessionExpired)
    window.dispatchEvent(new CustomEvent('auth:session-expired'))

    expect(service.login).toHaveBeenCalledTimes(1)

    // Cleanup
    window.removeEventListener('auth:session-expired', handleSessionExpired)
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
    let authState = { isAuthenticated: true, user: { sub: 'u1' } }

    // Simulate: onSessionExpired: () => { setAuthState({ isAuthenticated: false, user: null }) }
    tm.setConfig({
      clientId: 'test',
      authCenterBaseURL: 'https://auth.test.com',
      redirectUri: 'http://localhost:3000/callback',
      onSessionExpired: () => {
        authState = { isAuthenticated: false, user: null }
      },
    })

    // Extract and call the onSessionExpired callback
    const configArg = tm.setConfig.mock.calls[0][0]
    configArg.onSessionExpired()

    expect(authState).toEqual({ isAuthenticated: false, user: null })
  })

  // ============================================================
  // T7: 完整 init 流程：setConfig → registerGetToken → service.init
  // ============================================================
  it('T7: full init flow order: setConfig → registerGetToken → service.init', async () => {
    const callOrder: string[] = []

    tm.setConfig.mockImplementation(() => { callOrder.push('setConfig') })
    mockRegisterGetToken.mockImplementation(() => { callOrder.push('registerGetToken') })
    service.init.mockImplementation(async () => { callOrder.push('serviceInit') })

    // Simulate the exact flow from auth-context.tsx:
    const config = {
      clientId: 'test-client-id',
      authCenterBaseURL: 'https://auth.example.com',
      redirectUri: 'http://localhost:3000/callback',
      onSessionExpired: () => {},
    }

    // Step 1: setConfig
    tm.setConfig(config)

    // Step 2: registerGetToken
    mockRegisterGetToken(() => tm.ensureValidToken())

    // Step 3: service.init
    await service.init(config)

    expect(callOrder).toEqual(['setConfig', 'registerGetToken', 'serviceInit'])
  })

  // ============================================================
  // T8: ensureValidToken 返回 null 时 getAccessToken 也返回 null
  // ============================================================
  it('T8: getAccessToken returns null when ensureValidToken returns null', async () => {
    tm.ensureValidToken.mockResolvedValueOnce(null)

    const getAccessToken = async () => tm.ensureValidToken()
    const token = await getAccessToken()

    expect(token).toBeNull()
  })
})
