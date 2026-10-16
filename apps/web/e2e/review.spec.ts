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
    await expect(page.getByText("All caught up")).toBeVisible()
  }

  await page.goto("/slack")
  const card = page.locator("article", { hasText: "#revenue" })
  await expect(card.getByText(/Draft|Approved/)).toBeVisible()
  if (await card.getByRole("button", { name: "Approve & post" }).isVisible()) {
    await card.getByRole("button", { name: "Approve & post" }).click()
  }
  await expect(card.getByText("Approved · posted")).toBeVisible()
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
