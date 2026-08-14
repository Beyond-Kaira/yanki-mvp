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

  // 30s, not 15s: the e2e stack runs `next dev`, so the FIRST request for a
  // route pays its compile. The redirect is client-side and cannot happen until
  // the page hydrates, which makes this assertion a hostage to compile time on
  // a loaded runner rather than to anything about the guard.
  await expect(page).toHaveURL(/\/login\?next=/, { timeout: 30_000 })
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

  await page.locator('#product-nav').hover()
  // Not the email local part — the organization and the role.
  await expect(page.getByText('Acme Industries').first()).toBeVisible({ timeout: 15_000 })
  await expect(page.getByText(/Owner/).first()).toBeVisible()
})

scenario('the admin panel lists members and locks your own row', async ({ page }) => {
  const email = unique('admin')
  await signUp(page, email, { organization: 'Admin Co' })

  await page.goto('/admin')
  await expect(page.getByRole('heading', { level: 1, name: 'Admin Panel' })).toBeVisible()
  await expect(page.getByRole('heading', { name: /members/i })).toBeVisible()

  // Scope to the table: the email legitimately also appears in the shell
  // footer and the top bar, so an unscoped locator is ambiguous.
  const row = page.locator('tbody tr', { hasText: email })
  await expect(row).toBeVisible({ timeout: 15_000 })
  await expect(row.getByRole('button', { name: new RegExp(`remove ${email}`, 'i') })).toBeDisabled()

  // And the role filter never offers a platform role.
  await expect(page.getByRole('option', { name: /super admin/i })).toHaveCount(0)
})

