import { expect, test } from '@playwright/test';
import { adminFor, expectNoAxeViolations, expectNoHorizontalScroll, signIn } from '../fixtures';

const PAGES = [
  'obzor/svod', 'obzor/postup', 'obzor/rasxod', 'obzor/excel', 'obzor/vnimanie',
  'kazna/svod', 'kazna/platezhi', 'kazna/calendar', 'kazna/dogovory', 'kazna/celevye',
];

// S1: har bir sahifa 390/1024/1440 da gorizontal skrollsiz va axe buzilishlarisiz; skrinshotlar e2e/screens/.
test('S1 sahifalari: skrollsiz va axe toza', async ({ page }, info) => {
  test.setTimeout(240_000);
  // auth-shell-admin shu foydalanuvchi bilan kirgan: TOTP qadami qayta ishlatilmaydi — keyingi 30 s oynani kutamiz.
  await page.waitForTimeout(30_000 - (Date.now() % 30_000) + 500);
  await page.goto('/#kazna/svod');
  await signIn(page, adminFor(info.project.name));
  await expect(page).toHaveURL(/#kazna\/svod$/);
  for (const path of PAGES) {
    // goto sahifani qayta yuklaydi (sessiya → login); SPA ichida hash orqali o'tamiz.
    await page.evaluate((p) => { window.location.hash = p; }, path);
    await expect(page).toHaveURL(new RegExp(`#${path.replace('/', '\\/')}$`));
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Вход в систему' })).toHaveCount(0);
    await expect(page.getByText('Раздел в разработке')).toHaveCount(0);
    await page.waitForLoadState('networkidle');
    await page.screenshot({ path: `screens/${info.project.name}-${path.replace('/', '-')}.png`, fullPage: true });
    console.log(`page ${path}`);
    await expectNoHorizontalScroll(page);
    await expectNoAxeViolations(page);
  }
});
