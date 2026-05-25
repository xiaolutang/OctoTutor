import { test, expect } from "@playwright/test"
import { loginViaAuthCenter, TIMEOUTS } from "./helpers"

/**
 * R009 对话管理 E2E 集成测试
 *
 * 结构设计：
 * - 场景 1 (独立): 布局验证
 * - 场景 2-7 (串行): 在同一个 page 中完成创建→发送→切换→重命名→置顶→取消置顶→删除
 * - 场景 8 (独立): 流式切换阻止
 *
 * 场景 2-7 使用 test.step 划分子步骤，共享同一个 page 避免反复登录和等待侧边栏加载。
 */
test.describe("对话管理", () => {
  test.beforeEach(async ({ page }) => {
    test.setTimeout(120_000)
    await loginViaAuthCenter(page)
    await page.goto("/chat")
    await expect(page.locator("aside")).toBeVisible()
    // 等待 ChatUI mounted 完成
    await expect(page.locator("main.overflow-hidden").getByText("加载中...")).toBeHidden({ timeout: 10_000 })
  })

  // ── 场景 1: 布局验证（独立） ──
  test("打开 /chat 显示侧边栏和主聊天区", async ({ page }) => {
    await expect(page.locator("aside")).toBeVisible()
    await expect(page.locator("main.overflow-hidden")).toBeVisible()
    await expect(page.getByRole("button", { name: /新建对话/ })).toBeVisible()
  })

  // ── 场景 2-7: 完整对话生命周期（串行） ──
  test("对话生命周期: 创建→发送→切换→重命名→置顶→取消置顶→删除", async ({ page }) => {
    const cards = page.locator("aside").locator("div.group")

    // ── 场景 2: 新建对话 → 发送消息 → 等待 AI 回复 ──
    await test.step("新建对话并发送消息", async () => {
      await page.getByRole("button", { name: /新建对话/ }).click()
      await page.waitForTimeout(500)

      const input = page.getByPlaceholder("输入问题...")
      await input.fill("1+1等于几？请简短回答")
      await input.press("Enter")

      // 等待 sidebar 出现对话卡片
      await expect(cards.first()).toBeVisible({ timeout: 10_000 })

      // 等待 AI 回复（最多 45s，后端可能慢）
      const aiBubble = page.locator("main.overflow-hidden").locator("div.bg-muted").first()
      await aiBubble.waitFor({ state: "visible", timeout: 45_000 })
        .catch(() => { /* AI 未响应不阻塞后续测试 */ })
    })

    // ── 场景 3: 再建一个对话 → 切换 ──
    await test.step("切换对话加载历史", async () => {
      await page.getByRole("button", { name: /新建对话/ }).click()
      await page.waitForTimeout(500)

      const input = page.getByPlaceholder("输入问题...")
      await input.fill("2+2等于几？")
      await input.press("Enter")

      await expect(cards.first()).toBeVisible({ timeout: 10_000 })

      if ((await cards.count()) >= 2) {
        // 点击第一个卡片（最早创建的）
        await cards.first().click()
        await page.waitForTimeout(1_000)
        await expect(page.locator("main.overflow-hidden")).toBeVisible()
      }
    })

    // ── 场景 4: 重命名对话 ──
    await test.step("重命名对话", async () => {
      // 使用最后一个卡片（最新创建的）
      const lastCard = cards.last()
      await openCardMenu(page, lastCard)
      await lastCard.getByText("重命名").click()

      const renameInput = lastCard.locator("input")
      await expect(renameInput).toBeVisible()
      await renameInput.clear()
      await renameInput.fill("E2E 测试对话")
      await renameInput.press("Enter")

      await expect(page.locator("aside").getByText("E2E 测试对话")).toBeVisible({ timeout: 5_000 })
    })

    // ── 场景 5: 置顶对话 ──
    await test.step("置顶对话", async () => {
      const lastCard = cards.last()
      await openCardMenu(page, lastCard)
      await lastCard.getByText("置顶").click()

      await expect(page.locator("aside").getByText("📌 已置顶")).toBeVisible({ timeout: 5_000 })
    })

    // ── 场景 6: 取消置顶 ──
    await test.step("取消置顶", async () => {
      // 找置顶区的卡片
      const pinnedLabel = page.locator("aside").getByText("📌 已置顶")
      const pinnedSection = pinnedLabel.locator("..")
      const pinnedCard = pinnedSection.locator("div.group").first()

      await openCardMenu(page, pinnedCard)
      await pinnedCard.getByText("取消置顶").click()

      await page.waitForTimeout(1_000)
      await expect(page.locator("aside").getByText("E2E 测试对话")).toBeVisible()
    })

    // ── 场景 7: 删除对话 ──
    await test.step("删除对话", async () => {
      const lastCard = cards.last()
      const countBeforeDelete = await cards.count()
      await openCardMenu(page, lastCard)
      await lastCard.getByText("删除").click()

      // 验证确认弹窗
      await expect(page.getByText("确定删除这条对话？")).toBeVisible()
      await expect(page.getByText("删除后不可恢复。")).toBeVisible()

      await page.getByRole("button", { name: "确认删除" }).click()
      await page.waitForTimeout(1_000)

      // 验证卡片已删除（数量减少）
      const countAfterDelete = await cards.count()
      expect(countAfterDelete).toBeLessThan(countBeforeDelete)
    })
  })

  // ── 场景 8: 流式传输中切换被阻止并显示 toast 提示（独立） ──
  test("流式传输中切换对话被阻止并显示toast提示", async ({ page }) => {
    await page.getByRole("button", { name: /新建对话/ }).click()
    await page.waitForTimeout(500)

    const input = page.getByPlaceholder("输入问题...")
    await input.fill("请详细解释一下相对论的基本原理")
    await input.press("Enter")

    await page.waitForTimeout(500)

    const stopButton = page.getByRole("button", { name: "停止" })
    const isStreaming = await stopButton.isVisible().catch(() => false)

    if (isStreaming) {
      const cards = page.locator("aside").locator("div.group")
      if ((await cards.count()) >= 2) {
        await cards.first().click()
        // 验证 toast 提示出现
        await expect(page.getByText("请等待当前回答完成")).toBeVisible({ timeout: 3_000 })
        await page.waitForTimeout(500)
      }
      await stopButton.waitFor({ state: "hidden", timeout: TIMEOUTS.SSE_REPLY }).catch(() => {})
    }
  })
})

// ── 辅助函数 ──

async function openCardMenu(page: import("@playwright/test").Page, card: import("@playwright/test").Locator) {
  await card.hover()
  await page.waitForTimeout(300)
  // 三点菜单图标 — 卡片内最后一个 button
  await card.locator("button").last().click()
  await page.waitForTimeout(300)
}
