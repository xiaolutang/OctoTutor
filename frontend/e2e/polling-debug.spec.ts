import { test, expect } from "@playwright/test"
import { loginViaAuthCenter } from "./helpers"

test.describe("服务端行为验证", () => {
  test("刷新后服务端是否继续处理 AI 回复", async ({ page }) => {
    test.setTimeout(120_000)
    await loginViaAuthCenter(page)
    await page.goto("/chat")
    await expect(page.locator("aside")).toBeVisible()
    await expect(page.locator("main.overflow-hidden").getByText("加载中...")).toBeHidden({ timeout: 10_000 })

    const input = page.getByPlaceholder("输入问题...")

    // Step 1: 新建对话 + 发消息 + 等完整回复完成（正常流程）
    await page.getByRole("button", { name: /新建对话/ }).click()
    await page.waitForTimeout(500)
    await input.fill("1+1等于几 server-test-normal")
    await input.press("Enter")

    // 等正常回复完成
    await page.getByRole("button", { name: "停止" }).waitFor({ state: "hidden", timeout: 60_000 })
    await page.waitForTimeout(1_000)

    // 获取当前对话 ID（从 sidebar）
    const sidebarActive = page.locator("aside .bg-accent")
    await expect(sidebarActive).toBeVisible({ timeout: 5_000 })

    // 记住当前对话数
    const convCountBefore = await page.evaluate(async () => {
      const resp = await fetch("/api/conversations?limit=20")
      const data = await resp.json()
      return data?.items?.length ?? -1
    })
    console.log("=== 正常回复完成，对话数 ===", convCountBefore)

    // Step 2: 再建一个新对话，发消息后立刻刷新
    await page.getByRole("button", { name: /新建对话/ }).click()
    await page.waitForTimeout(500)
    await input.fill("2+2等于几 server-test-instant-refresh")
    await input.press("Enter")

    // 立刻刷新
    await page.reload()

    // 等页面加载
    await expect(page.locator("aside")).toBeVisible({ timeout: 10_000 })
    await expect(page.locator("main.overflow-hidden").getByText("加载中...")).toBeHidden({ timeout: 10_000 })
    await page.waitForTimeout(2_000)

    // 获取刷新后加载的 activeId
    const activeIdAfterRefresh = await page.evaluate(() =>
      sessionStorage.getItem("octotutor_active_conversation_id"),
    )
    console.log("=== 刷新后 activeId ===", activeIdAfterRefresh)

    // Step 3: 等 10 秒让服务端处理
    console.log("=== 等待 10 秒让服务端处理 ===")
    await page.waitForTimeout(10_000)

    // Step 4: 手动调用 API 检查对话消息
    const messagesAfter10s = await page.evaluate(async (convId) => {
      const url = convId
        ? `/api/conversations/current?conversation_id=${encodeURIComponent(convId)}`
        : "/api/conversations/current"
      const resp = await fetch(url)
      if (resp.status === 204) return { status: 204, messages: [] }
      const data = await resp.json()
      return {
        status: resp.status,
        messages: data.messages?.map((m: any) => ({
          role: m.role,
          content_length: m.content?.length || 0,
          status: m.status,
        })),
      }
    }, activeIdAfterRefresh)

    console.log("=== 10 秒后消息状态 ===")
    console.log(JSON.stringify(messagesAfter10s, null, 2))

    // Step 5: 再等 20 秒（总共 30 秒），再次检查
    console.log("=== 再等 20 秒 ===")
    await page.waitForTimeout(20_000)

    const messagesAfter30s = await page.evaluate(async (convId) => {
      const url = convId
        ? `/api/conversations/current?conversation_id=${encodeURIComponent(convId)}`
        : "/api/conversations/current"
      const resp = await fetch(url)
      if (resp.status === 204) return { status: 204, messages: [] }
      const data = await resp.json()
      return {
        status: resp.status,
        messages: data.messages?.map((m: any) => ({
          role: m.role,
          content_length: m.content?.length || 0,
          status: m.status,
          content_preview: m.content?.substring(0, 100) || "",
        })),
      }
    }, activeIdAfterRefresh)

    console.log("=== 30 秒后消息状态 ===")
    console.log(JSON.stringify(messagesAfter30s, null, 2))

    // 关键断言：30 秒后应该有 AI 回复
    const hasAiReply = messagesAfter30s.messages?.some(
      (m: any) => m.role === "ai" || m.role === "assistant",
    )
    console.log("=== 是否有 AI 回复 ===", hasAiReply)
  })
})
