import { expect, test, type Page } from '@playwright/test';
import { adminFor, expectNoHorizontalScroll, isMobile, signIn } from '../fixtures';

function watchCsp(page: Page): string[] {
  const violations: string[] = [];
  page.on('console', (msg) => {
    const text = msg.text();
    if (/Content Security Policy|Refused to/i.test(text)) violations.push(text);
  });
  return violations;
}

test('Финмодель: сводка, сценарий в адресе, доходы, долг, сценарии', async ({ page }, info) => {
  test.setTimeout(120_000);
  const csp = watchCsp(page);
  await page.waitForTimeout(30_000 - (Date.now() % 30_000) + 500); // boshqa TOTP qadami
  await page.goto('/#finmodel/svod');
  await signIn(page, adminFor(info.project.name));
  await expect(page.getByRole('heading', { level: 1, name: 'Финмодель: сводка' })).toBeVisible();
  await expect(page.getByText('Мощность к 2032 году')).toBeVisible();
  await expect(page.getByRole('img', { name: 'Выручка и EBITDA по годам' })).toBeVisible();
  await expect(page.getByRole('table', { name: 'Модель по годам' }).locator('tbody tr')).toHaveCount(7);
  // Boshlang'ich qoldiq: sintetik tarix 2024 yildan — 31.12.2025 holatida nol bo'lmasligi kerak.
  const model = await (await page.request.get('/api/v1/finmodel/model')).json() as { has_model: boolean; base: { opening_cash: number } };
  expect(model.has_model).toBe(true);
  expect(model.base.opening_cash).toBeGreaterThan(0);
  await page.getByRole('group', { name: 'Сценарий модели' }).getByRole('button', { name: 'Маловодье' }).click();
  await expect(page).toHaveURL(/#finmodel\/svod\?scen=water$/);
  await expect(page.getByText('Выработка ниже нормы на 15% в 2027–2029 годах').first()).toBeVisible();
  if (!isMobile(info.project.name)) {
    // Chap menyu havolasi ssenariyni bo'lim ichida saqlaydi (mobil'da menyu — yopiq Drawer).
    await page.getByRole('link', { name: /Доходы и расходы/ }).first().click();
    await expect(page).toHaveURL(/#finmodel\/dohody\?scen=water$/);
  } else {
    await page.evaluate(() => { window.location.hash = '#finmodel/dohody?scen=water'; });
  }
  await expect(page.getByRole('img', { name: 'Структура выручки по годам' })).toBeVisible();
  await expect(page.getByRole('table', { name: 'Себестоимость и тариф' })).toBeVisible();
  await page.evaluate(() => { window.location.hash = '#finmodel/dolg'; });
  await expect(page.getByRole('img', { name: 'Покрытие долга (DSCR)' })).toBeVisible();
  await expect(page.getByRole('table', { name: 'Инвестиции и долговая нагрузка по годам' })).toBeVisible();
  await page.evaluate(() => { window.location.hash = '#finmodel/scenarii'; });
  await expect(page.getByRole('table', { name: 'Сравнение сценариев' }).locator('tbody tr')).toHaveCount(4);
  await expect(page.getByRole('list', { name: 'Чувствительность' })).toBeVisible();
  await expect(page.getByRole('alert')).toHaveCount(0);
  await expectNoHorizontalScroll(page);
  expect(csp).toEqual([]);
});

test('Финмодель: экономист филиала не имеет доступа, DSCR в «Кредитах» — из модели', async ({ page }, info) => {
  test.skip(info.project.name !== 'desktop-1440', 'bitta kenglik yetarli');
  await page.goto('/#obzor/svod');
  await signIn(page, 'e2e_branch');
  await expect(page.getByRole('heading', { level: 1, name: 'Обзор: сводка' })).toBeVisible();
  expect((await page.request.get('/api/v1/finmodel/model')).status()).toBe(403);
  await page.context().clearCookies();
  await page.goto('/#kredity/svod');
  await page.reload();
  await page.waitForTimeout(30_000 - (Date.now() % 30_000) + 500); // boshqa TOTP qadami
  await signIn(page, adminFor(info.project.name));
  await expect(page.getByRole('heading', { level: 1, name: 'Кредиты: сводка' })).toBeVisible();
  const svod = await (await page.request.get('/api/v1/kredity/svod')).json() as { kpis: { dscr: number | null } };
  expect(svod.kpis.dscr).not.toBeNull();
});

test('Допущения финмодели (админ): правка, недопустимое значение, сохранение и возврат', async ({ page }, info) => {
  test.skip(info.project.name !== 'desktop-1440', 'global sozlama — bitta loyihada');
  test.setTimeout(90_000);
  await page.waitForTimeout(30_000 - (Date.now() % 30_000) + 500); // boshqa TOTP qadami
  await page.goto('/#admin/finmodel');
  await signIn(page, adminFor(info.project.name));
  await expect(page.getByRole('heading', { level: 1, name: 'Допущения финмодели' })).toBeVisible();
  const cell = page.getByRole('textbox', { name: 'Рост тарифа, 2027' });
  const original = await cell.inputValue();
  const save = page.getByRole('button', { name: 'Сохранить изменения' });
  await expect(save).toBeDisabled();
  // Chegaradan tashqari qiymat: saqlanmaydi, xabar ko'rinadi.
  await cell.fill('5');
  await save.click();
  await expect(page.getByRole('alert').filter({ hasText: 'Значение вне допустимого диапазона' })).toBeVisible();
  await page.getByRole('button', { name: 'Отменить изменения' }).click();
  await expect(cell).toHaveValue(original);
  // To'g'ri qiymat: saqlanadi, so'ng asl qiymat qaytariladi (global sozlama).
  const changed = original === '0,07' ? '0,08' : '0,07';
  await cell.fill(changed);
  await save.click();
  await expect(page.getByText('Допущения сохранены.')).toBeVisible();
  await page.mouse.move(0, 0); // sichqoncha ostidagi toast yopilmaydi
  await expect(page.locator('.toast')).toHaveCount(0, { timeout: 15_000 }); // toast tugmani yopib turadi
  await cell.fill(original);
  await save.click();
  await expect(page.getByText('Допущения сохранены.').first()).toBeVisible();
  await expect(cell).toHaveValue(original);
});
