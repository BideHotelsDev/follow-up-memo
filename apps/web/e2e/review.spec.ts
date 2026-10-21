import AxeBuilder from "@axe-core/playwright"
import { expect, test, type Page } from "@playwright/test"

// The mock data: two made-up meetings processed by POST /api/admin/runs (run once in beforeAll).
const DAVID = "david@liddellpropertyinvestments.com"

async function signIn(page: Page, email: string) {
  const resp = await page.request.post("/api/auth/dev-login", { data: { email } })
  expect(resp.status()).toBe(204)
}

test.beforeAll(async ({ request }) => {
  await request.post("/api/auth/dev-login", { data: { email: "kyle@bidehotels.com" } })
  expect((await request.post("/api/admin/runs")).ok()).toBeTruthy()
})

/** Press Save on Admin → settings and wait for the server to store it. */
async function save(page: Page) {
  const stored = page.waitForResponse((r) => r.url().endsWith("/api/admin/settings") && r.request().method() === "PUT")
  await page.getByRole("button", { name: "Save" }).click()
  expect((await stored).ok()).toBeTruthy()
}

async function noSidewaysScroll(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
}

async function accessible(page: Page) {
  const results = await new AxeBuilder({ page }).analyze()
  const serious = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical")
  expect(serious.map((v) => `${v.id}: ${v.nodes[0]?.target}`)).toEqual([])
}

test("every page loads, fits the screen and passes axe", async ({ page }) => {
  await signIn(page, DAVID)
  for (const [path, heading] of [
    ["/", /Good (morning|afternoon|evening), David/],
    ["/impact", "Impact"],
    ["/meetings", "Meetings"],
    ["/emails", "Email drafts"],
    ["/slack", "Slack drafts"],
    ["/tasks", "Tasks"],
    ["/how", "How it works"],
    ["/admin/categories", "Admin"],
    ["/admin/channels", "Admin"],
  ] as const) {
    await page.goto(path)
    await expect(page.getByRole("heading", { level: 1, name: heading })).toBeVisible()
    await noSidewaysScroll(page)
    await accessible(page)
  }
})

test("David answers a question and approves a channel update", async ({ page }) => {
  await signIn(page, DAVID)
  await page.goto("/")
  await expect(page.getByRole("heading", { name: "Needs your answer" })).toBeVisible()
  const question = page.getByText(/Who should own this: Check the Canary/)
  // The desktop and phone projects share the data: whichever runs second finds it answered and approved.
  if (await question.isVisible()) {
    await page.getByRole("button", { name: "Russell", exact: true }).click()
    await expect(question).toHaveCount(0)
  }

  await page.goto("/slack")
  const card = page.locator("article", { hasText: "#revenue" })
  await expect(card.getByText(/Draft|Approved/)).toBeVisible()
  if (await card.getByRole("button", { name: "Approve & post" }).isVisible()) {
    await card.getByRole("button", { name: "Approve & post" }).click()
  }
  await expect(card.getByText("Approved · posted")).toBeVisible()
})

test("Dictated text lands in the boxes and saves, as Wispr Flow types it", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"])
  await signIn(page, DAVID)
  await page.goto("/")
  const answer = page.getByLabel("Your answer")
  if (await answer.isVisible()) {
    await answer.click()
    // Wispr inserts text directly, or pastes it; check both reach the form.
    await page.keyboard.insertText("Yes, from the week before.")
    await page.keyboard.press("Enter")
    await page.evaluate(() => navigator.clipboard.writeText("Ask Russell to tell the laundry."))
    await page.keyboard.press("ControlOrMeta+V")
    await expect(answer).toHaveValue("Yes, from the week before.\nAsk Russell to tell the laundry.")
    await page.keyboard.press("ControlOrMeta+Enter")
    await expect(page.getByText("Should the second laundry delivery day start before half-term?")).toHaveCount(0)
  }

  await page.goto("/slack")
  const card = page.locator("article", { hasText: "Russell" }).first()
  await card.getByRole("button", { name: "Edit" }).click()
  const message = card.getByLabel("Message")
  await message.press("ControlOrMeta+End")
  await page.keyboard.insertText(" Thanks, Russell.")
  await page.keyboard.press("ControlOrMeta+Enter")
  await expect(card.getByText(/Thanks, Russell\./)).toBeVisible()

  await page.goto("/how")
  await expect(page.getByRole("heading", { name: "Dictating with Wispr Flow" })).toBeVisible()
  await expect(page.getByText(/David, .*The View, .*PriceLabs/)).toBeVisible()
})

