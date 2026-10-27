import { expect, test } from '@playwright/test';
import { E2E_PASSWORD, expectNoAxeViolations, NEW_PASSWORD } from '../fixtures';
import { totp } from '../totp';

/** 2FA majburiy emas (qaror 27.10.2026): parol to'g'ri bo'lsa sessiya ochiladi, 2FA esa taklif qilinadi. */
test('yangi xodim: majburiy parol almashtirish → 2FA taklifi → ulash → zaxira kodlar', async ({ page }, info) => {
  test.skip(info.project.name !== 'desktop-1440', 'oqim kenglikka bog\'liq emas — bir marta yetarli');

  await page.goto('/');
  await expect(page).toHaveURL(/#login$/);
  await page.getByLabel('Логин', { exact: true }).fill('e2e_new');
  await page.getByLabel('Пароль', { exact: true }).fill(E2E_PASSWORD);
  await page.getByRole('button', { name: 'Войти' }).click();

  // Vaqtinchalik parol: 2FA qadami yo'q, majburiy almashtirish saqlanadi.
  await expect(page.getByRole('heading', { name: 'Необходимо сменить пароль' })).toBeVisible();
  // V2: yashirin readonly username maydoni axe'da xato bermaydi.
  await expectNoAxeViolations(page);
  await page.getByLabel('Текущий пароль', { exact: true }).fill(E2E_PASSWORD);
  await page.getByLabel('Новый пароль', { exact: true }).fill(NEW_PASSWORD);
  await page.getByLabel('Повторите новый пароль', { exact: true }).fill(NEW_PASSWORD);
  await page.getByRole('button', { name: 'Сохранить пароль' }).click();

  // Paroldan keyin 2FA taklif qilinadi.
  await expect(page.getByRole('heading', { name: 'Подключить двухфакторную аутентификацию?' })).toBeVisible();
  await expectNoAxeViolations(page);
  await page.getByRole('button', { name: 'Подключить', exact: true }).click();

  // Kirgan foydalanuvchi ulashdan oldin joriy parolni tasdiqlaydi.
  await expect(page).toHaveURL(/#2fa\/setup$/);
  await page.getByLabel('Текущий пароль', { exact: true }).fill(NEW_PASSWORD);
  await page.getByRole('button', { name: 'Продолжить' }).click();
  await expect(page.getByRole('heading', { name: 'Подключение двухфакторной аутентификации' })).toBeVisible();
  await expect(page.getByRole('img', { name: /QR-код/ })).toBeVisible();
  await expect(page.getByText('Время подтверждения истекло')).toHaveCount(0);
  await expectNoAxeViolations(page);
  const secret = (await page.getByTestId('totp-secret').innerText()).replace(/\s+/g, '');
  await page.getByLabel('Код из приложения', { exact: true }).fill(totp(secret));
  await page.getByRole('button', { name: 'Подтвердить' }).click();

  // R-C3: bir martalik zaxira kodlar ekrani qoladi.
  await expect(page.getByRole('heading', { name: 'Резервные коды' })).toBeVisible();
  await expect(page).toHaveURL(/#2fa\/setup$/);
  await expect(page.getByTestId('backup-codes').getByRole('listitem')).toHaveCount(10);
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Скачать' }).click();
  expect((await download).suggestedFilename()).toBe('ugekazna-backup-codes-e2e_new.txt');
  const next = page.getByRole('button', { name: 'Продолжить' });
  await expect(next).toBeDisabled();
  await page.getByLabel('Я сохранил резервные коды в надёжном месте').check();
  await next.click();

  await expect(page).toHaveURL(/#obzor\/svod$/);
  await expect(page.getByRole('heading', { level: 1, name: 'Обзор: сводка' })).toBeVisible();
});

test('2FA можно пропустить: «Позже» открывает приложение, пункт меню остаётся', async ({ page }, info) => {
  test.skip(info.project.name !== 'desktop-1440', 'oqim kenglikka bog\'liq emas — bir marta yetarli');

  await page.goto('/');
  await page.getByLabel('Логин', { exact: true }).fill('e2e_skip');
  await page.getByLabel('Пароль', { exact: true }).fill(E2E_PASSWORD);
  await page.getByRole('button', { name: 'Войти' }).click();

  await expect(page.getByRole('heading', { name: 'Подключить двухфакторную аутентификацию?' })).toBeVisible();
  await page.getByRole('button', { name: 'Позже' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Обзор: сводка' })).toBeVisible();

  // Предложение больше не показывается, подключить можно из меню пользователя.
  await page.getByRole('button', { name: /Меню пользователя/ }).click();
  await expect(page.getByRole('menuitem', { name: 'Подключить 2FA' })).toBeVisible();
});
