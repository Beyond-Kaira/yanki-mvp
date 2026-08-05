import { test, expect, type Page } from '@playwright/test'

// Runs only against a live stack (DRY_RUN backend + web), like happy-path.
const baseURL = process.env.E2E_BASE_URL
const scenario = baseURL ? test : test.skip

const PASSWORD = 'correct-horse-battery'

function unique(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.floor(Math.random() * 100000)}@e2e.example`
}

async function signUp(
  page: Page,
  email: string,
  options: { organization?: string } = {},
) {
  await page.goto('/signup')
  if (options.organization) {
    await page.getByRole('radio', { name: /organization/i }).check()
    await page.getByLabel(/organization name/i).fill(options.organization)
  }
  await page.getByLabel(/work email/i).fill(email)
  await page.getByLabel('Password', { exact: true }).fill(PASSWORD)
  await page.getByLabel(/confirm password/i).fill(PASSWORD)
  await page.getByRole('button', { name: 'Sign up' }).click()
  await expect(page).toHaveURL(/\/dashboard/, { timeout: 30_000 })
}

scenario('the landing page is the front door, not the app', async ({ page }) => {
  await page.goto('/')

  await expect(
    page.getByRole('heading', { level: 1, name: /what AI answers say about your brand/i }),
  ).toBeVisible()
  // The regression this guards: `/` used to be the analysis form in the shell.
  await expect(page.getByRole('navigation', { name: /product navigation/i })).toHaveCount(0)
  await expect(page.getByRole('button', { name: /run analysis/i })).toHaveCount(0)
})

scenario('a signed-out visitor cannot reach the product', async ({ page }) => {
  await page.goto('/dashboard')

  await expect(page).toHaveURL(/\/login\?next=/, { timeout: 15_000 })
  await expect(page.getByRole('heading', { name: 'Login' })).toBeVisible()
})

scenario('login returns you to where you were headed', async ({ page }) => {
  const email = unique('next')
  await signUp(page, email)
  await page.getByRole('button', { name: /log out/i }).click()

  await page.goto('/admin')
  await expect(page).toHaveURL(/\/login\?next=%2Fadmin/, { timeout: 15_000 })

  await page.getByLabel(/email/i).fill(email)
  await page.getByLabel(/password/i).fill(PASSWORD)
  await page.getByRole('button', { name: 'Login' }).click()

  await expect(page).toHaveURL(/\/admin/, { timeout: 30_000 })
})

scenario('an individual account signs up, lands, and survives a refresh', async ({ page }) => {
  const email = unique('solo')
  await signUp(page, email)

  await expect(page.getByRole('button', { name: /run analysis/i })).toBeVisible()

  // The session must survive a reload — the classic client-auth bug.
  await page.reload()
  await expect(page).toHaveURL(/\/dashboard/)
  await expect(page.getByRole('button', { name: /log out/i })).toBeVisible({ timeout: 15_000 })
})

scenario('an organization account shows its name and role in the shell', async ({ page }) => {
  const email = unique('org')
  await signUp(page, email, { organization: 'Acme Industries' })

  // Not the email local part — the organization and the role.
  await expect(page.getByText('Acme Industries').first()).toBeVisible({ timeout: 15_000 })
  await expect(page.getByText(/Owner/).first()).toBeVisible()
})

scenario('the admin panel lists members and can change a role', async ({ page }) => {
  const email = unique('admin')
  await signUp(page, email, { organization: 'Admin Co' })

  await page.goto('/admin')
  await expect(page.getByRole('heading', { name: /members/i })).toBeVisible()

  // Scope to the table: the email legitimately also appears in the shell
  // footer and the top bar, so an unscoped locator is ambiguous.
  const row = page.locator('tbody tr', { hasText: email })
  await expect(row).toBeVisible({ timeout: 15_000 })
  await expect(row.getByRole('combobox')).toBeDisabled()
  await expect(row.getByRole('button')).toBeDisabled()

  // And the picker never offers a platform role.
  await expect(page.getByRole('option', { name: /super admin/i })).toHaveCount(0)
})

scenario('the nav advertises nothing that does not exist', async ({ page }) => {
  await signUp(page, unique('nav'))

  // "N/A" was on fifteen entries and is the operator's complaint.
  await expect(page.getByText('N/A')).toHaveCount(0)
  await expect(page.getByRole('link', { name: /site audit/i })).toHaveCount(0) // in flyout only
})

scenario('the shell is usable on a phone', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 })
  await signUp(page, unique('mobile'))

  // The rail must not occupy the viewport; a hamburger opens it instead.
  const hamburger = page.getByRole('button', { name: /open navigation/i })
  await expect(hamburger).toBeVisible()

  await hamburger.click()
  await expect(page.getByRole('navigation', { name: /toolkits/i })).toBeVisible()

  // Escape closes it.
  await page.keyboard.press('Escape')

  // Nothing may overflow the viewport horizontally.
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
  expect(overflow).toBeLessThanOrEqual(1)
})

scenario('the landing page does not overflow on a phone', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 })
  await page.goto('/')

  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
  expect(overflow).toBeLessThanOrEqual(1)
})

scenario('the admin table scrolls itself rather than the page', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 })
  await signUp(page, unique('table'), { organization: 'Table Co' })
  await page.goto('/admin')
  await expect(page.getByRole('heading', { name: /members/i })).toBeVisible()

  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
  expect(overflow).toBeLessThanOrEqual(1)
})

scenario('tablet width keeps the layout intact', async ({ page }) => {
  await page.setViewportSize({ width: 768, height: 1024 })
  await signUp(page, unique('tablet'))

  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
  expect(overflow).toBeLessThanOrEqual(1)
})
