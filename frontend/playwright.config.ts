import { defineConfig, devices } from '@playwright/test';

// Runs against a real API (default http://localhost:8000) and the production build.
export default defineConfig({
  testDir: './e2e',
  timeout: 45_000,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: { baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:4173', trace: 'retain-on-failure' },
  projects: [
    { name: 'desktop', use: { viewport: { width: 1440, height: 900 }, deviceScaleFactor: process.env.SCREENSHOT_VIEWPORT ? 2 : 1 } },
    { name: 'mobile', use: { ...devices['iPhone 14'], defaultBrowserType: 'chromium' } },
  ],
  // Set E2E_BASE_URL to test an already running stack, such as the nginx image.
  webServer: process.env.E2E_BASE_URL ? undefined : { command: 'npm run preview', url: 'http://localhost:4173', reuseExistingServer: !process.env.CI },
});
