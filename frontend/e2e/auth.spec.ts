import { test, expect } from "@playwright/test"
import { loginViaAuthCenter, TEST_USER, TIMEOUTS } from "./helpers"

test.describe("OctoTutor Auth Integration", () => {
  test("首页加载正常，显示登录按钮", async ({ page }) => {
    await page.goto("/")
    await expect(page).toHaveTitle(/章鱼哥解题/)
    await expect(page.locator("text=登录").first()).toBeVisible()
  })

  test("/chat 受保护路由重定向到认证中心", async ({ page }) => {
    await page.goto("/chat")
    await expect(page).toHaveURL(/auth\.localhost/, { timeout: TIMEOUTS.AUTH_FORM })
  })

  test("完整 OAuth 登录流程", async ({ page }) => {
    await loginViaAuthCenter(page)

    // 验证用户名显示在页面中
    const pageContent = await page.content()
    expect(pageContent).toContain(TEST_USER.username)
  })

  test("登录后访问 /chat 页面成功", async ({ page }) => {
    await loginViaAuthCenter(page)

    // 访问受保护页面
    await page.goto("/chat")
    // 等待页面加载，验证停留在 /chat
    await expect(page).toHaveURL(/\/chat/)
    const pageContent = await page.content()
    expect(pageContent).toContain("章鱼哥")
  })

  test("登录后退出", async ({ page }) => {
    await loginViaAuthCenter(page)

    // 点击退出按钮
    await page.locator("button:has-text('退出')").first().click()
    // 退出后应显示登录按钮
    await expect(page.locator("text=登录").first()).toBeVisible({ timeout: 10000 })
  })

  test("错误密码登录失败", async ({ page }) => {
    await page.goto("/")
    await page.locator("button:has-text('登录'), a:has-text('登录')").first().click()
    await page.waitForURL(/auth\.localhost/, { timeout: TIMEOUTS.AUTH_FORM })

    await page.locator("#username").fill(TEST_USER.username)
    await page.locator("#password").fill("wrong_password")
    await page.locator("#btn-submit").click()

    // 应停留在认证中心，显示错误提示
    await page.waitForTimeout(2000)
    expect(page.url()).toContain("auth.localhost")
  })
})
