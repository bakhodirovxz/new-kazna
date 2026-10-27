import { describe, expect, it } from 'vitest';
import css from './shell.css?raw';

/** Prototip: logo | bo'limlar (flex, wrap) | asboblar (flex:none) — D1: bo'limlar ≤ 2 qatorda. */
describe('shell.css top bar', () => {
  it('keeps all sections in one row from 1280px (no wrap) and wraps them only below', () => {
    expect(css).toMatch(/\.sections \{[^}]*flex: 1;[^}]*flex-wrap: nowrap;[^}]*min-width: 0;/);
    expect(css).toMatch(/@media \(max-width: 1279\.98px\) \{\s*\.sections \{ flex-wrap: wrap; \}/);
  });
  it('shows tool labels only on very wide screens; tools stay unshrinkable and right-aligned', () => {
    expect(css).toMatch(/@media \(max-width: 2399\.98px\) \{\s*\.tool__label,/);
    expect(css).toMatch(/\.tools \{[^}]*flex: none;[^}]*margin-left: auto;/);
    expect(css).toMatch(/\.topbar \{[^}]*flex-wrap: wrap;/);
  });
});
