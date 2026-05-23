import { TokenManager } from "@xlfoundry/auth-sdk-web"

/**
 * SharedTokenManager — 包装 TokenManager，保证 refreshTokens 并发安全
 *
 * 多个 API 同时 401 时，只触发一次 refreshTokens 网络请求，
 * 其余调用复用同一个 Promise 结果。
 *
 * 每次 refresh 完成后（无论成功失败）自动释放锁，
 * 下次 token 过期可以正常发起新的刷新请求。
 */
export class SharedTokenManager {
  private tm: TokenManager
  private refreshPromise: Promise<{ access_token: string } | null> | null = null

  constructor(tm: TokenManager) {
    this.tm = tm
  }

  setConfig(config: Parameters<TokenManager["setConfig"]>[0]): void {
    this.tm.setConfig(config)
  }

  getAccessToken(): string | null {
    return this.tm.getAccessToken()
  }

  async refreshTokens(): Promise<{ access_token: string } | null> {
    if (!this.refreshPromise) {
      this.refreshPromise = this._doRefresh()
    }
    return this.refreshPromise
  }

  private async _doRefresh(): Promise<{ access_token: string } | null> {
    try {
      return await this.tm.refreshTokens()
    } finally {
      this.refreshPromise = null
    }
  }

}
