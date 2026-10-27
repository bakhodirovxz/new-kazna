import { expect, test, type Page } from '@playwright/test';
import { adminFor, expectNoAxeViolations, expectNoHorizontalScroll, signIn } from '../fixtures';

/** TOTP qadami qayta ishlatilmaydi (oldingi spec'lar shu foydalanuvchi bilan kirgan): keyingi 30 s oynani kutamiz. */
async function nextTotpWindow(page: Page): Promise<void> {
  await page.waitForTimeout(30_000 - (Date.now() % 30_000) + 500);
}

function watchCsp(page: Page): string[] {
  const violations: string[] = [];
  page.on('console', (msg) => {
    const text = msg.text();
    if (/Content Security Policy|Refused to/i.test(text)) violations.push(text);
  });
  return violations;
}

/** goto sahifani qayta yuklaydi (sessiya -> login); SPA ichida hash orqali o'tamiz. */
async function open(page: Page, hash: string, heading: string | RegExp): Promise<void> {
  await page.evaluate((h) => { window.location.hash = h; }, hash);
  await expect(page.getByRole('heading', { level: 1, name: heading })).toBeVisible();
  await expect(page.getByRole('alert')).toHaveCount(0);
  await page.waitForLoadState('networkidle');
}

test('Производство: сводка с картой, станции, реализация, головная организация', async ({ page }, info) => {
  test.setTimeout(180_000);
  const csp = watchCsp(page);
  await nextTotpWindow(page);
  await page.goto('/#proizvodstvo/svod');
  await signIn(page, adminFor(info.project.name));
  await expect(page.getByRole('heading', { level: 1, name: 'Производство: сводка' })).toBeVisible();
  await expect(page.getByText('Выработка электроэнергии')).toBeVisible();
  await expect(page.getByRole('img', { name: 'Выработка по месяцам' })).toBeVisible();
  await expect(page.getByRole('group', { name: 'Карта Узбекистана с расположением ГЭС' })).toBeVisible();
  // Dev stack'da ASKUE_LIVE_URL bo'sh: jonli quvvat — «Источник не подключён».
  await expect(page.getByText('Источник данных не подключён: онлайн-мониторинг ГЭС')).toBeVisible();
  await expectNoHorizontalScroll(page);
  await expectNoAxeViolations(page);

  await open(page, 'proizvodstvo/stancii', 'Выработка по станциям');
  if (info.project.name === 'desktop-1440') {
    await expect(page.getByRole('table', { name: 'Станции' }).locator('tbody tr')).toHaveCount(15);
  }
  await expectNoAxeViolations(page);
  await open(page, 'proizvodstvo/realiz', 'Реализация');
  await expect(page.getByRole('img', { name: 'Реализация электроэнергии по месяцам' })).toBeVisible();
  await expectNoHorizontalScroll(page);
  await expectNoAxeViolations(page);

  await page.evaluate(() => { window.location.hash = 'proizvodstvo/svod?br=1'; });
  await expect(page.getByText(/Головная организация не эксплуатирует станции/)).toBeVisible();
  expect(csp).toEqual([]);
});

test('Склад: сводка, остатки, минимальный запас, неликвиды', async ({ page }, info) => {
  test.setTimeout(180_000);
  const csp = watchCsp(page);
  await nextTotpWindow(page);
  await page.goto('/#sklad/svod');
  await signIn(page, adminFor(info.project.name));
  await expect(page.getByRole('heading', { level: 1, name: 'Склад: сводка' })).toBeVisible();
  await expect(page.getByText('Стоимость запасов')).toBeVisible();
  await expect(page.getByRole('img', { name: 'Движение запасов по месяцам' })).toBeVisible();
  await expectNoHorizontalScroll(page);
  await expectNoAxeViolations(page);
  await open(page, 'sklad/ostatki', 'Остатки по складам');
  await expect(page.getByRole('table', { name: 'Склады' })).toBeVisible();
  await expectNoAxeViolations(page);
  await open(page, 'sklad/minimum', 'Минимальный запас');
  await expect(page.getByRole('table', { name: 'Ниже минимального запаса' })).toBeVisible();
  await expectNoAxeViolations(page);
  await open(page, 'sklad/nelikvid', 'Неликвиды');
  await expect(page.getByRole('list', { name: 'Возраст запасов' })).toBeVisible();
  await expectNoHorizontalScroll(page);
  await expectNoAxeViolations(page);
  expect(csp).toEqual([]);
});

test('Экономист филиала видит только свой филиал', async ({ page }, info) => {
  test.skip(info.project.name !== 'desktop-1440', 'bitta kenglik yetarli');
  test.setTimeout(120_000);
  await nextTotpWindow(page);
  await page.goto('/#sklad/ostatki');
  await signIn(page, 'e2e_branch');
  const table = page.getByRole('table', { name: 'Склады' });
  await expect(table).toBeVisible();
  await expect(table.locator('tbody tr')).toHaveCount(1);
  await expect(table.getByText('Каскад Чирчикских ГЭС')).toBeVisible();
  const denied = await page.request.get('/api/v1/proizvodstvo/stancii?br=2');
  expect(denied.status()).toBe(403);
  const own = await page.request.get('/api/v1/sklad/ostatki');
  expect(own.status()).toBe(200);
  const body = (await own.json()) as { branches: Array<{ branch_id: number }> };
  expect(body.branches.map((b) => b.branch_id)).toEqual([3]);
  const stations = (await (await page.request.get('/api/v1/proizvodstvo/stancii')).json()) as { stations: Array<{ branch_id: number }> };
  expect(stations.stations.map((s) => s.branch_id)).toEqual([3]);
});
