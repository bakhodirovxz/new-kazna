import axe from 'axe-core';
import { expect } from 'vitest';

/** jsdom rang hisoblay olmaydi — kontrast tokens.test.ts va Playwright'da tekshiriladi. */
export async function expectNoAxeViolations(node: Element): Promise<void> {
  const result = await axe.run(node, {
    rules: { 'color-contrast': { enabled: false }, region: { enabled: false } },
  });
  const problems = result.violations.map(
    (v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(', ')}`,
  );
  expect(problems).toEqual([]);
}
