import { expect, test } from '@playwright/test';
import { signIn } from '../fixtures';

test('filialga bog\'langan foydalanuvchi: filtr qulflangan, begona filial va admin ochilmaydi', async ({ page }, info) => {
  test.skip(info.project.name !== 'desktop-1440', 'rol mantiqi kenglikka bog\'liq emas');

  await page.goto('/#obzor/svod?br=5');
  await expect(page).toHaveURL(/#login\?next=obzor%2Fsvod%3Fbr%3D5$/);
  await signIn(page, 'e2e_branch');
  await expect(page).toHaveURL(/#obzor\/svod\?br=3$/);
  await expect(page.getByLabel('Филиал', { exact: true })).toBeDisabled();
  await expect(page.getByText('Доступны только данные вашего филиала')).toBeVisible();

  await page.getByRole('button', { name: /Меню пользователя/ }).click();
  await expect(page.getByRole('menuitem', { name: 'Администрирование' })).toHaveCount(0);
  await page.keyboard.press('Escape');

  await page.goto('/#admin/users');
  await expect(page.getByRole('heading', { name: 'Нет доступа' })).toBeVisible();
});
