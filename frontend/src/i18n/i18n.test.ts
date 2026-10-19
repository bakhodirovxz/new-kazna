import { expect, it } from 'vitest';
import { t } from './index';

it('interpolates parameters and keeps unknown placeholders', () => {
  expect(t('error.rateLimited', { seconds: 42 })).toBe('Слишком много запросов. Повторите через 42 с.');
  expect(t('error.rateLimited')).toBe('Слишком много запросов. Повторите через {seconds} с.');
  expect(t('common.retry')).toBe('Повторить');
});
