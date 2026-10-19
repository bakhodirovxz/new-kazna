import { expect, test } from '@playwright/test';

test('R-T17: index.html no-cache, hash-li assetlar immutable', async ({ page, request }, info) => {
  test.skip(info.project.name !== 'desktop-1440', 'server sarlavhasi kenglikka bog\'liq emas');
  const index = await request.get('/');
  expect(index.status()).toBe(200);
  expect(index.headers()['cache-control']).toBe('no-cache');

  await page.goto('/');
  const asset = await page.evaluate(
    () => document.querySelector<HTMLScriptElement>('script[src^="/assets/"]')?.getAttribute('src') ?? '',
  );
  expect(asset).toMatch(/^\/assets\//);
  expect((await request.get(asset)).headers()['cache-control']).toContain('immutable');
});
