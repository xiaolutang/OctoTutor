import { test, expect } from "@playwright/test"

/**
 * Dev Sandbox 生产环境保护测试
 *
 * Playwright baseURL 指向 Docker 生产部署 (octotutor.localhost)。
 * 这些测试验证 /dev 路由在生产环境中不可访问。
 */
test.describe("Dev Sandbox 生产环境保护", () => {
  test("/dev 在生产环境返回 404", async ({ page }) => {
    const response = await page.goto("/dev")
    // 页面应显示 404（被 middleware 拦截或构建时已排除）
    await expect(page.locator("h1")).toHaveText("404")
    expect(response!.status()).toBe(404)
  })

  test("/dev 子路径在生产环境返回 404", async ({ page }) => {
    const response = await page.goto("/dev/some-test")
    await expect(page.locator("h1")).toHaveText("404")
    expect(response!.status()).toBe(404)
  })
})
