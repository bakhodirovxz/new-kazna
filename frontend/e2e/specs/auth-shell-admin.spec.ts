import { expect, test } from '@playwright/test';
import {
  adminFor,
  expectNoAxeViolations,
  expectNoHorizontalScroll,
  expectVisibleFocusRing,
  isMobile,
  sectionRows,
  signIn,
} from '../fixtures';

test('login → 2FA → navigatsiya → filtrlar → admin → sessiya tugashi', async ({ page }, info) => {
  test.setTimeout(120_000); // TOTP oynasini kutish uzun testni 30 s'dan oshirishi mumkin
  const mobile = isMobile(info.project.name);
  const desktop = info.project.name === 'desktop-1440';
  const username = adminFor(info.project.name);

  await page.goto('/#kazna/svod');
  await expect(page).toHaveURL(/#login\?next=kazna%2Fsvod$/);
  await expect(page.getByRole('heading', { name: 'Вход в систему' })).toBeVisible();
  await expectNoAxeViolations(page);

  await signIn(page, username);
  await expect(page).toHaveURL(/#kazna\/svod$/);
  await expect(page.getByRole('heading', { level: 1, name: 'Казначейство: сводка' })).toBeVisible();
  await expect(page.getByText('Раздел в разработке')).toBeVisible();
  await expectNoHorizontalScroll(page);
  await expectNoAxeViolations(page);

  // Chap menyu (mobil'da — Drawer).
  if (mobile) {
    await page.getByRole('button', { name: 'Меню раздела' }).click();
    await expect(page.getByRole('dialog')).toBeVisible();
    await expectNoAxeViolations(page); // Drawer ochiq
  }
  await page.getByRole('link', { name: 'Платёжный календарь' }).click();
  await expect(page).toHaveURL(/#kazna\/calendar$/);
  await expect(page.getByRole('heading', { level: 1, name: 'Платёжный календарь' })).toBeVisible();

  // Davr filtri URL'da va yangilanganda saqlanadi (mobil'da — BottomSheet).
  if (mobile) {
    await page.getByRole('button', { name: /^Фильтры/ }).click();
    await expect(page.getByRole('dialog')).toBeVisible();
    await expectNoAxeViolations(page); // BottomSheet ochiq
  }
  await page.getByLabel('Период', { exact: true }).selectOption('q1');
  if (mobile) await page.getByRole('button', { name: 'Готово' }).click();
  await expect(page).toHaveURL(/#kazna\/calendar\?per=q1$/);
  await page.reload();
  await expect(page.getByRole('group', { name: 'Активные фильтры' })).toContainText('I квартал');

  // Bo'lim almashtirish filtrni saqlaydi.
  await page.getByRole('navigation', { name: 'Разделы' }).getByRole('link', { name: 'Обзор' }).click();
  await expect(page).toHaveURL(/#obzor\/svod\?per=q1$/);
  await expectNoHorizontalScroll(page);

  // V3: bo'limlar qatorida (mobil'da gorizontal skroll) fokus halqasi ko'rinadi va kesilmaydi.
  // Oxirgi bosilgan havola (.sec) sichqoncha fokusida: klaviatura bilan Tab bosib :focus-visible .sec ga yetamiz.
  const onSection = () =>
    page.evaluate(() => document.activeElement?.classList.contains('sec') === true && document.activeElement.matches(':focus-visible'));
  await page.keyboard.press('Tab');
  for (let i = 0; i < 25 && !(await onSection()); i++) await page.keyboard.press('Tab');
  expect(await onSection()).toBe(true);
  await expectVisibleFocusRing(page, mobile ? '.sections' : undefined);

  // R-D1: yuqori panel 1280 / 1440 / 1920 da <= 2 qator, gorizontal skroll yo'q.
  if (desktop) {
    for (const width of [1280, 1440, 1920]) {
      await page.setViewportSize({ width, height: 900 });
      const rows = await sectionRows(page);
      expect(rows, `${width}px`).toBeGreaterThanOrEqual(1);
      expect(rows, `${width}px`).toBeLessThanOrEqual(2);
      await expectNoHorizontalScroll(page);
    }
    await page.setViewportSize({ width: 1440, height: 900 });
  }

  // Admin → foydalanuvchilar.
  await page.getByRole('button', { name: /Меню пользователя/ }).click();
  // 2FA уже подключена — пункт «Подключить 2FA» не показывается.
  await expect(page.getByRole('menuitem', { name: 'Подключить 2FA' })).toHaveCount(0);
  await page.getByRole('menuitem', { name: 'Администрирование' }).click();
  await expect(page).toHaveURL(/#admin\/users$/);
  await page.getByLabel('Поиск', { exact: true }).fill(username);
  await expect(page.getByText(username, { exact: true })).toBeVisible();
  if (!mobile) await expect(page.getByRole('table', { name: 'Пользователи' })).toBeVisible();
  await expectNoHorizontalScroll(page);
  await expectNoAxeViolations(page);

  // V4: mobil'da jadval kartochkaga aylanadi — katak yorliqlari saqlanadi.
  if (mobile) {
    const label = await page.locator('td[data-label="Роль"]').first().evaluate((el) => getComputedStyle(el, '::before').content);
    expect(label).toContain('Роль');
  }

  // V5: «Должности» → «Добавить должность» → bo'sh yuborish: native tekshiruvsiz, maxsus xatolar.
  await page.goto('/#admin/roles');
  await page.getByRole('tab', { name: 'Должности' }).click();
  await page.keyboard.press('ArrowRight'); // tab'lar bo'ylab klaviatura: fokus halqasi (V3)
  await expectVisibleFocusRing(page);
  await page.getByRole('tab', { name: 'Должности' }).click();
  await page.getByRole('button', { name: 'Добавить должность' }).click();
  const dialog = page.getByRole('dialog', { name: 'Новая должность' });
  await expect(dialog).toBeVisible();
  await dialog.getByRole('button', { name: 'Создать' }).click();
  await expect(dialog.getByText('Обязательное поле')).toHaveCount(2); // название + роль
  await expect(dialog).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(dialog).toBeHidden();

  // Sessiya tugadi (cookie yo'q) filtrli sahifada → login, qaytish manzili filtrlari bilan saqlanadi.
  await page.goto('/#kazna/calendar?per=q1');
  await expect(page.getByRole('heading', { level: 1, name: 'Платёжный календарь' })).toBeVisible();
  const usedStep = Math.floor(Date.now() / 30_000);
  await page.context().clearCookies();
  await page.reload();
  await expect(page).toHaveURL(/#login\?next=kazna%2Fcalendar%3Fper%3Dq1$/);

  // Review Focus 1: qayta kirgach aynan o'sha sahifa va filtr (desktop; TOTP replay — keyingi qadamni kutamiz).
  if (desktop) {
    await expect.poll(() => Math.floor(Date.now() / 30_000), { timeout: 40_000, intervals: [1000] }).toBeGreaterThan(usedStep);
    await signIn(page, username);
    await expect(page).toHaveURL(/#kazna\/calendar\?per=q1$/);
  }
});
