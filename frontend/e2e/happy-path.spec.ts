import { test, expect } from '@playwright/test'

// Runs only when E2E_BASE_URL points at a live stack (DRY_RUN backend + web).
// Skipped otherwise so CI and local `npm test` stay green with no services up.
const baseURL = process.env.E2E_BASE_URL
const scenario = baseURL ? test : test.skip

// The analysis form moved behind auth when `/` became a landing page, so the
// happy path now starts where a real user starts: at the front door. This
// exercises strictly more than it used to — landing, sign-up, the post-auth
// redirect, the product shell, and then the pipeline — rather than a form that
// happened to sit on the root page.
scenario('signs up, submits a URL, and renders a GEO score', async ({ page }) => {
  const email = `happy-${Date.now()}@e2e.example`
  const password = 'correct-horse-battery'

  await page.goto('/')
  await page
    .getByRole('link', { name: /create an account/i })
    .first()
    .click()

  await page.getByLabel(/work email/i).fill(email)
  await page.getByLabel('Password', { exact: true }).fill(password)
  await page.getByLabel(/confirm password/i).fill(password)
  await page.getByRole('button', { name: 'Sign up' }).click()

  await expect(page).toHaveURL(/\/dashboard/, { timeout: 30_000 })

  await page.getByLabel(/url/i).fill('https://example.com')
  await page.getByRole('button', { name: /run analysis/i }).click()

  // The pipeline runs the six steps; give it a generous window.
  const gauge = page.getByRole('img', { name: /GEO score/i })
  await expect(gauge).toBeVisible({ timeout: 180_000 })

  // A percentage is rendered on the results screen.
  await expect(page.getByText(/%/).first()).toBeVisible()
})
