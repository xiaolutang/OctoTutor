import { test, expect } from "@playwright/test"
import { loginViaAuthCenter } from "./helpers"

function messageList(page: import("@playwright/test").Page) {
  return page.locator("main.overflow-hidden").locator("div.overflow-y-auto")
}

test.describe("刷新中断 → 中断提示 → 重新生成", () => {
  test.beforeEach(async ({ page }) => {
    test.setTimeout(120_000)
    await loginViaAuthCenter(page)
    await page.goto("/chat")
    await expect(page.locator("aside")).toBeVisible()
    await expect(page.locator("main.overflow-hidden").getByText("加载中...")).toBeHidden({ timeout: 10_000 })
  })

  test("完整流程：发消息 → 刷新 → 占位可见 → 超时 → 中断提示 → 重新生成成功", async ({ page }) => {
    const input = page.getByPlaceholder("输入问题...")
    const list = messageList(page)

    // Step 1: 新建对话 + 发消息
    await page.getByRole("button", { name: /新建对话/ }).click()
    await page.waitForTimeout(500)
    await input.fill("3+3等于几 interrupt-recovery-test")
    await input.press("Enter")

    // Step 2: 立刻刷新
    await page.reload()
    await expect(page.locator("aside")).toBeVisible({ timeout: 10_000 })
    await expect(page.locator("main.overflow-hidden").getByText("加载中...")).toBeHidden({ timeout: 10_000 })

    // Step 3: 验证用户消息 + 占位 AI 消息
    await expect(list.locator("div.bg-primary").first()).toContainText("interrupt-recovery-test", { timeout: 10_000 })
    await expect(list.locator("div.bg-muted").first()).toBeVisible({ timeout: 10_000 })
    console.log("✓ 用户消息和占位 AI 消息可见")

    // Step 4: 等待轮询超时（10 polls × 3s = 30s）+ 一些余量
    console.log("等待轮询超时...")
    await expect(list.locator("div.bg-muted").first()).toContainText("中断", { timeout: 45_000 })
    console.log("✓ 中断提示出现")

    // Step 5: hover AI 气泡区域使重新生成按钮可见
    const aiBubble = list.locator("div.bg-muted").first()
    // Hover the entire message row (group container) to trigger button visibility
    await aiBubble.locator("xpath=ancestor::div[contains(@class,'group')]").hover()
    const regenerateBtn = page.locator("button[title='重新生成']").first()
    await expect(regenerateBtn).toBeVisible({ timeout: 5_000 })
    console.log("✓ 重新生成按钮可见")

    // Step 6: 点击重新生成
    await regenerateBtn.click({ force: true })

    // Step 7: 等待 AI 回复完成
    await expect(page.getByRole("button", { name: "停止" }).first()).toBeVisible({ timeout: 10_000 }).catch(() => {})
    await page.getByRole("button", { name: "停止" }).waitFor({ state: "hidden", timeout: 60_000 })
    await page.waitForTimeout(1_000)
    console.log("✓ 重新生成完成")

    // Step 8: 验证 AI 回复有实质内容
    const finalAiBubble = list.locator("div.bg-muted").first()
    const finalText = await finalAiBubble.innerText({ timeout: 5_000 })
    expect(finalText.length, "AI 回复应有实质内容").toBeGreaterThan(5)
    console.log("✓ AI 回复内容:", finalText.substring(0, 100))
  })

  test("正常对话刷新后消息恢复（无中断）", async ({ page }) => {
    const input = page.getByPlaceholder("输入问题...")
    const list = messageList(page)

    // 正常发消息 + 等回复完成
    await page.getByRole("button", { name: /新建对话/ }).click()
    await page.waitForTimeout(500)
    await input.fill("5+5等于几 normal-refresh-test")
    await input.press("Enter")

    // 等用户消息可见
    await expect(list.locator("div.bg-primary").first()).toContainText("normal-refresh-test", { timeout: 5_000 })

    // 等 AI 回复完成
    await expect(list.locator("div.bg-muted").first()).toBeVisible({ timeout: 30_000 })
    await page.getByRole("button", { name: "停止" }).waitFor({ state: "hidden", timeout: 60_000 })
    await page.waitForTimeout(1_000)

    // 刷新
    await page.reload()
    await expect(page.locator("aside")).toBeVisible({ timeout: 10_000 })
    await expect(page.locator("main.overflow-hidden").getByText("加载中...")).toBeHidden({ timeout: 10_000 })

    // 验证消息恢复（不应有占位/中断提示）
    await expect(list.locator("div.bg-primary").first()).toContainText("normal-refresh-test", { timeout: 10_000 })
    await expect(list.locator("div.bg-muted").first()).toBeVisible({ timeout: 10_000 })

    // 不应有"中断"提示（因为 AI 已回复）
    const aiText = await list.locator("div.bg-muted").first().innerText({ timeout: 5_000 })
    expect(aiText).not.toContain("中断")
    console.log("✓ 正常对话刷新后消息完整恢复")
  })
})
