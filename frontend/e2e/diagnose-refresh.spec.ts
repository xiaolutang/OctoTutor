import { test, expect } from "@playwright/test"
import { loginViaAuthCenter } from "./helpers"

function messageList(page: import("@playwright/test").Page) {
  return page.locator("main.overflow-hidden").locator("div.overflow-y-auto")
}

test.describe("诊断：刷新后用户看到什么", () => {
  test.beforeEach(async ({ page }) => {
    test.setTimeout(120_000)
    await loginViaAuthCenter(page)
    await page.goto("/chat")
    await expect(page.locator("aside")).toBeVisible()
    await expect(page.locator("main.overflow-hidden").getByText("加载中...")).toBeHidden({ timeout: 10_000 })
  })

  test("诊断：新建对话 → 发消息 → 立刻刷新 → 截图 + 全文输出", async ({ page }) => {
    const input = page.getByPlaceholder("输入问题...")
    const list = messageList(page)

    // Step 1: 新建对话
    await page.getByRole("button", { name: /新建对话/ }).click()
    await page.waitForTimeout(500)

    // Step 2: 发送消息（用唯一标记）
    await input.fill("诊断测试 diagnostic-marker-QWERTY")
    await input.press("Enter")

    // Step 3: 立刻刷新（不等任何 SSE 事件）
    await page.reload()

    // Step 4: 等页面完全加载
    await expect(page.locator("aside")).toBeVisible({ timeout: 10_000 })
    await expect(page.locator("main.overflow-hidden").getByText("加载中...")).toBeHidden({ timeout: 10_000 })
    await page.waitForTimeout(2_000) // 额外等 2s 让消息加载

    // Step 5: 截图
    await page.screenshot({ path: "test-results/diagnose-refresh.png", fullPage: true })

    // Step 6: 输出消息区全文
    const allText = await list.innerText({ timeout: 5_000 }).catch(() => "<empty>")
    console.log("=== 消息区全文 ===")
    console.log(allText)
    console.log("=================")

    // Step 7: 输出 sidebar 选中的对话
    const activeItem = page.locator("aside .bg-accent")
    const activeText = await activeItem.innerText({ timeout: 5_000 }).catch(() => "<no active>")
    console.log("=== Sidebar 选中项 ===")
    console.log(activeText)
    console.log("======================")

    // Step 8: 输出 sessionStorage
    const storedId = await page.evaluate(() => sessionStorage.getItem("octotutor_active_conversation_id"))
    console.log("=== sessionStorage ===")
    console.log("activeId:", storedId)
    console.log("=======================")

    // Step 9: 检查用户消息气泡
    const userBubbles = list.locator("div.bg-primary")
    const userCount = await userBubbles.count()
    console.log("=== 用户消息气泡数量 ===")
    console.log(userCount)
    console.log("========================")

    // Step 10: 检查 AI 消息气泡
    const aiBubbles = list.locator("div.bg-muted")
    const aiCount = await aiBubbles.count()
    console.log("=== AI 消息气泡数量 ===")
    console.log(aiCount)
    console.log("=======================")

    // 关键断言
    expect(allText, "消息区不应为空").not.toBe("<empty>")
    expect(allText, "应看到刚发的诊断标记").toContain("diagnostic-marker-QWERTY")
  })

  test("诊断：发消息 → 等 SSE init 到达 → 立刻刷新", async ({ page }) => {
    const input = page.getByPlaceholder("输入问题...")
    const list = messageList(page)

    // 新建对话
    await page.getByRole("button", { name: /新建对话/ }).click()
    await page.waitForTimeout(500)

    // 注入 fetch 拦截器：记录 SSE init 中的 conversation_id
    const sseInitId = await page.evaluate(() => {
      return new Promise<string | null>((resolve) => {
        const origFetch = window.fetch
        let resolved = false
        window.fetch = function (...args: Parameters<typeof fetch>) {
          const url = typeof args[0] === "string" ? args[0] : (args[0] as Request).url
          const result = origFetch.apply(this, args)

          if (url.includes("/chat/stream") && !resolved) {
            result.then(async (response) => {
              if (!response.ok || !response.body) return
              const reader = response.body.getReader()
              const decoder = new TextDecoder()
              let remaining = ""

              while (true) {
                const { done, value } = await reader.read()
                if (done) break
                const chunk = decoder.decode(value, { stream: true })
                remaining += chunk
                // 查找 init 事件
                const initMatch = remaining.match(/event:\s*init\s*\ndata:\s*\{"conversation_id"\s*:\s*"([^"]+)"\}/)
                if (initMatch && !resolved) {
                  resolved = true
                  resolve(initMatch[1])
                }
              }
              if (!resolved) resolve(null)
            }).catch(() => { if (!resolved) resolve(null) })
          }
          return result
        }
        // 超时
        setTimeout(() => { if (!resolved) resolve(null) }, 30_000)
      })
    })

    // 发送消息
    await input.fill("诊断测试2 diagnostic-marker-ASDFGH")
    await input.press("Enter")

    // 等 SSE init 到达
    console.log("=== SSE init conversation_id ===")
    console.log(sseInitId)
    console.log("=================================")

    // 等 init 到达后立刻刷新
    if (sseInitId) {
      await page.waitForTimeout(100) // 给 INSERT_NEW 一点时间
    }
    await page.reload()

    // 等页面完全加载
    await expect(page.locator("aside")).toBeVisible({ timeout: 10_000 })
    await expect(page.locator("main.overflow-hidden").getByText("加载中...")).toBeHidden({ timeout: 10_000 })
    await page.waitForTimeout(2_000)

    // 截图
    await page.screenshot({ path: "test-results/diagnose-refresh-with-init.png", fullPage: true })

    // 输出信息
    const allText = await list.innerText({ timeout: 5_000 }).catch(() => "<empty>")
    console.log("=== 消息区全文 ===")
    console.log(allText)

    const storedId = await page.evaluate(() => sessionStorage.getItem("octotutor_active_conversation_id"))
    console.log("=== sessionStorage activeId ===")
    console.log(storedId)
    console.log("=== SSE init conversation_id ===")
    console.log(sseInitId)
    console.log("=== 是否匹配 ===")
    console.log(storedId === sseInitId)

    // 核心断言
    expect(allText, "消息区不应为空").not.toBe("<empty>")
    expect(allText, "应看到诊断标记").toContain("diagnostic-marker-ASDFGH")
  })
})