scenario('the Admin Panel is one surface with three tabs', async ({ page }) => {
  await signUp(page, unique('tabs'), { organization: 'Tabs Co' })

  await page.goto('/admin')
  const tabs = page.getByRole('navigation', { name: /admin panel sections/i })
  await expect(tabs.getByRole('link', { name: 'Members & roles' })).toBeVisible()
  await expect(tabs.getByRole('link', { name: 'Invitations' })).toBeVisible()
  await expect(tabs.getByRole('link', { name: 'Audit log' })).toBeVisible()

  await tabs.getByRole('link', { name: 'Invitations' }).click()
  await expect(page).toHaveURL(/\/admin\/invitations/)
  // The heading stays "Admin Panel" — the tabs change the section, not the page.
  await expect(page.getByRole('heading', { level: 1, name: 'Admin Panel' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Invitations' })).toBeVisible()

  await tabs.getByRole('link', { name: 'Audit log' }).click()
  await expect(page).toHaveURL(/\/admin\/audit/)
  await expect(page.getByRole('heading', { name: 'Audit log' })).toBeVisible()
})

scenario('inviting a colleague seats them with the invited role', async ({ page }) => {
  const owner = unique('inviter')
  const invitee = unique('invitee')
  await signUp(page, owner, { organization: 'Invite Co' })

  await page.goto('/admin/invitations')
  await page.getByLabel('Email address').fill(invitee)
  await page.getByLabel('Role').selectOption('editor')
  await page.getByRole('button', { name: /send invitation/i }).click()

  // Email is off in the DRY_RUN stack, so the panel says so and shows the link
  // rather than claiming a send that never happened.
  await expect(page.getByText(/email is not configured/i)).toBeVisible({ timeout: 15_000 })
  const link = await page.locator('code').first().innerText()
  expect(link).toContain('/invite/')

  const row = page.locator('tbody tr', { hasText: invitee })
  await expect(row).toBeVisible()
  await expect(row.getByText('Pending')).toBeVisible()

  // Accept it as the invitee, in a clean context so no session leaks across.
  const inviteePage = await page.context().browser()!.newContext()
  const acceptTab = await inviteePage.newPage()
  await acceptTab.goto(new URL(link).pathname)
  await expect(acceptTab.getByRole('heading', { name: /join invite co/i })).toBeVisible({
    timeout: 15_000,
  })
  await acceptTab.getByLabel('Choose a password').fill(PASSWORD)
  await acceptTab.getByLabel('Confirm password').fill(PASSWORD)
  await acceptTab.getByRole('button', { name: /create account and join/i }).click()
  await expect(acceptTab).toHaveURL(/\/dashboard/, { timeout: 30_000 })
  await acceptTab.locator('#product-nav').hover()
  // Seated with the invited role, in the inviter's organization.
  await expect(acceptTab.getByText('Invite Co').first()).toBeVisible({ timeout: 15_000 })
  await expect(acceptTab.getByText(/Editor/).first()).toBeVisible()
  await inviteePage.close()

  // And the owner now sees them as a member with that role.
  await page.goto('/admin')
  const memberRow = page.locator('tbody tr', { hasText: invitee })
  await expect(memberRow).toBeVisible({ timeout: 15_000 })
  await expect(memberRow.getByRole('combobox')).toHaveValue('editor')
})

scenario('a used invitation link cannot be used twice', async ({ page }) => {
  const owner = unique('once')
  const invitee = unique('once-invitee')
  await signUp(page, owner, { organization: 'Once Co' })

  await page.goto('/admin/invitations')
  await page.getByLabel('Email address').fill(invitee)
  await page.getByRole('button', { name: /send invitation/i }).click()
  await expect(page.getByText(/email is not configured/i)).toBeVisible({ timeout: 15_000 })
  const link = new URL(await page.locator('code').first().innerText()).pathname

  const first = await page.context().browser()!.newContext()
  const firstTab = await first.newPage()
  await firstTab.goto(link)
  await firstTab.getByLabel('Choose a password').fill(PASSWORD)
  await firstTab.getByLabel('Confirm password').fill(PASSWORD)
  await firstTab.getByRole('button', { name: /create account and join/i }).click()
  await expect(firstTab).toHaveURL(/\/dashboard/, { timeout: 30_000 })
  await first.close()

  const second = await page.context().browser()!.newContext()
  const secondTab = await second.newPage()
  await secondTab.goto(link)
  await expect(secondTab.getByRole('heading', { name: /can't be used/i })).toBeVisible({
    timeout: 15_000,
  })
  // Matched by text, not by role: Next renders a permanently-empty
  // `role="alert"` route announcer, so `getByRole('alert')` is ambiguous on
  // every page in this app.
  await expect(secondTab.getByText(/already been used/i)).toBeVisible()
  await second.close()
})

scenario('the audit log records what the admin did, with before and after', async ({ page }) => {
  const owner = unique('audit')
  await signUp(page, owner, { organization: 'Audit Co' })

  await page.goto('/admin/audit')
  await expect(page.getByRole('heading', { name: 'Audit log' })).toBeVisible()

  // Signing up is itself an audited event, so the log is never empty here.
  const row = page.locator('tbody tr', { hasText: 'auth:signup' })
  await expect(row).toBeVisible({ timeout: 15_000 })

  await row.getByRole('button', { name: 'Show' }).click()
  // Every event carries the request that produced it.
  await expect(row.getByText(/^Request$/)).toBeVisible()

  // And the integrity sweep reports a clean log.
  await expect(page.getByText(/recent entries verified against their stored hash/i)).toBeVisible()
})

scenario('a member row links to that record\'s own history', async ({ page }) => {
  const owner = unique('history')
  await signUp(page, owner, { organization: 'History Co' })

  await page.goto('/admin')
  const row = page.locator('tbody tr', { hasText: owner })
  await expect(row).toBeVisible({ timeout: 15_000 })
  await row.getByRole('link', { name: owner }).click()

  await expect(page).toHaveURL(/\/admin\/audit\?entity_type=user&entity_id=/)
  await expect(page.getByRole('heading', { name: 'Change history' })).toBeVisible()
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
