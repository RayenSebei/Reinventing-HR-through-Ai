import { defineConfig, devices } from '@playwright/test'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const frontendDir = path.dirname(fileURLToPath(import.meta.url))
const vouchDir = path.resolve(frontendDir, '..')
const port = 8765

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  workers: 2,
  reporter: 'list',
  timeout: 45_000,
  expect: { timeout: 8_000 },
  use: {
    ...devices['Desktop Chrome'],
    baseURL: `http://127.0.0.1:${port}`,
    trace: 'retain-on-failure',
    launchOptions: {
      executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH || undefined,
      args: ['--disable-dev-shm-usage'],
    },
  },
  webServer: {
    command: `python -m app --seed --yes --host 127.0.0.1 --port ${port}`,
    cwd: vouchDir,
    url: `http://127.0.0.1:${port}/api/meta`,
    reuseExistingServer: false,
    timeout: 180_000,
    env: {
      VOUCH_DATA_DIR: path.join(frontendDir, 'test-results', 'playwright-data'),
      VOUCH_DEMO_MODE: '1',
      VOUCH_MODEL: 'lexicon',
      VOUCH_JWT_SECRET: 'playwright-test-jwt-secret-not-for-production',
      VOUCH_LEDGER_KEY: 'playwright-test-ledger-key-not-for-production',
    },
  },
})
