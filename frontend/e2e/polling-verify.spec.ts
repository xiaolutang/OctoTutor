import { test, expect } from "@playwright/test"
import { loginViaAuthCenter, TIMEOUTS } from "./helpers"

function messageList(page: import("@playwright/test").Page) {
  return page.locator("main.overflow-hidden").locator("div.overflow-y-auto")
}

async function waitForSSEDone(page: import("@playwright/test").Page, timeout = 45_000) {
  await page.getByRole("button", { name: "停止" }).waitFor({ state: "hidden", timeout }).catch(() => {})
  await page.waitForTimeout(1_000)
}

test.describe("刷新后 AI 回复轮询验证", () => {
  test.beforeEach(async ({ page }) => {
    test.setTimeout(120_000)
    await loginViaAuthCenter(page)
    await page.goto("/chat")
    await expect(page.locator("aside")).toBeVisible()
    await expect(page.locator("main.overflow-hidden").getByText("加载中...")).toBeHidden({ timeout: 10_000 })
  })

  test("新建对话 → 发消息 → 立刻刷新 → 占位提示可见 → AI 回复最终出现", async ({ page }) => {
    const input = page.getByPlaceholder("输入问题...")
    const list = messageList(page)

    // Step 1: 新建对话 + 发消息
    await page.getByRole("button", { name: /新建对话/ }).click()
    await page.waitForTimeout(500)
    await input.fill("1+1等于几 polling-verify-marker")
    await input.press("Enter")

    // Step 2: 立刻刷新（不等 SSE）
    await page.reload()

    // Step 3: 等页面加载完成
    await expect(page.locator("aside")).toBeVisible({ timeout: 10_000 })
    await expect(page.locator("main.overflow-hidden").getByText("加载中...")).toBeHidden({ timeout: 10_000 })

    // Step 4: 验证用户消息可见
    await expect(list.locator("div.bg-primary").first()).toContainText("polling-verify-marker", { timeout: 10_000 })

    // Step 5: 验证占位 AI 消息可见（"正在检索相关知识..."动画）
    await expect(list.locator("div.bg-muted").first()).toBeVisible({ timeout: 10_000 })
    const placeholderText = await list.locator("div.bg-muted").first().innerText({ timeout: 5_000 }).catch(() => "")
    console.log("=== 占位消息内容 ===")
    console.log(placeholderText)
    // 占位消息应包含状态提示文字
    expect(placeholderText).toMatch(/检索|生成|等待/)

    // Step 6: 等待 AI 回复完成（轮询会自动获取）
    // 最多等待 60 秒（轮询间隔 3s × 20 次）
    console.log("=== 等待 AI 回复（轮询中）===")
    const startTime = Date.now()

    // 等待 AI 回复有实际内容（不是空内容 + 正在检索）
    await page.waitForFunction(
      () => {
        const aiBubbles = document.querySelectorAll("main.overflow-hidden div.bg-muted")
        for (const bubble of aiBubbles) {
          const text = bubble.textContent || ""
          // AI 回复完成：有实际内容且不包含"检索/生成"状态提示
          if (text.length > 20 && !text.includes("检索") && !text.includes("生成")) {
            return true
          }
        }
        return false
      },
      { timeout: 60_000 },
    )

    const elapsed = ((Date.now() - startTime) / 1000).toFixed(1)
    console.log(`=== AI 回复到达，耗时 ${elapsed}s ===`)

    // Step 7: 最终验证 — AI 回复有实质内容
    const aiBubble = list.locator("div.bg-muted").first()
    const finalText = await aiBubble.innerText({ timeout: 5_000 })
    console.log("=== AI 回复内容（前 200 字）===")
    console.log(finalText.substring(0, 200))
    expect(finalText.length).toBeGreaterThan(10)
  })
})
