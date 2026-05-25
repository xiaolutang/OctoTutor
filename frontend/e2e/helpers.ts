import { type Page } from "@playwright/test"

/** 测试账号（通过环境变量传入，运行时必须设置 E2E_USERNAME / E2E_PASSWORD） */
export const TEST_USER = {
  username: process.env.E2E_USERNAME!,
  password: process.env.E2E_PASSWORD!,
}

/** 超时配置 */
export const TIMEOUTS = {
  AUTH_NAV: 15_000,
  AUTH_FORM: 10_000,
  /** SSE 流式回复等待上限 */
  SSE_REPLY: 30_000,
}

/** 完成OAuth登录并等待回到 OctoTutor */
export async function loginViaAuthCenter(page: Page) {
  await page.goto("/")
  await page.locator("button:has-text('登录'), a:has-text('登录')").first().click()
  await page.waitForURL(/auth\.localhost/, { timeout: TIMEOUTS.AUTH_FORM })

  await page.locator("#username").fill(TEST_USER.username)
  await page.locator("#password").fill(TEST_USER.password)
  await page.locator("#btn-submit").click()

  // 等待回调完成并回到 OctoTutor，用退出按钮出现作为登录成功标志
  await page.waitForURL(/octotutor\.localhost/, { timeout: TIMEOUTS.AUTH_NAV })
  await page.locator("button:has-text('退出')").first().waitFor({ state: "visible", timeout: 10_000 })
}
