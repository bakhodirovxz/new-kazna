import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';
import { E2E_PASSWORD, NEW_PASSWORD } from '../fixtures';
import { totp } from '../totp';

test('yangi xodim: 2FA ulash → zaxira kodlar → majburiy parol almashtirish', async ({ page }, info) => {
  test.skip(info.project.name !== 'desktop-1440', 'oqim kenglikka bog\'liq emas — bir marta yetarli');

  await page.goto('/');
  await expect(page).toHaveURL(/#login$/);
  await page.getByLabel('Логин', { exact: true }).fill('e2e_new');
  await page.getByLabel('Пароль', { exact: true }).fill(E2E_PASSWORD);
  await page.getByRole('button', { name: 'Войти' }).click();

  // R-C1: yangi foydalanuvchi #2fa/setup'ga yetadi (login'ga qaytarilmaydi).
  await expect(page).toHaveURL(/#2fa\/setup$/);
  await expect(page.getByRole('heading', { name: 'Подключение двухфакторной аутентификации' })).toBeVisible();
  // R-C2: login'dan keyin darhol enroll/start ishlaydi (backend javobdan oldin commit qiladi).
  await expect(page.getByRole('img', { name: /QR-код/ })).toBeVisible();
  await expect(page.getByText('Время подтверждения истекло')).toHaveCount(0);
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  const secret = (await page.getByTestId('totp-secret').innerText()).replace(/\s+/g, '');
  await page.getByLabel('Код из приложения', { exact: true }).fill(totp(secret));
  await page.getByRole('button', { name: 'Подтвердить' }).click();

  // R-C3: bir martalik zaxira kodlar ekrani qoladi (login/parol sahifasiga sakramaydi).
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

  await expect(page.getByRole('heading', { name: 'Необходимо сменить пароль' })).toBeVisible();
  // V2: yashirin readonly username maydoni axe'da xato bermaydi.
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.getByLabel('Текущий пароль', { exact: true }).fill(E2E_PASSWORD);
  await page.getByLabel('Новый пароль', { exact: true }).fill(NEW_PASSWORD);
  await page.getByLabel('Повторите новый пароль', { exact: true }).fill(NEW_PASSWORD);
  await page.getByRole('button', { name: 'Сохранить пароль' }).click();

  await expect(page).toHaveURL(/#obzor\/svod$/);
  await expect(page.getByRole('heading', { level: 1, name: 'Обзор: сводка' })).toBeVisible();
});
