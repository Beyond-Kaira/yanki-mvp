import { test, expect, type Page } from '@playwright/test'
import type { AnalysisSummary } from '../lib/contracts'

// Uses the real frontend with intercepted API fixtures; no paid analysis or
// database mutation is needed to exercise the live history lifecycle.
const scenario = process.env.E2E_BASE_URL ? test : test.skip
const finished: AnalysisSummary = {
  id: 'finished', url: 'https://finished.example/', status: 'done', progress: 100,
  current_step: null, geo_score: 61.5, error: null,
  created_at: new Date(Date.now() - 600_000).toISOString(), updated_at: new Date(Date.now() - 300_000).toISOString(),
}
const active: AnalysisSummary = {
  ...finished, id: 'active', url: 'https://acme.example/', status: 'running', progress: 45,
  current_step: 'execute', geo_score: null, created_at: new Date(Date.now() - 134_000).toISOString(), updated_at: new Date().toISOString(),
}

async function mockApi(page: Page, initialRows = [finished], omitNewRun = false) {
  let rows = initialRows
  let details = new Map(initialRows.map(row => [row.id, row]))
  let detailRequests = 0
  let listRequests = 0
  await page.route('**/api/**', async route => {
    const request = route.request()
    const url = new URL(request.url())
    let body: unknown
    if (url.pathname === '/api/v1/auth/refresh') body = { access_token: 'preview-token' }
    else if (url.pathname === '/api/v1/auth/me') body = {
      id: 'preview-user', email: 'preview@example.com', is_active: true,
      organization: { id: 'preview-org', name: 'Preview workspace' },
      organizations: [{ id: 'preview-org', name: 'Preview workspace', role: 'owner' }], role: 'owner', permissions: [],
    }
    else if (url.pathname === '/api/v1/analyses' && request.method() === 'POST') {
      details.set(active.id, active)
      if (!omitNewRun) rows = [active, ...rows]
      body = { id: active.id }
    }
    else if (url.pathname === '/api/v1/analyses') {
      listRequests += 1
      const status = url.searchParams.get('status')
      const filtered = status ? rows.filter(row => row.status === status) : rows
      body = { analyses: filtered.slice(0, Number(url.searchParams.get('limit') ?? 20)), total: filtered.length,
        user_analyses_used: rows.filter(row => row.status !== 'failed').length, user_analyses_limit: 5, limit: 5, offset: 0 }
    }
    else if (url.pathname.startsWith('/api/v1/analyses/')) {
      detailRequests += 1
      body = details.get(decodeURIComponent(url.pathname.split('/').at(-1)!))
      if (!body) return route.fulfill({ status: 404, json: { detail: 'Analysis not found.' } })
    }
    else return route.fulfill({ status: 404, json: { detail: 'No preview fixture for this endpoint.' } })
    return route.fulfill({ json: body })
  })
  return {
    setRows: (next: AnalysisSummary[]) => { rows = next; details = new Map(next.map(row => [row.id, row])) },
    setListRows: (next: AnalysisSummary[]) => { rows = next },
    setDetails: (row: AnalysisSummary) => { details.set(row.id, row) },
    requests: () => listRequests,
    detailRequests: () => detailRequests,
  }
}

scenario('starting an analysis keeps the default page and full-width history until completion', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1440, height: 1100 })
  const api = await mockApi(page)
  await page.goto('/ai-visibility')
  const history = page.getByRole('region', { name: 'Your analyses' })
  await expect(history.getByRole('link', { name: /finished\.example/ })).toBeVisible()
  const originalWidth = (await history.boundingBox())!.width
  expect(originalWidth).toBeGreaterThan(1000)
  await page.getByRole('textbox', { name: /url/i }).fill(active.url)
  await page.getByRole('button', { name: 'Run analysis', exact: true }).click()
  const card = history.getByRole('article', { name: 'Analysis for acme.example' })
  await expect(card).toBeVisible()
  await expect(page).toHaveURL(/\/ai-visibility$/)
  await expect(page.getByRole('button', { name: 'Run analysis', exact: true })).toBeEnabled()
  await expect(page.getByRole('textbox', { name: /url/i })).toHaveValue(active.url)
  await expect(history.getByRole('link', { name: /finished\.example/ })).toBeVisible()
  expect((await history.boundingBox())!.width).toBe(originalWidth)
  await expect(card.getByRole('list', { name: 'Analysis steps' }).getByRole('listitem')).toHaveCount(6)
  await card.getByRole('button', { name: /collapse analysis steps/i }).click()
  await expect(card.getByRole('list', { name: 'Analysis steps' })).toBeHidden()
  await card.getByRole('button', { name: /show analysis steps/i }).click()
  await page.screenshot({ path: testInfo.outputPath('analysis-running-desktop.png'), fullPage: true })
  api.setRows([{ ...active, status: 'done', progress: 100, current_step: null, geo_score: 72 }, finished])
  await expect(history.getByRole('link', { name: /acme\.example.*done/ })).toBeVisible()
  await expect(card).toHaveCount(0)
  await expect(page).toHaveURL(/\/ai-visibility$/)
  await expect(page.getByRole('button', { name: 'Run analysis', exact: true })).toBeVisible()
  const requests = api.requests()
  await page.waitForTimeout(2300)
  expect(api.requests()).toBe(requests)
})

