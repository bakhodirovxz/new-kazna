import { ApiError } from '../api/client';
import { t } from '../i18n';

/** Auth formalari uchun: 429 — kutish vaqti, qolgani — server xabari (ruscha) yoki umumiy matn. */
export function authErrorText(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 429) return t('error.rateLimited', { seconds: error.retryAfter ?? 60 });
    return error.message;
  }
  return t('error.generic');
}
