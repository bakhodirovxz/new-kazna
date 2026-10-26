import AxeBuilder from '@axe-core/playwright';
import { expect, type Page } from '@playwright/test';
import { totp } from './totp';

/** backend/app/devtools.py bilan bir xil qiymatlar (faqat dev/test). */
export const E2E_PASSWORD = 'E2e-Sinov-Kalit-2026!';
export const E2E_TOTP_SECRET = 'JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP';
export const NEW_PASSWORD = 'Yangi-Mustahkam-77#Qadam';

const ADMINS: Record<string, string> = {
  'mobile-390': 'e2e_admin_390',
  'tablet-1024': 'e2e_admin_1024',
  'desktop-1440': 'e2e_admin_1440',
};

/** Har kenglik o'z foydalanuvchisi bilan: bitta TOTP qadami ikki marta ishlatilmaydi. */
export function adminFor(project: string): string {
  return ADMINS[project] ?? 'e2e_admin_1440';
}

export function isMobile(project: string): boolean {
  return project === 'mobile-390';
}

export async function signIn(page: Page, username: string): Promise<void> {
  await page.getByLabel('Логин', { exact: true }).fill(username);
  await page.getByLabel('Пароль', { exact: true }).fill(E2E_PASSWORD);
  await page.getByRole('button', { name: 'Войти' }).click();
  await expect(page.getByRole('heading', { name: 'Подтверждение входа' })).toBeVisible();
  await page.getByLabel('Код из приложения', { exact: true }).fill(totp(E2E_TOTP_SECRET));
}

export async function expectNoHorizontalScroll(page: Page): Promise<void> {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
}

/** R-D1: yuqori paneldagi bo'limlar nechta qatorga tushgan (turli offsetTop soni). */
export async function sectionRows(page: Page): Promise<number> {
  return page.evaluate(
    () => new Set(Array.from(document.querySelectorAll<HTMLElement>('.sections .sec')).map((el) => el.offsetTop)).size,
  );
}

/** V3: Tab bilan fokus olgan elementda ko'rinadigan kontur bor; kesilgan emas (clip berilsa). */
export async function expectVisibleFocusRing(page: Page, clipSelector?: string): Promise<void> {
  const ring = await page.evaluate((clip) => {
    const el = document.activeElement as HTMLElement | null;
    if (!el) return null;
    const style = getComputedStyle(el);
    const width = parseFloat(style.outlineWidth);
    const offset = parseFloat(style.outlineOffset) || 0;
    const box = el.getBoundingClientRect();
    const pad = Math.max(0, width + offset);
    const bounds = clip ? el.closest(clip)?.getBoundingClientRect() : undefined;
    return {
      focusVisible: el.matches(':focus-visible'),
      style: style.outlineStyle,
      width,
      clipped: bounds ? box.top - pad < bounds.top - 0.5 || box.bottom + pad > bounds.bottom + 0.5 : false,
    };
  }, clipSelector);
  expect(ring).not.toBeNull();
  expect(ring?.focusVisible).toBe(true);
  expect(ring?.style).not.toBe('none');
  expect(ring?.width).toBeGreaterThanOrEqual(2);
  expect(ring?.clipped).toBe(false);
}

/** Axe: ochiq Drawer/BottomSheet kabi holatlarda ham — har kenglikda 0 buzilish. */
export async function expectNoAxeViolations(page: Page): Promise<void> {
  // Overlay animatsiyasi tugamaguncha rang yarim shaffof — contrast soxta buzilish beradi.
  // Cheksiz (spinner/skeleton) animatsiyalar kutilmaydi; bekor qilinganlari reject beradi — allSettled.
  await page.evaluate(() =>
    Promise.allSettled(
      document
        .getAnimations()
        .filter((a) => a.effect?.getComputedTiming().iterations !== Infinity)
        .map((a) => a.finished),
    ),
  );
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
}
