import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';

const admin = { email: process.env.E2E_ADMIN_EMAIL ?? '', password: process.env.E2E_ADMIN_PASSWORD ?? '' };
const viewer = { email: process.env.E2E_VIEWER_EMAIL ?? '', password: process.env.E2E_VIEWER_PASSWORD ?? '' };
const API = process.env.E2E_API_URL ?? 'http://localhost:8000';

const ROUTES: [string, RegExp][] = [
  ['/', /on track to cost/],
  ['/infrastructure', /^Infrastructure$/],
  ['/infrastructure/rds-orders-primary', /^rds-orders-primary$/],
  ['/costs', /^Costs$/],
  ['/forecasts', /^Forecasts$/],
  ['/kubernetes', /^Kubernetes$/],
  ['/map', /^Service map$/],
  ['/alerts', /^Alerts$/],
  ['/advisor', /^Cloud Advisor$/],
  ['/reports', /^Reports$/],
  ['/system', /^System$/],
];

async function signIn(page: Page, who: { email: string; password: string }) {
  await page.goto('/login');
  await page.getByLabel('Email').fill(who.email);
  await page.getByLabel('Password').fill(who.password);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('heading', { level: 1, name: /on track to cost/ })).toBeVisible();
}

async function apiGet<T>(path: string, who = admin): Promise<T> {
  const login = await fetch(`${API}/api/v1/auth/login`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(who) });
  const { access_token } = (await login.json()) as { access_token: string };
  return (await fetch(`${API}/api/v1${path}`, { headers: { Authorization: `Bearer ${access_token}` } })).json() as T;
}

function watch(page: Page) {
  const problems: string[] = [];
  page.on('pageerror', (e) => problems.push(`pageerror: ${e.message}`));
  page.on('console', (m) => { if (m.type() === 'error') problems.push(`console: ${m.text()}`); });
  page.on('response', (r) => { if (r.url().includes('/api/') && r.status() >= 400) problems.push(`${r.status()} ${r.url()}`); });
  return problems;
}

test('the demo button signs in as a read-only viewer', async ({ page }) => {
  test.skip(!process.env.E2E_DEMO, 'Needs DEMO_LOGIN_ENABLED on the API');
  await page.goto('/login');
  await page.getByRole('button', { name: 'View the demo' }).click();
  await expect(page.getByRole('heading', { level: 1, name: /on track to cost/ })).toBeVisible();
  await page.goto('/alerts');
  await expect(page.getByText(/Your viewer role can read alerts/)).toBeVisible();
});

test('redirects to sign-in and rejects a wrong password', async ({ page }) => {
  await page.goto('/costs');
  await expect(page).toHaveURL(/login/);
  await page.getByLabel('Email').fill(viewer.email);
  await page.getByLabel('Password').fill('wrong-password-123');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('alert')).toContainText('do not match');
});

for (const theme of ['light', 'dark']) {
  test(`every page renders from the API in ${theme} theme, without errors or sideways scroll`, async ({ page }) => {
    await page.addInitScript((t) => localStorage.setItem('cloudpulse.theme', t), theme);
    const problems = watch(page);
    await signIn(page, admin);
    for (const [path, heading] of ROUTES) {
      await page.goto(path);
      await expect(page.getByRole('heading', { level: 1, name: heading })).toBeVisible();
      await expect(page.getByRole('status').filter({ hasText: 'Loading' })).toHaveCount(0);
      await expect(page.getByRole('alert')).toHaveCount(0);
      await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(overflow, `${path} scrolls sideways`).toBeLessThanOrEqual(0);
      const axe = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']).analyze();
      expect(axe.violations.map((v) => `${v.id}: ${v.nodes[0].html}`), `${path} accessibility`).toEqual([]);
      if (process.env.SCREENSHOT_DIR) {
        const name = path === '/' ? 'overview' : path.slice(1).replace('/', '-');
        await page.screenshot({ path: `${process.env.SCREENSHOT_DIR}/${test.info().project.name}-${theme}-${name}.png`, fullPage: !process.env.SCREENSHOT_VIEWPORT });
      }
    }
    expect(problems).toEqual([]);
  });
}

