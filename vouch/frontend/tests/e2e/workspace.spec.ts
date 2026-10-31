import { expect, test, type Page } from '@playwright/test'
import { mkdir } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const frontendDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..')
const screenshotsDir = path.join(frontendDir, 'test-results', 'screenshots')
const roles = [
  { role: 'recruiter', email: 'recruiter@vouch.demo' },
  { role: 'hiring_manager', email: 'manager@vouch.demo' },
  { role: 'auditor', email: 'auditor@vouch.demo' },
  { role: 'hr_admin', email: 'admin@vouch.demo' },
] as const
const resolutions = [
  { name: '1280x720', width: 1280, height: 720 },
  { name: '1920x1080', width: 1920, height: 1080 },
] as const
const themes = ['dark', 'light'] as const

async function signIn(page: Page, email: string) {
  await page.goto('/')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password').fill('demo1234')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('heading', { name: 'Your hiring. Under control.' })).toBeVisible()
}

async function captureCspErrors(page: Page) {
  await page.addInitScript(() => {
    const violations: string[] = []
    Object.assign(window, { __cspViolations: violations })
    document.addEventListener('securitypolicyviolation', event => {
      violations.push(`${event.violatedDirective}: ${event.blockedURI} at ${event.sourceFile}:${event.lineNumber}`)
    })
  })
  const errors: string[] = []
  page.on('console', message => {
    if (message.type() === 'error' && /content security policy|violates the following/i.test(message.text())) {
      errors.push(message.text())
    }
  })
  return errors
}

for (const { role, email } of roles) {
  test.describe(`${role} workspace`, () => {
    for (const resolution of resolutions) {
      for (const theme of themes) {
        test(`renders ${resolution.name} ${theme} command center`, async ({ page }) => {
          await page.setViewportSize({ width: resolution.width, height: resolution.height })
          const consoleCspErrors = await captureCspErrors(page)
          await signIn(page, email)
          const bundlePath = await page.locator('script[src]').first().getAttribute('src')
          if (bundlePath) {
            const bundle = await page.request.get(new URL(bundlePath, page.url()).toString())
            expect(await bundle.text()).not.toContain('demo1234')
          }
          if (theme === 'light') await page.getByRole('button', { name: 'Switch to light theme' }).click()
          await expect(page.getByRole('navigation', { name: 'Main navigation' })).toBeVisible()
          const adminLink = page.getByRole('link', { name: 'Administration', exact: true })
          if (role === 'hr_admin') await expect(adminLink).toBeVisible()
          else await expect(adminLink).toHaveCount(0)
          await page.screenshot({
            path: path.join(screenshotsDir, `${role}-${resolution.name}-${theme}.png`),
            animations: 'disabled',
          })
          const violations = await page.evaluate(() => (window as Window & { __cspViolations: string[] }).__cspViolations)
          expect(consoleCspErrors, 'CSP console errors').toEqual([])
          expect(violations, 'browser securitypolicyviolation events').toEqual([])
        })
      }
    }

    test('opens case, evidence, ledger, assurance, and role-scoped admin views', async ({ page }) => {
      await signIn(page, email)
      await page.getByRole('link', { name: 'Cases', exact: true }).click()
      await expect(page.getByRole('heading', { name: 'Cases' })).toBeVisible()
      await page.getByRole('link', { name: 'Junior Software Reliability Analyst' }).click()
      await expect(page.getByRole('heading', { name: 'Case analytics' })).toBeVisible()
      await page.getByRole('tab', { name: 'Evidence' }).click()
      await expect(page.getByRole('heading', { name: 'Evidence review' })).toBeVisible()
      await page.getByRole('link', { name: 'Trust Ledger' }).click()
      await expect(page.getByRole('heading', { name: 'Trust ledger' })).toBeVisible()
      const verifyButton = page.getByRole('button', { name: 'Verify chain' })
      if (role === 'auditor' || role === 'hr_admin') await expect(verifyButton).toBeVisible()
      else await expect(verifyButton).toHaveCount(0)
      await page.getByRole('link', { name: 'Assurance' }).click()
      await expect(page.getByRole('heading', { name: 'Assurance' })).toBeVisible()
      if (role === 'auditor' || role === 'hr_admin') {
        await expect(page.getByRole('button', { name: 'Run SENTINEL' })).toBeVisible()
      }
      if (role === 'hr_admin') {
        await page.getByRole('link', { name: 'Administration' }).click()
        await expect(page.getByRole('heading', { name: 'Administration' })).toBeVisible()
      } else {
        await page.goto('/admin')
        await expect(page.getByRole('alert')).toContainText('Only HR administrators')
      }
    })
  })
}

test.beforeAll(async () => {
  await mkdir(screenshotsDir, { recursive: true })
})

test('hides demo account shortcuts when metadata disables demo mode', async ({ page }) => {
  await page.route('**/api/meta', route => route.fulfill({
    json: { model_mode: 'lexicon', n8n_delivery: false, approval_minutes: 15, test_mode: false, demo_mode: false },
  }))
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Demo accounts' })).toHaveCount(0)
  await expect(page.getByText('recruiter@vouch.demo')).toHaveCount(0)
})