scenario('all start surfaces keep live and completed analyses usable on small screens', async ({ page }, testInfo) => {
  await mockApi(page, [active, finished])
  for (const width of [320, 375, 768]) {
    await page.setViewportSize({ width, height: 1100 })
    for (const path of ['/dashboard', '/ai-visibility', '/search-visibility']) {
      await page.goto(path)
      const card = page.getByRole('article', { name: 'Analysis for acme.example' })
      await expect(card).toBeVisible()
      await expect(card.getByRole('list', { name: 'Analysis steps' }).getByRole('listitem')).toHaveCount(6)
      await expect(page.getByRole('button', { name: 'Run analysis', exact: true })).toBeVisible()
      await expect(page.getByRole('link', { name: /finished\.example/ })).toBeVisible()
      expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1)
      expect(await card.evaluate(element => element.scrollWidth - element.clientWidth)).toBeLessThanOrEqual(1)
      if (width === 375 && path === '/ai-visibility') await page.screenshot({ path: testInfo.outputPath('analysis-running-mobile.png'), fullPage: true })
    }
  }
})

scenario('full history updates live progress beside completed rows', async ({ page }) => {
  const api = await mockApi(page, [active, finished])
  await page.goto('/analyses')
  const table = page.getByRole('table', { name: 'Your analyses, newest first' })
  await expect(table.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '45')
  await expect(table.getByRole('link', { name: 'finished.example' })).toBeVisible()
  api.setRows([{ ...active, status: 'done', progress: 100, current_step: null, geo_score: 72 }, finished])
  await expect(table.getByRole('link', { name: 'acme.example' })).toBeVisible()
  await expect(table.getByRole('progressbar')).toHaveCount(0)
})

scenario('a submitted run survives omitted list rows, reloads and completes via its own ID', async ({ page }) => {
  const api = await mockApi(page, [finished], true)
  await page.goto('/ai-visibility')
  await page.getByRole('textbox', { name: /url/i }).fill(active.url)
  await page.getByRole('button', { name: 'Run analysis', exact: true }).click()
  const card = page.getByRole('article', { name: 'Analysis for acme.example' })
  await expect(card.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '45')
  await card.getByRole('button', { name: /collapse analysis steps/i }).click()
  api.setDetails({ ...active, progress: 80, current_step: 'footprint' })
  await expect(card.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '80')
  await expect(card.getByRole('button', { name: /show analysis steps/i })).toHaveAttribute('aria-expanded', 'false')
  await expect(page.getByRole('link', { name: /finished\.example/ })).toBeVisible()
  expect(api.detailRequests()).toBeGreaterThan(1)
  await page.reload()
  await expect(card.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '80')
  api.setDetails({ ...active, status: 'done', progress: 100, current_step: null, geo_score: 72 })
  await expect(page.getByRole('link', { name: /acme\.example.*done/ })).toBeVisible()
  const reads = api.detailRequests()
  await page.waitForTimeout(2300)
  expect(api.detailRequests()).toBe(reads)
})

