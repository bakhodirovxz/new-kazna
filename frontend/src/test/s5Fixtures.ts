import type { AiRequestOut, AiStatusOut, Page } from '../api/types';

export const AI_STATUS_ON: AiStatusOut = { enabled: true, reason: null, user_per_hour: 20, org_per_day: 300, used_last_hour: 2 };
export const AI_STATUS_OFF: AiStatusOut = { enabled: false, reason: 'disabled', user_per_hour: 20, org_per_day: 300, used_last_hour: 0 };

const JOURNAL_ROW: AiRequestOut = {
  id: 41, created_at: '2026-09-24T09:15:00Z', finished_at: '2026-09-24T09:15:21Z', username: 'kazna.spec',
  section: 'kredity', page: 'svod', filters: { br: null, per: 'ytd' }, preset: null, question: 'Почему вырос долг?',
  status: 'ok', error_code: null, context_chars: 5210, answer_chars: 1830, model: 'claude-opus-5-5', duration_ms: 21000,
};

export const AI_JOURNAL: Page<AiRequestOut> = {
  items: [JOURNAL_ROW, { ...JOURNAL_ROW, id: 40, question: null, preset: 'risks', status: 'timeout', error_code: 'ai_timeout', answer_chars: 0 }],
  total: 2, page: 1, page_size: 50,
};