test("Tasks and meetings filter by employee", async ({ page }) => {
  await signIn(page, DAVID)
  await page.goto("/tasks")
  await page.getByRole("group", { name: "Owner" }).getByRole("button", { name: "Sam", exact: true }).click()
  await expect(page.getByText("Update the PriceLabs minimum-stay rule for The View to two nights")).toBeVisible()
  await expect(page.getByText("Ask the laundry about a second delivery day")).toHaveCount(0)

  await page.goto("/meetings")
  const items = page.locator('a[href^="/meetings/"]')
  await expect(items.first()).toBeVisible()
  const everyone = await items.count()
  await page.getByRole("combobox", { name: "Employee" }).click()
  await page.getByRole("option", { name: "Russell’s meetings" }).click()
  await expect(items).not.toHaveCount(everyone)
  await expect(page.getByRole("link", { name: /Housekeeping sync/ }).first()).toBeVisible()
  await expect(page.getByRole("combobox", { name: "Viewing as" })).toHaveCount(0)
})

test("A task's due date changes from its drawer", async ({ page }) => {
  await signIn(page, DAVID)
  await page.goto("/tasks")
  await page.getByRole("button", { name: /Ask the laundry about a second delivery day/ }).click()
  const due = page.getByLabel("Due")
  await due.fill("2031-01-03")
  await due.blur()
  await expect(page.getByRole("dialog").getByText("Open", { exact: true })).toBeVisible()
  await page.keyboard.press("Escape")
  await expect(page.getByText("Fri 3 Jan", { exact: true })).toBeVisible()
})

test("David manages meeting categories and filters by them", async ({ page }) => {
  await signIn(page, DAVID)
  await page.goto("/")
  await page.getByRole("link", { name: "Admin" }).first().click()
  await page.getByRole("link", { name: "Categories" }).click()
  const name = `Legal ${Date.now() % 100000}`
  await page.getByLabel("New category").fill(name)
  await page.getByRole("button", { name: "Add" }).click()
  await page.getByLabel(`What ${name} covers`).fill("Contracts, leases and disputes")
  await page.getByLabel(`What ${name} covers`).blur()
  await page.getByRole("switch", { name: `${name} is sensitive` }).click()
  await expect(page.getByRole("switch", { name: `${name} is sensitive` })).toBeChecked()
  await page.reload()
  await expect(page.getByLabel(`What ${name} covers`)).toHaveValue("Contracts, leases and disputes")

  await page.goto("/meetings")
  await page.getByRole("combobox", { name: "Category" }).click()
  await page.getByRole("option", { name: "Revenue" }).click()
  await expect(page.getByRole("link", { name: /Weekly revenue/ }).first()).toBeVisible()
  await expect(page.getByRole("link", { name: /Housekeeping sync/ })).toHaveCount(0)
})

test("David writes his own instructions for Claude", async ({ page }) => {
  await signIn(page, DAVID)
  await page.goto("/admin/settings")
  const box = page.getByLabel("When writing follow-up emails")
  await box.fill("Never mention our rates or occupancy to OTAs.")
  await save(page)
  await page.reload()
  await expect(page.getByLabel("When writing follow-up emails")).toHaveValue(
    "Never mention our rates or occupancy to OTAs.",
  )
  await box.fill("")
  await save(page)
})

test("David previews the weekly digest and switches on reminders", async ({ page }) => {
  await signIn(page, DAVID)
  await page.goto("/admin/settings")
  await page.getByRole("button", { name: "Preview this week’s digest" }).click()
  await expect(page.getByText(/David’s week in follow-ups/)).toBeVisible()
  await page.getByRole("switch", { name: "Send due-date reminders" }).click()
  await save(page)
  await page.goto("/how")
  await expect(page.getByText(/on weekdays, everyone with tasks due that day or overdue/)).toBeVisible()
  await page.goto("/admin/settings")
  await page.getByRole("switch", { name: "Send due-date reminders" }).click()
  await save(page)
})
