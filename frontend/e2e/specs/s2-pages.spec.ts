import { expect, test } from '@playwright/test';
import { adminFor, expectNoAxeViolations, expectNoHorizontalScroll, signIn } from '../fixtures';

const PAGES = ['kredity/svod', 'kredity/reestr', 'kredity/grafik'];

// S2 «Кредиты»: har sahifa 390/1024/1440 da gorizontal skrollsiz, axe va CSP buzilishlarisiz; skrinshotlar e2e/screens/.
test('S2 sahifalari: Кредиты — skrollsiz, axe va CSP toza', async ({ page }, info) => {
  test.setTimeout(120_000);
  const csp: string[] = [];
  page.on('console', (msg) => {
    if (/Content Security Policy|Refused to/i.test(msg.text())) csp.push(msg.text());
  });
  // oldingi spec shu foydalanuvchi bilan kirgan: TOTP qadami qayta ishlatilmaydi — keyingi 30 s oynani kutamiz.
  await page.waitForTimeout(30_000 - (Date.now() % 30_000) + 500);
  await page.goto('/#kredity/svod');
  await signIn(page, adminFor(info.project.name));
  await expect(page).toHaveURL(/#kredity\/svod$/);
  for (const path of PAGES) {
    await page.evaluate((p) => { window.location.hash = p; }, path);
    await expect(page).toHaveURL(new RegExp(`#${path.replace('/', '\/')}$`));
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Вход в систему' })).toHaveCount(0);
    await expect(page.getByText('Раздел в разработке')).toHaveCount(0);
    await expect(page.getByRole('alert')).toHaveCount(0);
    await page.waitForLoadState('networkidle');
    await page.screenshot({ path: `screens/${info.project.name}-${path.replace('/', '-')}.png`, fullPage: true });
    await expectNoHorizontalScroll(page);
    await expectNoAxeViolations(page);
  }
  expect(csp).toEqual([]);
});