test('the theme toggle switches and persists', async ({ page }) => {
  await page.addInitScript(() => { if (!sessionStorage.getItem('seeded')) { localStorage.setItem('cloudpulse.theme', 'light'); sessionStorage.setItem('seeded', '1'); } });
  await signIn(page, admin);
  if (test.info().project.name === 'mobile') await page.getByRole('button', { name: 'Open menu' }).click();
  await page.getByRole('button', { name: 'Switch to dark theme' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
});

test('the overview shows the figures the API returns and labels them simulated', async ({ page }) => {
  await signIn(page, admin);
  const d = await apiGet<{ costs: { last_30d_usd: number; month_end_estimate_usd: number }; health: { health_score: number } }>('/dashboard/executive');
  const usd = (n: number) => n.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });
  await expect(page.getByRole('heading', { level: 1 })).toContainText(usd(d.costs.month_end_estimate_usd));
  await expect(page.getByText(usd(d.costs.last_30d_usd), { exact: true })).toBeVisible();
  await expect(page.getByText(d.health.health_score.toFixed(1), { exact: true })).toBeVisible();
  await expect(page.getByText('Simulated data').first()).toBeVisible();
});

test('live readings poll the API', async ({ page }) => {
  await signIn(page, admin);
  await page.goto('/infrastructure');
  await expect(page.getByText(/Simulated live readings, updated/)).toBeVisible();
  const next = page.waitForResponse((r) => r.url().includes('/infrastructure/live'), { timeout: 20_000 });
  expect((await next).status()).toBe(200);
});

test('the map traces dependencies and shows details', async ({ page }) => {
  await signIn(page, admin);
  await page.goto('/map');
  await page.locator('[data-node="rds-orders-primary"]').click();
  await expect(page.getByText('Called by')).toBeVisible();
  await expect(page.getByRole('link', { name: 'Open metrics' })).toHaveAttribute('href', '/infrastructure/rds-orders-primary');
});

test('the advisor answers and states its mode', async ({ page }) => {
  await signIn(page, admin);
  await page.goto('/advisor');
  await page.getByLabel('Ask a question').fill('Where can I save the most?');
  await page.getByRole('button', { name: 'Ask', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Where can I save the most?' })).toBeVisible();
  await expect(page.getByText('Rule-based fallback').first()).toBeVisible();
});

test('the report downloads as a PDF', async ({ page }) => {
  await signIn(page, admin);
  await page.goto('/reports');
  const [download] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'Download PDF' }).click()]);
  expect(readFileSync(await download.path()).subarray(0, 4).toString()).toBe('%PDF');
  await expect(page.getByText(/^Downloaded cloudpulse-executive-report/)).toBeVisible();
});

test('an engineer-level user can acknowledge an alert and history updates', async ({ page }) => {
  await signIn(page, admin);
  await page.goto('/alerts');
  await page.getByRole('button', { name: 'Run rules now' }).click();
  await expect(page.getByText('Alert rules ran')).toBeVisible();
  const before = await apiGet<{ total: number }>('/alerts?status=acknowledged');
  await page.getByRole('button', { name: 'Acknowledge' }).first().click();
  await expect(page.getByText(/: acknowledged\.$/)).toBeVisible();
  await expect.poll(async () => (await apiGet<{ total: number }>('/alerts?status=acknowledged')).total).toBe(before.total + 1);
});

test('a viewer cannot see alert actions or user administration', async ({ page }) => {
  await signIn(page, viewer);
  await page.goto('/alerts');
  await expect(page.getByText(/Your viewer role can read alerts/)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Run rules now' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Acknowledge' })).toHaveCount(0);
  await page.goto('/system');
  await expect(page.getByRole('heading', { name: 'Platform' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Users' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Reset simulation' })).toHaveCount(0);
});

test('an admin password that breaks the rules is caught before sending', async ({ page }) => {
  await signIn(page, admin);
  await page.goto('/system');
  await page.getByLabel('Full name').fill('Test User');
  await page.getByLabel('Email').fill('new@cloudpulse.test');
  await page.getByLabel('Password').fill('short');
  await page.getByRole('button', { name: 'Add user' }).click();
  await expect(page.getByRole('alert')).toContainText('at least 12');
});

test('an expired session returns to sign-in with an explanation', async ({ page }) => {
  await signIn(page, admin);
  await page.evaluate(() => sessionStorage.setItem('cloudpulse.token', 'not-a-valid-token'));
  await page.goto('/costs');
  await expect(page).toHaveURL(/login/);
  await expect(page.getByText('Your session expired')).toBeVisible();
});

test('a failed request shows what happened and offers a retry', async ({ page }) => {
  await signIn(page, admin);
  await page.route('**/api/v1/finops/recommendations', (r) => r.fulfill({ status: 500, json: { error: { code: 'internal_error', message: 'An unexpected error occurred' } } }));
  await page.goto('/costs');
  await expect(page.getByText('This data could not be loaded.')).toBeVisible({ timeout: 15_000 });
  await expect(page.getByRole('button', { name: 'Try again' })).toBeVisible();
});
