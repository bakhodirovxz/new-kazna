import { defineConfig } from '@playwright/test';

/** Haqiqiy dev stack (Caddy + API + DB). Konteyner ichidan: https://caddy (deploy/compose.frontend.yml). */
export default defineConfig({
  testDir: './specs',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list'], ['html', { open: 'never', outputFolder: 'playwright-report' }]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'https://localhost:8443',
    // Faqat dev/test E2E: Caddy `tls internal` (ichki CA) sertifikati.
    ignoreHTTPSErrors: true,
    locale: 'ru-RU',
    timezoneId: 'Asia/Tashkent',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'mobile-390', use: { browserName: 'chromium', viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true } },
    { name: 'tablet-1024', use: { browserName: 'chromium', viewport: { width: 1024, height: 768 } } },
    { name: 'desktop-1440', use: { browserName: 'chromium', viewport: { width: 1440, height: 900 } } },
  ],
});
