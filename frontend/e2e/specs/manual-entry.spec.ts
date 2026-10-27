import { expect, test, type BrowserContext, type Page } from '@playwright/test';
import { expectNoHorizontalScroll, signIn } from '../fixtures';

/** MVP (23a): kirituvchi -> tasdiqlovchi -> nashr; o'zini tasdiqlash yo'q;
 *  filial doirasi; CSP buzilishi yo'q. Haqiqiy dev stack + worker kerak (ETL so'rovi <= 1 daqiqa). */

const KIND = { maker: 'e2e_maker', checker: 'e2e_checker' } as const;

function width(project: string): string {
  return project.split('-')[1] ?? '1440';
}

/** Oldingi oyning oxirgi kuni: har doim "bugundan oldin" va joriy yil (ytd) filtriga mos. */
function lastDayOfPreviousMonth(): string {
  const now = new Date();
  const d = new Date(Date.UTC(now.getFullYear(), now.getMonth(), 0));
  return d.toISOString().slice(0, 10);
}

function uniqueAccount(): string {
  const tail = String(Date.now()).slice(-12) + String(Math.floor(Math.random() * 1000)).padStart(3, '0');
  return `20208${tail}`.slice(0, 20);
}

async function goto(page: Page, hash: string): Promise<void> {
  await page.evaluate((h) => { window.location.hash = h; }, hash);
  await expect(page).toHaveURL(new RegExp(`#${hash.replace(/[/?]/g, '\\$&')}`));
}

async function watchCsp(page: Page): Promise<void> {
  await page.addInitScript(() => {
    (window as unknown as { __csp: string[] }).__csp = [];
    document.addEventListener('securitypolicyviolation', (e) => {
      (window as unknown as { __csp: string[] }).__csp.push(`${e.violatedDirective} ${e.blockedURI}`);
    });
  });
}

async function cspViolations(page: Page): Promise<string[]> {
  return page.evaluate(() => (window as unknown as { __csp?: string[] }).__csp ?? []);
}

async function csrfToken(context: BrowserContext): Promise<string> {
  const cookie = (await context.cookies()).find((c) => c.name === '__Host-ugk_csrf');
  expect(cookie, 'CSRF cookie').toBeDefined();
  return decodeURIComponent(cookie?.value ?? '');
}

async function submitDrawer(page: Page): Promise<void> {
  await page.getByRole('dialog').getByRole('button', { name: 'Отправить на согласование' }).click();
  await expect(page.getByRole('status').filter({ hasText: /Отправлено на согласование: пакет №\d+/ })).toBeVisible();
  await expect(page.getByRole('dialog')).toHaveCount(0);
}

async function pickFirstBranch(page: Page): Promise<void> {
  const select = page.getByRole('dialog').getByLabel('Филиал');
  await select.selectOption({ index: 1 });
}

async function openFirstBatchOf(page: Page, name: string | RegExp): Promise<void> {
  await page.getByRole('button', { name }).first().click();
}

