import { describe, expect, it } from 'vitest';
import css from './shell.css?raw';

/** Prototip: logo | bo'limlar (flex, wrap) | asboblar (flex:none) — D1: bo'limlar ≤ 2 qatorda. */
describe('shell.css top bar', () => {
  it('gives the sections column a wide flex basis from 1280px so tools wrap below instead of squeezing it', () => {
    const wide = /@media \(min-width: 1280px\) \{([^@]*)\}\s*(?:@|\/\*|$)/.exec(css)?.[1] ?? '';
    expect(wide).toMatch(/\.sections-nav \{[^}]*flex: 1 1 56rem;/);
  });
  it('lets sections wrap and shrink; tools stay unshrinkable and right-aligned', () => {
    expect(css).toMatch(/\.sections \{[^}]*flex: 1;[^}]*flex-wrap: wrap;[^}]*min-width: 0;/);
    expect(css).toMatch(/\.tools \{[^}]*flex: none;[^}]*margin-left: auto;/);
    expect(css).toMatch(/\.topbar \{[^}]*flex-wrap: wrap;/);
  });
});
