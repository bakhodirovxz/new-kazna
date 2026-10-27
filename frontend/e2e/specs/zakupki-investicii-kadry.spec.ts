import { expect, test, type Page } from '@playwright/test';
import { adminFor, expectNoAxeViolations, expectNoHorizontalScroll, signIn } from '../fixtures';

const PERSONAL = /^(.*_)?(fio|full_?name|first_?name|last_?name|middle_?name|surname|pinfl|passport|phone|email)(_.*)?$/i;

function watchCsp(page: Page): string[] {
  const violations: string[] = [];
  page.on('console', (msg) => {
    const text = msg.text();
    if (/Content Security Policy|Refused to/i.test(text)) violations.push(text);
  });
  return violations;
}

/** Bir foydalanuvchining TOTP qadami ikki marta ishlatilmaydi: keyingi 30 s oynani kutib kiramiz (s1-pages.spec.ts kabi). */
async function login(page: Page, username: string, hash: string): Promise<void> {
  await page.waitForTimeout(30_000 - (Date.now() % 30_000) + 500);
  await page.goto(`/${hash}`);
  await signIn(page, username);
  await expect(page).toHaveURL(new RegExp(`${hash.replace(/[/?]/g, '\$&')}$`));
}

/** goto sahifani qayta yuklaydi (sessiya → login); SPA ichida location.hash orqali o'tamiz. */
async function open(page: Page, path: string, heading: string | RegExp): Promise<void> {
  await page.evaluate((p) => { window.location.hash = p; }, path);
  await expect(page.getByRole('heading', { level: 1, name: heading })).toBeVisible();
  await expect(page.getByRole('alert')).toHaveCount(0);
}

function keys(value: unknown): string[] {
  if (Array.isArray(value)) return value.flatMap(keys);
  if (value && typeof value === 'object') return Object.entries(value).flatMap(([k, v]) => [k, ...keys(v)]);
  return [];
}

test('Закупки: сводка, лоты с фильтром, поставщики, экономия', async ({ page }, info) => {
  test.setTimeout(120_000);
  const csp = watchCsp(page);
  await login(page, adminFor(info.project.name), '#zakupki/svod');
  await expect(page.getByRole('heading', { level: 1, name: 'Закупки: сводка' })).toBeVisible();
  await expect(page.getByText('Заключено договоров')).toBeVisible();
  await expect(page.getByRole('img', { name: 'Заключённые договоры по месяцам' })).toBeVisible();
  await expectNoHorizontalScroll(page);
  await expectNoAxeViolations(page);

  await open(page, 'zakupki/loty?per=ytd', 'Лоты');
  await page.getByRole('button', { name: 'Просроченные' }).click();
  await expect(page.getByRole('table', { name: 'Лоты' }).locator('.badge--neg').first()).toBeVisible();
  await open(page, 'zakupki/postavshiki', 'Договоры и поставщики');
  await expect(page.getByRole('table', { name: 'Закупки по филиалам' })).toBeVisible();
  await open(page, 'zakupki/ekonomiya', 'Экономия');
  await expect(page.getByRole('table', { name: 'Экономия по способам закупки' })).toBeVisible();
  await expectNoHorizontalScroll(page);
  await expectNoAxeViolations(page);
  expect(csp).toEqual([]);
});

test('Инвестиции: сводка, реестр объектов, источники, риски; филиал без объектов', async ({ page }, info) => {
  test.setTimeout(120_000);
  const csp = watchCsp(page);
  await login(page, adminFor(info.project.name), '#investicii/svod');
  await expect(page.getByRole('heading', { level: 1, name: 'Инвестиции: сводка' })).toBeVisible();
  await expect(page.getByRole('img', { name: 'Освоение нарастающим итогом' })).toBeVisible();
  await expectNoAxeViolations(page);
  await open(page, 'investicii/obekty', 'Объекты');
  if (info.project.name === 'desktop-1440') {
    await expect(page.getByRole('table', { name: 'Реестр объектов' }).locator('tbody tr')).toHaveCount(14);
  }
  await open(page, 'investicii/istochniki', 'Источники и освоение');
  await expect(page.getByRole('list', { name: 'Освоение по объектам' })).toBeVisible();
  await open(page, 'investicii/riski', 'Сроки и риски');
  await expect(page.getByText('Этапы и сроки')).toBeVisible();
  await expectNoHorizontalScroll(page);
  await expectNoAxeViolations(page);
  await page.evaluate(() => { window.location.hash = 'investicii/svod?br=1'; });
  await expect(page.getByText('У выбранного филиала нет объектов адресной программы.')).toBeVisible();
  expect(csp).toEqual([]);
});

test('Кадры: сводка, численность, оплата труда, движение', async ({ page }, info) => {
  test.setTimeout(120_000);
  const csp = watchCsp(page);
  await login(page, adminFor(info.project.name), '#kadry/svod');
  await expect(page.getByRole('heading', { level: 1, name: 'Кадры: сводка' })).toBeVisible();
  await expect(page.getByText('Штатная численность')).toBeVisible();
  await expect(page.getByRole('img', { name: 'Фонд оплаты труда по месяцам' })).toBeVisible();
  await expectNoAxeViolations(page);
  await open(page, 'kadry/chislennost', 'Численность');
  await expect(page.getByRole('list', { name: 'Вакансии по филиалам' })).toBeVisible();
  await open(page, 'kadry/fot', 'Оплата труда');
  await expect(page.getByText('Доля ФОТ в расходовании')).toBeVisible();
  await open(page, 'kadry/dvizhenie', 'Движение кадров');
  await expect(page.getByRole('table', { name: 'Текучесть по филиалам' })).toBeVisible();
  await expectNoHorizontalScroll(page);
  await expectNoAxeViolations(page);
  expect(csp).toEqual([]);
});

test('Экономист филиала: только свои кадры, без закупок и инвестиций, без персональных полей', async ({ page }, info) => {
  test.setTimeout(120_000);
  test.skip(info.project.name !== 'desktop-1440', 'bitta kenglik yetarli');
  await login(page, 'e2e_branch', '#kadry/chislennost');
  const table = page.getByRole('table', { name: 'Численность по филиалам' });
  await expect(table).toBeVisible();
  await expect(table.locator('tbody tr')).toHaveCount(1);
  await expect(table.getByText('Каскад Чирчикских ГЭС')).toBeVisible();
  expect((await page.request.get('/api/v1/zakupki/svod')).status()).toBe(403);
  expect((await page.request.get('/api/v1/investicii/svod')).status()).toBe(403);
  expect((await page.request.get('/api/v1/kadry/svod?br=2')).status()).toBe(403);
  const own = await page.request.get('/api/v1/kadry/chislennost');
  expect(own.status()).toBe(200);
  const body = (await own.json()) as { branches: Array<{ branch_id: number }> };
  expect(body.branches.map((b) => b.branch_id)).toEqual([3]);
  expect(keys(body).filter((k) => PERSONAL.test(k))).toEqual([]);
});
