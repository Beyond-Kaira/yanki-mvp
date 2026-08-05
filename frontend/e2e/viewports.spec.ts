import { test, expect, type Page } from '@playwright/test'

const baseURL = process.env.E2E_BASE_URL
const scenario = baseURL ? test : test.skip
const PASSWORD = 'correct-horse-battery'

async function signUp(page: Page) {
  const email = `vp-${Date.now()}-${Math.floor(Math.random() * 1e5)}@e2e.example`
  await page.goto('/signup')
  await page.getByLabel(/work email/i).fill(email)
  await page.getByLabel('Password', { exact: true }).fill(PASSWORD)
  await page.getByLabel(/confirm password/i).fill(PASSWORD)
  await page.getByRole('button', { name: 'Sign up' }).click()
  await expect(page).toHaveURL(/\/dashboard/, { timeout: 30_000 })
}

const SIZES = [
  { name: 'mobile-small', width: 320, height: 640 },
  { name: 'mobile', width: 375, height: 812 },
  { name: 'mobile-large', width: 414, height: 896 },
  { name: 'tablet', width: 768, height: 1024 },
  { name: 'tablet-landscape', width: 1024, height: 768 },
  { name: 'desktop', width: 1440, height: 900 },
]

const PUBLIC_PAGES = ['/', '/login', '/signup', '/checker', '/methodology']
const PRIVATE_PAGES = [
  '/dashboard',
  '/admin',
  '/admin/invitations',
  '/admin/audit',
  '/settings',
  '/site-audit',
]

async function horizontalOverflow(page: Page): Promise<number> {
  return page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
}

for (const size of SIZES) {
  scenario(`public pages do not overflow at ${size.name} (${size.width}px)`, async ({ page }) => {
    await page.setViewportSize({ width: size.width, height: size.height })
    for (const path of PUBLIC_PAGES) {
      await page.goto(path)
      await page.waitForLoadState('networkidle')
      expect(await horizontalOverflow(page), `${path} at ${size.width}px`).toBeLessThanOrEqual(1)
    }
  })

  scenario(`signed-in pages do not overflow at ${size.name} (${size.width}px)`, async ({ page }) => {
    await page.setViewportSize({ width: size.width, height: size.height })
    await signUp(page)
    for (const path of PRIVATE_PAGES) {
      await page.goto(path)
      await page.waitForLoadState('networkidle')
      expect(await horizontalOverflow(page), `${path} at ${size.width}px`).toBeLessThanOrEqual(1)
    }
  })
}

scenario('the nav rail is hidden on mobile and present on desktop', async ({ page }) => {
  await signUp(page)
  const nav = page.getByRole('navigation', { name: /toolkits/i })

  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/dashboard')
  await expect(nav).toBeVisible()
  await expect(page.getByRole('button', { name: /open navigation/i })).toBeHidden()

  await page.setViewportSize({ width: 375, height: 812 })
  await page.goto('/dashboard')
  await expect(page.getByRole('button', { name: /open navigation/i })).toBeVisible()
})

scenario('primary controls meet the 44px touch target', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 })
  await signUp(page)
  await page.goto('/admin')
  await page.getByRole('heading', { name: /members/i }).waitFor()

  const hamburger = page.getByRole('button', { name: /open navigation/i })
  const box = await hamburger.boundingBox()
  expect(box!.height).toBeGreaterThanOrEqual(44)
  expect(box!.width).toBeGreaterThanOrEqual(44)
})

scenario('forms stay usable on the smallest phone', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 640 })
  await page.goto('/signup')

  for (const label of [/work email/i]) {
    const input = page.getByLabel(label)
    const box = await input.boundingBox()
    expect(box!.width).toBeLessThanOrEqual(320)
    expect(box!.height).toBeGreaterThanOrEqual(36)
  }
  // The account-type radios must not be clipped either.
  await expect(page.getByRole('radio', { name: /organization/i })).toBeVisible()
})
