import { expect, test } from '@playwright/test';
import { totp } from '../totp';

// RFC 6238 A-ilova (SHA-1, "12345678901234567890"): 8 raqamli kodning oxirgi 6 tasi.
const RFC_SECRET = 'GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ';

test('TOTP generatori RFC 6238 test vektorlariga mos', ({}, info) => {
  test.skip(info.project.name !== 'desktop-1440', 'brauzersiz test — bir marta yetarli');
  expect(totp(RFC_SECRET, 59_000)).toBe('287082');
  expect(totp(RFC_SECRET, 1_111_111_109_000)).toBe('081804');
  expect(totp(RFC_SECRET, 2_000_000_000_000)).toBe('279037');
});
