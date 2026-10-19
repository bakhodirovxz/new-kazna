import { describe, expect, it } from 'vitest';
import { contrastRatio, readTokens } from './contrast';
import css from './tokens.css?raw';

const tokens = readTokens(css);
const color = (ref: string): string => {
  if (ref.startsWith('#')) return ref;
  const value = tokens[ref];
  if (!value) throw new Error(`token ${ref} topilmadi`);
  return value;
};

/** [oldingi rang, fon, minimal nisbat] — WCAG 2.1: matn 4.5, matn bo'lmagan 3.0. */
const PAIRS: Array<[string, string, number]> = [
  ['--ink', '--bg', 4.5],
  ['--ink', '--card', 4.5],
  ['--ink', '--soft', 4.5],
  ['--muted', '--bg', 4.5],
  ['--muted', '--card', 4.5],
  ['--muted', '--soft', 4.5],
  ['--muted', '--neg-bg', 4.5],
  ['--brand', '--card', 4.5],
  ['--brand', '--soft', 4.5],
  ['--brand', '--bg', 4.5],
  ['--brand2', '--card', 4.5],
  ['--neg', '--card', 4.5],
  ['--neg', '--bg', 4.5],
  ['--neg', '--neg-bg', 4.5],
  ['--warn', '--warn-bg', 4.5],
  ['--ok', '--ok-bg', 4.5],
  ['--ok', '--card', 4.5],
  ['#ffffff', '--brand2', 4.5],
  ['#ffffff', '--brand', 4.5],
  ['#ffffff', '--neg', 4.5],
  ['#ffffff', '--ok', 4.5],
  ['#ffffff', '--ink', 4.5],
  ['--top-ink', '--top', 4.5],
  ['--top-ink', '--top-end', 4.5],
  ['--top-ink', '--top2', 4.5],
  ['--focus', '--card', 3],
  ['--focus', '--bg', 3],
  ['--focus-on-dark', '--top-end', 3],
];

describe('design tokens', () => {
  it('parses every token used by the contrast table', () => {
    for (const [fg, bg] of PAIRS) {
      expect(color(fg)).toMatch(/^#[0-9a-f]{6}$/);
      expect(color(bg)).toMatch(/^#[0-9a-f]{6}$/);
    }
  });

  it.each(PAIRS)('%s on %s has contrast ≥ %s', (fg, bg, min) => {
    expect(contrastRatio(color(fg), color(bg))).toBeGreaterThanOrEqual(min);
  });
});
