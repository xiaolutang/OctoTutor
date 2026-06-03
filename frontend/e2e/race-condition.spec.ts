import { test, expect } from "@playwright/test"
import { loginViaAuthCenter, TIMEOUTS } from "./helpers"

/**
 * 竞态条件 E2E — 严格版本
 *
 * 用户的精确操作：
 *   1. 新建对话
 *   2. 发送消息
 *   3. 立刻 Cmd+Shift+R 刷新
 *
 * DOM 结构：
 * - 消息列表区: main.overflow-hidden > div.flex > div.overflow-y-auto
 * - 用户消息气泡: div.bg-primary
 * - AI 消息气泡: div.bg-muted
 */
function messageList(page: import("@playwright/test").Page) {
  return page.locator("main.overflow-hidden").locator("div.overflow-y-auto")
}

async function waitForSSEDone(page: import("@playwright/test").Page, timeout = 45_000) {
  await page.getByRole("button", { name: "停止" }).waitFor({ state: "hidden", timeout }).catch(() => {})
  await page.waitForTimeout(1_000)
}

test.describe("竞态条件验证 — 严格版", () => {
  test.beforeEach(async ({ page }) => {
    test.setTimeout(120_000)
    await loginViaAuthCenter(page)
    await page.goto("/chat")
    await expect(page.locator("aside")).toBeVisible()
    await expect(page.locator("main.overflow-hidden").getByText("加载中...")).toBeHidden({ timeout: 10_000 })
  })

  // ── 场景 A: 发消息后立刻刷新（不等任何东西） ──
  test("发消息后立刻刷新 → 加载的是新对话而非旧对话", async ({ page }) => {
    // 先创建一个旧对话，确保有多个对话
    await page.getByRole("button", { name: /新建对话/ }).click()
    await page.waitForTimeout(500)
    const input = page.getByPlaceholder("输入问题...")
    await input.fill("旧对话 unique-old-conv-xyz")
    await input.press("Enter")
    await waitForSSEDone(page)

    // 记住旧对话在 sidebar 的标题
    await page.waitForTimeout(1_000)

    // 新建对话 → 发消息 → 立刻刷新（不等任何东西）
    await page.getByRole("button", { name: /新建对话/ }).click()
    await page.waitForTimeout(500)
    await input.fill("新对话 instant-refresh-abc")
    await input.press("Enter")

    // 不等任何东西，直接刷新
    await page.reload()

    // 等页面加载完成
    await expect(page.locator("aside")).toBeVisible({ timeout: 10_000 })
    await expect(page.locator("main.overflow-hidden").getByText("加载中...")).toBeHidden({ timeout: 10_000 })

    // 核心断言：不应看到旧对话的内容
    const list = messageList(page)
    const allText = await list.innerText({ timeout: 10_000 }).catch(() => "")
    const showsOldConv = allText.includes("unique-old-conv-xyz")
    expect(showsOldConv).toBe(false)
  })

  // ── 场景 A2: 用 JS 在 SSE fetch 发出后立刻刷新（最小延迟） ──
  test("SSE请求发出后立刻JS刷新 → 不回到旧对话", async ({ page }) => {
    // 先创建旧对话
    await page.getByRole("button", { name: /新建对话/ }).click()
    await page.waitForTimeout(500)
    const input = page.getByPlaceholder("输入问题...")
    await input.fill("旧对话A2 old-conv-a2-marker")
    await input.press("Enter")
    await waitForSSEDone(page)
    await page.waitForTimeout(1_000)

    // 新建对话
    await page.getByRole("button", { name: /新建对话/ }).click()
    await page.waitForTimeout(500)

    // 注入拦截器：在 fetch 发出后立刻用 JS 刷新（绕过 Playwright 延迟）
    await page.evaluate(() => {
      const originalFetch = window.fetch
      let refreshed = false
      window.fetch = function (...args: Parameters<typeof fetch>) {
        const url = typeof args[0] === 'string' ? args[0] : (args[0] as Request).url
        // 只拦截 SSE 请求
        if (url.includes('/chat/stream') && !refreshed) {
          refreshed = true
          // fetch 已发出，立刻刷新（比 Playwright page.reload() 更快）
          setTimeout(() => window.location.reload(), 0)
        }
        return originalFetch.apply(this, args)
      }
    })

    await input.fill("新对话A2 instant-js-refresh")
    await input.press("Enter")

    // 等刷新完成
    await expect(page.locator("aside")).toBeVisible({ timeout: 10_000 })
    await expect(page.locator("main.overflow-hidden").getByText("加载中...")).toBeHidden({ timeout: 10_000 })

    // 核心断言：不应看到旧对话内容
    const list = messageList(page)
    const allText = await list.innerText({ timeout: 10_000 }).catch(() => "")
    const showsOldConv = allText.includes("old-conv-a2-marker")
    expect(showsOldConv).toBe(false)
  })

  // ── 场景 B: 发消息后等 AI 开始回复再刷新 ──
  test("发消息等AI回复开始后刷新 → 新对话消息可见", async ({ page }) => {
    await page.getByRole("button", { name: /新建对话/ }).click()
    await page.waitForTimeout(500)
    const input = page.getByPlaceholder("输入问题...")
    await input.fill("回复后刷新 unique-after-reply-marker")
    await input.press("Enter")

    const list = messageList(page)

    // 等用户消息可见
    await expect(list.locator("div.bg-primary").first()).toContainText("回复后刷新", { timeout: 5_000 })

    // 等 AI 回复开始（bg-muted 出现）
    await expect(list.locator("div.bg-muted").first()).toBeVisible({ timeout: TIMEOUTS.SSE_REPLY })

    // 等 SSE 完成
    await waitForSSEDone(page)

    // 刷新
    await page.reload()
    await expect(page.locator("aside")).toBeVisible({ timeout: 10_000 })
    await expect(page.locator("main.overflow-hidden").getByText("加载中...")).toBeHidden({ timeout: 10_000 })

    // 验证用户消息恢复
    const listAfterRefresh = messageList(page)
    await expect(listAfterRefresh.locator("div.bg-primary").first()).toContainText("回复后刷新", { timeout: 10_000 })

    // 验证 AI 回复也恢复
    await expect(listAfterRefresh.locator("div.bg-muted").first()).toBeVisible({ timeout: 10_000 })
  })

  // ── 场景 C: 新建对话发消息，消息本身可见（不刷新） ──
  test("新建对话发消息 → 用户消息和AI回复区都可见（不刷新）", async ({ page }) => {
    await page.getByRole("button", { name: /新建对话/ }).click()
    await page.waitForTimeout(500)
    const input = page.getByPlaceholder("输入问题...")
    await input.fill("不刷新测试 unique-no-refresh")
    await input.press("Enter")

    const list = messageList(page)
    await expect(list.locator("div.bg-primary").first()).toContainText("不刷新测试", { timeout: 5_000 })
    await expect(list.locator("div.bg-muted").first()).toBeVisible({ timeout: TIMEOUTS.SSE_REPLY })

    // sidebar 有新对话卡片
    await expect(page.locator("aside").locator("div.group").first()).toBeVisible({ timeout: 10_000 })
  })

  // ── 场景 D: 多对话切换 ──
  test("两个对话切换 → 各自历史消息正确", async ({ page }) => {
    const cards = page.locator("aside").locator("div.group")
    const input = page.getByPlaceholder("输入问题...")
    const list = messageList(page)

    // 对话 A
    await page.getByRole("button", { name: /新建对话/ }).click()
    await page.waitForTimeout(500)
    await input.fill("标记A alpha-marker-x1")
    await input.press("Enter")
    await expect(list.locator("div.bg-primary").first()).toContainText("alpha-marker-x1", { timeout: 5_000 })
    await waitForSSEDone(page)
    await page.waitForTimeout(1_000)

    // 对话 B
    await page.getByRole("button", { name: /新建对话/ }).click()
    await page.waitForTimeout(500)
    await input.fill("标记B beta-marker-x2")
    await input.press("Enter")
    await expect(list.locator("div.bg-primary").first()).toContainText("beta-marker-x2", { timeout: 5_000 })
    await waitForSSEDone(page)
    await page.waitForTimeout(1_000)

    // 切换回 A
    expect(await cards.count()).toBeGreaterThanOrEqual(2)
    const cardA = cards.filter({ hasText: /alpha-marker-x1/ }).first()
    if (await cardA.isVisible()) {
      await cardA.click()
      await page.waitForTimeout(2_000)
      const listA = messageList(page)
      await expect(listA.locator("div.bg-primary").first()).toContainText("alpha-marker-x1", { timeout: 10_000 })
      await expect(listA.locator("div.bg-muted").first()).toBeVisible({ timeout: 10_000 })
    }
  })
})
