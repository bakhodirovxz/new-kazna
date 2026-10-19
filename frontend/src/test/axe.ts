import axe from 'axe-core';
import { expect, vi } from 'vitest';

/** jsdom rang hisoblay olmaydi — kontrast tokens.test.ts va Playwright'da tekshiriladi. */
export async function expectNoAxeViolations(node: Element): Promise<void> {
  // axe ikonka-ligatura tekshiruvi canvas so'raydi; jsdom'da yo'q — jim stub (stderr shovqinisiz).
  const canvas = vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null);
  const result = await axe.run(node, {
    rules: { 'color-contrast': { enabled: false }, region: { enabled: false } },
  });
  canvas.mockRestore();
  const problems = result.violations.map(
    (v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(', ')}`,
  );
  expect(problems).toEqual([]);
}