scenario('details animate through intermediate heights, reverse smoothly and respect reduced motion', async ({ page }) => {
  const api = await mockApi(page, [active, finished])
  await page.emulateMedia({ reducedMotion: 'no-preference' })
  for (const width of [1440, 375]) {
    await page.setViewportSize({ width, height: 1100 })
    await page.goto('/ai-visibility')
    const card = page.getByRole('article', { name: 'Analysis for acme.example' })
    await expect(card).toBeVisible()
    const sample = async (reverse = false) => card.evaluate(async (element, reverse) => {
      const toggle = element.querySelector('button')!
      const heights = [element.getBoundingClientRect().height]
      toggle.click()
      let start: number | undefined
      let reversed = false
      await new Promise<void>(resolve => {
        function tick(time: number) {
          start ??= time
          heights.push(element.getBoundingClientRect().height)
          if (reverse && !reversed && time - start >= 70) { toggle.click(); reversed = true }
          if (time - start < 400) requestAnimationFrame(tick)
          else resolve()
        }
        requestAnimationFrame(tick)
      })
      return heights
    }, reverse)
    const closing = await sample()
    const max = closing[0], min = closing.at(-1)!
    expect(max - min).toBeGreaterThan(50)
    expect(closing.filter(height => height > min + 2 && height < max - 2).length).toBeGreaterThan(2)
    const opening = await sample()
    expect(opening.filter(height => height > min + 2 && height < max - 2).length).toBeGreaterThan(2)
    expect(Math.abs(opening.at(-1)! - max)).toBeLessThan(1)
    const reversed = await sample(true)
    expect(Math.min(...reversed)).toBeLessThan(max - 5)
    expect(Math.abs(reversed.at(-1)! - max)).toBeLessThan(1)
    await expect(card.getByRole('button')).toHaveAttribute('aria-expanded', 'true')
    api.setListRows([finished])
    await expect.poll(() => api.detailRequests()).toBeGreaterThan(0)
    await expect(card).toBeVisible()
    api.setListRows([active, finished])
  }
  await page.emulateMedia({ reducedMotion: 'reduce' })
  const card = page.getByRole('article', { name: 'Analysis for acme.example' })
  const duration = await card.getByRole('list', { name: 'Analysis steps' }).evaluate(element => getComputedStyle(element.parentElement!.parentElement!.parentElement!).transitionDuration)
  expect(duration).toBe('0s')
  await card.getByRole('button', { name: /collapse analysis steps/i }).click()
  await expect(card.getByRole('list', { name: 'Analysis steps' })).toBeHidden()
})

scenario('the history heading and View all stay anchored while details expand downwards', async ({ page }) => {
  await mockApi(page, [active, finished, { ...finished, id: 'older', url: 'https://older.example/' }])
  await page.emulateMedia({ reducedMotion: 'no-preference' })
  for (const width of [1440, 375]) {
    await page.setViewportSize({ width, height: 740 })
    await page.goto('/ai-visibility')
    const card = page.getByRole('article', { name: 'Analysis for acme.example' })
    await expect(card).toBeVisible()
    await page.locator('main').evaluate(element => { element.scrollTop = element.scrollHeight })
    const capture = () => page.evaluate(() => {
      const heading = document.getElementById('recent-analyses-heading')!
      const section = heading.closest('section')!
      const link = section.querySelector('a')!
      const toggle = section.querySelector('article button')!
      const main = section.closest('main')!
      return { heading: heading.getBoundingClientRect().top, link: link.getBoundingClientRect().top, toggle: toggle.getBoundingClientRect().top,
        scrollTop: main.scrollTop, maxScroll: main.scrollHeight - main.clientHeight }
    })
    const initialExpanded = await capture()
    await card.getByRole('button').click()
    await expect(card.getByRole('button')).toHaveAttribute('aria-expanded', 'false')
    await page.waitForTimeout(70)
    const duringCollapse = await capture()
    expect(Math.abs(duringCollapse.heading - initialExpanded.heading)).toBeLessThan(1)
    expect(Math.abs(duringCollapse.link - initialExpanded.link)).toBeLessThan(1)
    await page.waitForTimeout(200)
    const before = await capture()
    expect(Math.abs(before.heading - initialExpanded.heading)).toBeLessThan(1)
    expect(Math.abs(before.link - initialExpanded.link)).toBeLessThan(1)
    expect(Math.abs(before.toggle - initialExpanded.toggle)).toBeLessThan(1)
    const target = await card.getByRole('button').boundingBox()
    await page.mouse.click(target!.x + target!.width / 2, target!.y + target!.height / 2)
    await page.waitForTimeout(250)
    const after = await capture()
    expect(Math.abs(after.heading - before.heading)).toBeLessThan(1)
    expect(Math.abs(after.link - before.link)).toBeLessThan(1)
    expect(Math.abs(after.toggle - before.toggle)).toBeLessThan(1)
    await card.getByRole('button').click()
    await page.waitForTimeout(250)
    const collapsed = await capture()
    expect(Math.abs(collapsed.heading - before.heading)).toBeLessThan(1)
    expect(Math.abs(collapsed.link - before.link)).toBeLessThan(1)
    await page.locator('main').evaluate(element => { element.scrollTop = 0 })
    await expect.poll(() => page.getByRole('region', { name: 'Your analyses' }).evaluate(element => (element as HTMLElement).style.minHeight)).toBe('')
  }
})

