import type {
  KredityGrafikOut,
  KredityReestrOut,
  KreditySvodOut,
  LoanKpisOut,
  LoanPaymentOut,
  LoanRowOut,
  LoanYearOut,
  ReportPeriodOut,
} from '../api/types';

export const PERIOD_M08_KR: ReportPeriodOut = { code: 'm08', label: 'Август 2026', date_from: '2026-08-01', date_to: '2026-08-31', open_last: false };

function payment(day: string, loanId: number, creditor: string, project: string, principal: number | null, interest: number | null): LoanPaymentOut {
  return {
    day,
    loan_id: loanId,
    creditor,
    project,
    branch_name: loanId === 1 ? 'Чарвакская ГЭС' : 'Каскад Чирчикских ГЭС',
    principal,
    interest,
    total: principal === null || interest === null ? null : principal + interest,
  };
}

const ADB = 'Азиатский банк развития';
const NBU = 'Национальный банк';

export const UPCOMING: LoanPaymentOut[] = [
  payment('2026-09-15', 1, ADB, 'Модернизация Чарвакской ГЭС', 1000, 460),
  payment('2026-10-10', 2, NBU, 'Оборотные средства', 100, 18),
  payment('2027-03-15', 1, ADB, 'Модернизация Чарвакской ГЭС', 1000, 400),
  payment('2027-10-10', 2, NBU, 'Оборотные средства', 300, 18),
  payment('2028-03-15', 1, ADB, 'Модернизация Чарвакской ГЭС', null, null),
];

export const SCHEDULE: LoanYearOut[] = Array.from({ length: 10 }, (_, i) => ({
  year: 2026 + i,
  principal: [2200, 1300, 7000][i] ?? 0,
  interest: [1008, 418, 350][i] ?? 0,
}));

export const LOAN_KPIS: LoanKpisOut = {
  as_of: '2026-08-31',
  loans: 2,
  portfolio: 9400,
  rate: 522 / 9400,
  fx_share: 9000 / 9400,
  service: 3208,
  paid: 1630,
  paid_share: 1630 / 3208,
  next_payment: UPCOMING[0] ?? null,
  peak_year: 2028,
  peak_amount: 7350,
  missing_fx: [],
  dscr: null,
};

export const LOAN_ROWS: LoanRowOut[] = [
  {
    loan_id: 1, loan_code: 'ADB-01', creditor: ADB, project: 'Модернизация Чарвакской ГЭС', branch_id: 2, branch_name: 'Чарвакская ГЭС',
    currency: 'USD', rate: 0.05, outstanding: 9000, outstanding_cur: 0.76, original_cur: 0.85, repaid_share: 0.1, grace_until: '2027-01-01', in_grace: true, maturity: '2028-12-31',
  },
  {
    loan_id: 2, loan_code: 'NBU-02', creditor: NBU, project: 'Оборотные средства', branch_id: 3, branch_name: 'Каскад Чирчикских ГЭС',
    currency: 'UZS', rate: 0.18, outstanding: 400, outstanding_cur: 400, original_cur: 500, repaid_share: 0.2, grace_until: null, in_grace: false, maturity: '2027-12-31',
  },
];

const CURRENCIES = [{ name: 'USD', amount: 9000 }, { name: 'UZS', amount: 400 }];

export const KREDITY_SVOD: KreditySvodOut = {
  period: PERIOD_M08_KR, has_loans: true, kpis: LOAN_KPIS, schedule: SCHEDULE, currencies: CURRENCIES, upcoming: UPCOMING,
};

export const KREDITY_REESTR: KredityReestrOut = {
  period: PERIOD_M08_KR, has_loans: true, kpis: LOAN_KPIS, loans: LOAN_ROWS,
  creditors: [{ name: ADB, amount: 9000 }, { name: NBU, amount: 400 }], currencies: CURRENCIES,
};

export const KREDITY_GRAFIK: KredityGrafikOut = { period: PERIOD_M08_KR, has_loans: true, schedule: SCHEDULE, upcoming: UPCOMING };

export const KREDITY_EMPTY_GRAFIK: KredityGrafikOut = {
  period: PERIOD_M08_KR, has_loans: false, schedule: SCHEDULE.map((y) => ({ ...y, principal: 0, interest: 0 })), upcoming: [],
};