test('kirituvchi hisob va qoldiq kiritadi, tasdiqlovchi tasdiqlaydi, nashr qilinadi', async ({ page, browser }, info) => {
  test.setTimeout(300_000);
  const w = width(info.project.name);
  const number = uniqueAccount();
  const last4 = number.slice(-4);
  await watchCsp(page);

  // 1. Kirituvchi: bank hisobi
  await page.goto('/#vvod/kazna-bank_account');
  await signIn(page, `${KIND.maker}_${w}`);
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await expect(page.getByText('Сведения, которые 1С не передаёт')).toBeVisible();
  await page.getByRole('button', { name: 'Добавить' }).click();
  const drawer = page.getByRole('dialog');
  await pickFirstBranch(page);
  await drawer.getByLabel('Банк').selectOption({ index: 1 });
  await drawer.getByLabel('Валюта').selectOption('UZS');
  await drawer.getByLabel('Номер счёта').fill(number);
  await submitDrawer(page);

  // 2. Tasdiqlovchi (alohida kontekst): hisobni tasdiqlaydi
  const checkerCtx = await browser.newContext({ ignoreHTTPSErrors: true, viewport: page.viewportSize() });
  const checker = await checkerCtx.newPage();
  await watchCsp(checker);
  await checker.goto('/#vvod/inbox');
  await signIn(checker, `${KIND.checker}_${w}`);
  await expect(checker.getByRole('table', { name: 'На согласовании' })).toBeVisible();
  await openFirstBatchOf(checker, /^Пакет №\d+$/);
  await expect(checker.getByRole('heading', { name: /Пакет №\d+/ })).toBeVisible();
  await expect(checker.getByText('…' + last4)).toBeVisible(); // sezgir qiymat faqat niqob
  await expect(checker.getByText(number)).toHaveCount(0);
  await checker.getByRole('button', { name: 'Утвердить' }).click();
  await expect(checker.getByText('Утверждено').first()).toBeVisible();

  // 3. Kirituvchi: shu hisob bo'yicha oy oxiri qoldig'i
  await goto(page, 'vvod/kazna-balance');
  await page.getByRole('button', { name: 'Добавить' }).click();
  await pickFirstBranch(page);
  await drawer.getByRole('combobox', { name: 'Счёт' }).fill(last4);
  await drawer.getByRole('option', { name: new RegExp(last4) }).first().click();
  await drawer.getByLabel(/Дата/).fill(lastDayOfPreviousMonth());
  await drawer.getByLabel(/Остаток/).fill('1 500,00');
  await submitDrawer(page);

  // 4. O'zini tasdiqlash imkonsiz: "Мои пакеты"da tugma yo'q, API 403
  await goto(page, 'vvod/batches');
  await openFirstBatchOf(page, /^Пакет №\d+$/);
  await expect(page.getByRole('button', { name: 'Утвердить' })).toHaveCount(0);
  const mine = await page.evaluate(async () => {
    const r = await fetch('/api/v1/data/batches?box=mine');
    return (await r.json()) as { items: Array<{ batch_id: number; version: number }> };
  });
  const own = mine.items[0];
  expect(own).toBeDefined();
  const csrf = await csrfToken(page.context());
  const denied = await page.request.post(`/api/v1/data/batches/${own?.batch_id}/approve`, {
    headers: { 'X-CSRF-Token': csrf },
    data: { expected_version: own?.version, comment: null },
  });
  expect(denied.status()).toBe(403);

  // 5. Tasdiqlovchi qoldiqni tasdiqlaydi va nashr holatini kutadi
  // Tasdiqlovchi hali oldingi paket sahifasida: ro'yxatga qaytamiz; yangi paket ro'yxatga fon so'rovi
  // (60 s interval) bilan keladi.
  await checker.getByRole('button', { name: 'К списку' }).click();
  await expect(checker.getByRole('button', { name: /^Пакет №\d+$/ }).first()).toBeVisible({ timeout: 90_000 });
  await openFirstBatchOf(checker, /^Пакет №\d+$/);
  await checker.getByRole('button', { name: 'Утвердить' }).click();
  await expect(checker.getByText('Утверждено').first()).toBeVisible();
  await expect(checker.getByText(/Опубликовано \(сборка №\d+\)/)).toBeVisible({ timeout: 150_000 });

  // 6. Reyestr va "История изменений"
  // Reyestr keshi (5 daqiqa) boshqa kontekstdagi tasdiqni ko'rmaydi: sahifani qayta yuklaymiz
  // (sessiya cookie'si saqlanadi).
  await page.reload();
  await goto(page, 'vvod/kazna-balance');
  await expect(page.getByRole('table', { name: 'Остатки на счетах' })).toContainText(/1\s500,00/);
  await page.getByRole('row').filter({ hasNotText: 'На согласовании' }).getByRole('button', { name: 'История изменений' }).first().click();
  await expect(page.getByRole('dialog', { name: 'История изменений' })).toContainText('Утверждено');
  await page.keyboard.press('Escape');

  // 7. "Казначейство" qoldiqni ko'rsatadi (best-effort: format s1 sahifasiga bog'liq)
  await goto(page, 'kazna/svod');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await expectNoHorizontalScroll(page);

  // 8. CSP buzilishi yo'q
  expect(await cspViolations(page)).toEqual([]);
  expect(await cspViolations(checker)).toEqual([]);
  await checkerCtx.close();
});

test('filial iqtisodchisi boshqa filial uchun paket yarata olmaydi', async ({ page }, info) => {
  test.skip(info.project.name !== 'desktop-1440', "rol mantiqi kenglikka bog'liq emas");
  // branch-scope.spec.ts shu foydalanuvchi bilan kirgan: TOTP qadami qayta ishlatilmaydi.
  await page.waitForTimeout(30_000 - (Date.now() % 30_000) + 500);
  await watchCsp(page);
  await page.goto('/#vvod/kazna-balance');
  await signIn(page, 'e2e_branch');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await page.getByRole('button', { name: 'Добавить' }).click();
  const branch = page.getByRole('dialog').getByLabel('Филиал');
  await expect(branch).toBeDisabled(); // faqat o'z filiali
  await page.keyboard.press('Escape');

  const csrf = await csrfToken(page.context());
  const foreign = await page.request.post('/api/v1/data/batches', {
    headers: { 'X-CSRF-Token': csrf },
    data: {
      entity: 'kazna.balance', branch_id: 5, origin: 'form', submit: false,
      items: [{ values: { branch_code: 'X', bank_code: 'X', date: lastDayOfPreviousMonth(), balance: '1.00' } }],
    },
  });
  expect(foreign.status()).toBe(403);
  expect(((await foreign.json()) as { error: { code: string } }).error.code).toBe('scope_violation');
  expect(await cspViolations(page)).toEqual([]);
});