scenario('a failed fifth run stays visible after reload, frees quota and keeps the start form in place', async ({ page }, testInfo) => {
  const previous = Array.from({ length: 4 }, (_, index) => ({ ...finished, id: `finished-${index}`, url: `https://finished-${index}.example/` }))
  const api = await mockApi(page, previous)
  await page.setViewportSize({ width: 1440, height: 950 })
  await page.goto('/ai-visibility')
  const heading = page.getByRole('heading', { name: 'Your analyses', exact: true })
  await expect(page.getByText('4 / 5', { exact: true })).toBeVisible()
  const initialHeading = (await heading.boundingBox())!.y
  const url = page.getByRole('textbox', { name: /url/i })
  await url.fill(active.url)
  await page.getByRole('button', { name: 'Run analysis', exact: true }).click()
  const card = page.getByRole('article', { name: 'Analysis for acme.example' })
  await expect(card.getByRole('progressbar')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Run analysis', exact: true })).toBeDisabled()
  await expect(url).toHaveValue(active.url)
  expect((await heading.boundingBox())!.y).toBe(initialHeading)
  const failed = { ...active, status: 'failed' as const, progress: 0, current_step: 'discovery' as const, error: 'could not read the site' }
  api.setRows([failed, ...previous])
  await expect(card.getByRole('alert')).toHaveText('could not read the site')
  await expect(page.getByRole('button', { name: 'Run analysis', exact: true })).toBeEnabled()
  await expect(page.getByText('4 / 5', { exact: true })).toBeVisible()
  expect((await heading.boundingBox())!.y).toBe(initialHeading)
  await page.reload()
  await expect(card.getByRole('alert')).toHaveText('could not read the site')
  await expect(page.getByRole('button', { name: 'Run analysis', exact: true })).toBeEnabled()
  await page.screenshot({ path: testInfo.outputPath('analysis-failure-retained.png'), fullPage: true })
})

scenario('history headings stay in position through delayed quota, history and fonts', async ({ page }) => {
  const rows = Array.from({ length: 5 }, (_, index) => ({ ...finished, id: `finished-${index}`, url: `https://finished-${index}.example/` }))
  await mockApi(page, rows)
  for (const width of [1512, 375, 320]) {
    await page.setViewportSize({ width, height: 740 })
    for (const path of ['/dashboard', '/ai-visibility', '/search-visibility']) {
      let releaseData!: () => void
      let releaseFonts!: () => void
      const dataReady = new Promise<void>(resolve => { releaseData = resolve })
      const fontsReady = new Promise<void>(resolve => { releaseFonts = resolve })
      await page.route('**/*.woff2', async route => { await fontsReady; await route.continue() })
      await page.route('**/api/v1/analyses?**', async route => { await dataReady; await route.fallback() })
      await page.goto(path, { waitUntil: 'domcontentloaded' })
      await expect(page.getByRole('heading', { name: 'Your analyses', exact: true })).toBeVisible()
      const capture = () => page.evaluate(() => {
        const heading = document.getElementById('recent-analyses-heading')!
        const link = heading.closest('section')!.querySelector('a')!
        const position = (element: Element) => {
          const range = document.createRange()
          range.selectNodeContents(element)
          return { boxY: element.getBoundingClientRect().y, textY: range.getBoundingClientRect().y }
        }
        return { heading: position(heading), link: position(link) }
      })
      const initial = await capture()
      releaseData()
      await expect(page.getByRole('link', { name: /finished-0\.example/ })).toBeVisible()
      const withData = await capture()
      releaseFonts()
      await page.evaluate(async () => { await document.fonts.ready })
      const loaded = await capture()
      for (const state of [withData, loaded]) {
        for (const element of ['heading', 'link'] as const) {
          expect(Math.abs(state[element].boxY - initial[element].boxY), `${path}, ${width}px: ${element} box`).toBeLessThan(1)
          expect(Math.abs(state[element].textY - initial[element].textY), `${path}, ${width}px: ${element} text`).toBeLessThan(1)
        }
      }
      await page.unroute('**/*.woff2')
      await page.unroute('**/api/v1/analyses?**')
    }
  }
})
