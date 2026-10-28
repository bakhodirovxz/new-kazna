import type { AiRequestOut, AiStatusOut, FinBaseOut, FinmodelOut, FinSummaryOut, FinYearOut, Page } from '../api/types';

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

export const FIN_YEARS = [2026, 2027, 2028, 2029, 2030, 2031, 2032];
const DSCR = [1.35, 1.1, 1.5, 1.8, 2.0, 2.2, 2.4];

/** Yil qatori: summalar mln so'mda; 2027 — ковенант buzilishi va manfiy qoldiq. */
export function finYear(year: number, over: Partial<FinYearOut> = {}): FinYearOut {
  const i = year - 2026;
  const revenue = 5_000_000 + i * 500_000;
  const opex = 2_000_000 + i * 100_000;
  const tax = revenue * 0.15;
  const ebitda = revenue - opex - tax;
  const capex = i === 1 ? 2_900_000 : 400_000;
  const dscr = DSCR[i] ?? 2;
  const debt = Math.round(ebitda / dscr);
  return {
    year,
    capacity_mw: [2000, 2120, 2330, 2425, 2485, 2525, 2555][i] ?? 2555,
    generation: 7000 + i * 300,
    supply: 6890 + i * 295,
    tariff: Math.round(705 * 1.08 ** i),
    revenue,
    opex,
    tax,
    ebitda,
    margin: ebitda / revenue,
    capex_plan: i >= 3 ? 0 : capex,
    capex,
    principal: Math.round(debt * 0.7),
    interest: debt - Math.round(debt * 0.7),
    debt_service: debt,
    net_flow: ebitda - capex - debt,
    balance: i === 1 ? -150_000 : 300_000 + i * 200_000,
    dscr,
    covenant_breach: dscr < 1.2,
    unit_cost: Math.round(((opex + tax) / (6890 + i * 295)) * 100) / 100,
    ...over,
  };
}

export const FIN_SUMMARY_BASE: FinSummaryOut = {
  scenario: 'base', title: 'Базовый', note: 'Приток воды в норме, тариф растёт по плану, курс стабилен',
  capacity_last: 2555, capacity_added: 555, revenue_first: 5_000_000, revenue_last: 8_000_000, ebitda_total: 16_000_000,
  margin_avg: 0.4, capex_total: 5_300_000, debt_service_total: 8_000_000, dscr_min: 1.1, dscr_min_year: 2027,
  cum_flow: 1_500_000, negative_years: 1, verdict: 'needs_financing',
};

export const FIN_SUMMARIES: FinSummaryOut[] = [
  FIN_SUMMARY_BASE,
  { ...FIN_SUMMARY_BASE, scenario: 'water', title: 'Маловодье', note: 'Выработка ниже нормы на 15% в 2027–2029 годах', cum_flow: 900_000, dscr_min: 0.95 },
  { ...FIN_SUMMARY_BASE, scenario: 'tariff', title: 'Сдержанный тариф', note: 'Тариф растёт на 4% в год вместо 8%', cum_flow: 1_100_000, dscr_min: 1.05, revenue_last: 6_500_000 },
  { ...FIN_SUMMARY_BASE, scenario: 'fx', title: 'Ослабление сума', note: 'Курс растёт на 20%: дорожают валютные кредиты и импортное оборудование', cum_flow: 2_000_000, dscr_min: 1.3, negative_years: 0, verdict: 'funded' },
];

const BASE: FinBaseOut = {
  as_of: '2026-09-24', capacity_mw: 2000, opex_base: 2_000_000, opex_months: 12, opening_cash: 450_000,
  missing_fx: [], aip_missing_years: [2029, 2030, 2031, 2032], assumptions_at: '2026-09-20T10:00:00Z',
  stale_assumptions: false, covenant: 1.2,
};

export const FIN_MODEL: FinmodelOut = {
  has_model: true, scenario: 'base', company_wide: false, base: BASE,
  years: FIN_YEARS.map((y) => finYear(y)), summary: FIN_SUMMARY_BASE, scenarios: FIN_SUMMARIES,
  sensitivity: [
    { scenario: 'water', title: 'Маловодье', delta_cum: -600_000, dscr_min: 0.95 },
    { scenario: 'fx', title: 'Ослабление сума', delta_cum: 500_000, dscr_min: 1.3 },
    { scenario: 'tariff', title: 'Сдержанный тариф', delta_cum: -400_000, dscr_min: 1.05 },
  ],
};

export const FIN_MODEL_WATER: FinmodelOut = {
  ...FIN_MODEL, scenario: 'water', summary: FIN_SUMMARIES[1] ?? FIN_SUMMARY_BASE,
  years: FIN_YEARS.map((y) => finYear(y, y >= 2027 && y <= 2029 ? { generation: (7000 + (y - 2026) * 300) * 0.85 } : {})),
};

export const FIN_MODEL_STALE: FinmodelOut = {
  ...FIN_MODEL, company_wide: true,
  base: { ...BASE, stale_assumptions: true, missing_fx: ['XDR'], opex_months: 7 },
};

export const FIN_MODEL_EMPTY: FinmodelOut = {
  has_model: false, scenario: 'base', company_wide: false, base: null, years: [], summary: null, scenarios: [], sensitivity: [],
};
