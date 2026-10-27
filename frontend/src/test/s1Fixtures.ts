import type {
  AlertsOut,
  CalendarOut,
  CashKpisOut,
  ItemBranchesOut,
  KaznaCalendarOut,
  KaznaCelevyeOut,
  KaznaDogovoryOut,
  KaznaKpisOut,
  KaznaPlatezhiOut,
  KaznaSvodOut,
  ObzorExcelOut,
  ObzorFlowOut,
  ObzorSvodOut,
  ReportPeriodOut,
} from '../api/types';

export const PERIOD_M08: ReportPeriodOut = { code: 'm08', label: 'Август 2026', date_from: '2026-08-01', date_to: '2026-08-31', open_last: false };

export const CASH_KPIS: CashKpisOut = {
  opening: 1000, inflow: 100, outflow: 40, net: 60, closing: 1060, diff: 0,
  opening_prev: null, inflow_prev: 80, outflow_prev: 50, net_prev: 30, closing_prev: 750, diff_prev: null, has_data: true,
};

const months = Array.from({ length: 9 }, (_, i) => ({
  month_id: 202601 + i, inflow: 10 * (i + 1), outflow: 5 * (i + 1), closing: 900 + i * 10, inflow_prev: 9 * (i + 1), outflow_prev: 4 * (i + 1),
}));

export const SVOD: ObzorSvodOut = {
  period: PERIOD_M08,
  kpis: CASH_KPIS,
  months,
  activity: [
    { activity: 'centralized', amount: 10 },
    { activity: 'operating', amount: 25 },
    { activity: 'investing', amount: 5 },
  ],
  branches: [
    { branch_id: 2, name: 'Чарвакская ГЭС', short_name: 'Чарвак', opening: 600, inflow: 70, outflow: 30, net: 40, closing: 640, diff: 0 },
    { branch_id: 3, name: 'Каскад Чирчикских ГЭС', short_name: 'Чирчик', opening: 400, inflow: 30, outflow: 10, net: 20, closing: 420, diff: 0 },
  ],
  items_in: [{ item_id: 11, code: 'PKM54-I01', name: 'Реализация электроэнергии', activity: 'operating', amount: 100 }],
  items_out: [
    { item_id: 21, code: 'PKM54-O03', name: 'Налоги и обязательные платежи', activity: 'centralized', amount: 25 },
    { item_id: 22, code: 'PKM54-O09', name: 'Прочие операционные расходы', activity: 'operating', amount: 15 },
  ],
  stations: [
    { branch_id: 1, code: 'UGE-01', name: 'АО «Узбекгидроэнерго»', short_name: 'Узбекгидроэнерго', kind: 'head', capacity_mw: null, lat: 41.3111, lon: 69.2797, inflow: 0, outflow: 0, closing: 5000, receivable: null, payable: null, overdue_payable: null, production: null },
    { branch_id: 2, code: 'UGE-02', name: 'Чарвакская ГЭС', short_name: 'Чарвак', kind: 'ges', capacity_mw: 666, lat: 41.626, lon: 70.029, inflow: 70, outflow: 30, closing: 640, receivable: 20, payable: 50, overdue_payable: 15, production: null },
    { branch_id: 6, code: 'UGE-06', name: 'Туямуюнская ГЭС', short_name: 'Туямуюн', kind: 'ges', capacity_mw: 150, lat: 41.24, lon: 61.41, inflow: 5, outflow: 3, closing: 90, receivable: null, payable: null, overdue_payable: null, production: null },
  ],
};

export const FLOW_IN: ObzorFlowOut = {
  period: PERIOD_M08, kpis: CASH_KPIS, direction: 'in', months: months.map((m) => m.month_id),
  series: [
    { key: '11', name: 'Реализация электроэнергии', values: months.map((m) => m.inflow) },
    { key: 'others', name: 'Остальные статьи', values: months.map(() => 1) },
  ],
  items: SVOD.items_in, activity: [],
  banks: [{ bank_name: 'Узпромстройбанк', amount: 60, closing: 700 }, { bank_name: 'Асакабанк', amount: 40, closing: 360 }],
  branches: [{ branch_id: 2, name: 'Чарвакская ГЭС', amount: 70 }, { branch_id: 3, name: 'Каскад Чирчикских ГЭС', amount: 30 }],
};

export const FLOW_OUT: ObzorFlowOut = {
  ...FLOW_IN, direction: 'out',
  series: [
    { key: 'centralized', name: 'Централизованная', values: months.map(() => 2) },
    { key: 'operating', name: 'Операционная', values: months.map(() => 3) },
    { key: 'investing', name: 'Инвестиционная', values: months.map(() => 1) },
  ],
  items: SVOD.items_out, activity: SVOD.activity,
  branches: [{ branch_id: 2, name: 'Чарвакская ГЭС', amount: 30 }, { branch_id: 3, name: 'Каскад Чирчикских ГЭС', amount: 10 }],
};

export const EXCEL: ObzorExcelOut = {
  period: PERIOD_M08, kpis: CASH_KPIS, branches: SVOD.branches,
  total: { branch_id: 0, name: 'Итого', short_name: 'Итого', opening: 1000, inflow: 100, outflow: 40, net: 60, closing: 1060, diff: 0 },
  detail: [
    { branch_id: 2, branch_name: 'Чарвакская ГЭС', direction: 'in', item_id: 11, item_name: 'Реализация электроэнергии', activity: 'operating', amount: 70 },
    { branch_id: 2, branch_name: 'Чарвакская ГЭС', direction: 'out', item_id: 21, item_name: 'Налоги и обязательные платежи', activity: 'centralized', amount: 25 },
    { branch_id: 3, branch_name: 'Каскад Чирчикских ГЭС', direction: 'out', item_id: 22, item_name: 'Прочие операционные расходы', activity: 'operating', amount: 5 },
  ],
};

export const ALERTS: AlertsOut = {
  period: PERIOD_M08,
  checked: ['Остаток ниже месячного расходования', 'Исполнение плана платежей'],
  items: [
    { code: 'contracts_overdue_90d', level: 'critical', title: 'Просроченные договоры', message: '1 договор просрочен более 90 дней на сумму 60,0 млн', section: 'kazna', page: 'dogovory', value: 1 },
    { code: 'payment_plan_execution', level: 'warning', title: 'Исполнение плана платежей', message: 'исполнение 40,0%, отклонение 18,0 млн', section: 'kazna', page: 'platezhi', value: 0.4 },
  ],
};

export const KAZNA_KPIS: KaznaKpisOut = {
  balance: 1060, balance_date: '2026-08-31', banks: 2, plan: 50, fact: 40, execution: 0.8, orders_count: 3, orders_amount: 17,
  requests_count: 2, requests_amount: 11, receivable: 50, payable: 100, overdue_payable: 0,
};

const statuses = ['черновик', 'на согласовании', 'утверждено', 'отправлено в банк', 'исполнено', 'отклонено'];

export const CALENDAR: CalendarOut = {
  as_of: '2026-09-24', start: '2026-09-25', total: 130, balance: 1078, coverage: 1078 / 130,
  days: Array.from({ length: 14 }, (_, i) => {
    const d = new Date(Date.UTC(2026, 8, 25 + i));
    return { date: d.toISOString().slice(0, 10), taxes: 0, salary: 0, loans: i === 7 ? 120 : 0, contracts: i === 0 ? 6 : i === 6 ? 4 : 0, total: i === 7 ? 120 : i === 0 ? 6 : i === 6 ? 4 : 0 };
  }),
};

export const EMPTY_CALENDAR: CalendarOut = { as_of: null, start: null, days: [], total: 0, balance: null, coverage: null };

export const KAZNA_SVOD: KaznaSvodOut = {
  period: PERIOD_M08, kpis: KAZNA_KPIS,
  plan_fact: [{ item_id: 22, name: 'Прочие операционные расходы', activity: 'operating', plan: 50, fact: 40, execution: 0.8, deviation: 10 }],
  orders: statuses.map((status) => ({ status, count: status === 'исполнено' ? 2 : status === 'отклонено' ? 1 : 0, amount: status === 'исполнено' ? 15 : status === 'отклонено' ? 2 : 0 })),
  calendar: CALENDAR,
  banks: [{ bank_name: 'Узпромстройбанк', balance: 700 }, { bank_name: 'Асакабанк', balance: 360 }],
  contracts: [
    { contract_id: 2, number: '№ 2/2025', cp_name: 'ООО «Тест Поставщик»', branch_id: 3, branch_name: 'Каскад Чирчикских ГЭС', kind: 'receivable', amount: 50, overdue: 10, overdue_days: 20, end_date: '2026-06-30' },
    { contract_id: 1, number: '№ 1/2025', cp_name: 'ООО «Гидромонтаж»', branch_id: 3, branch_name: 'Каскад Чирчикских ГЭС', kind: 'payable', amount: 100, overdue: 0, overdue_days: 0, end_date: '2026-12-31' },
  ],
};

export const KAZNA_PLATEZHI: KaznaPlatezhiOut = { period: PERIOD_M08, kpis: KAZNA_KPIS, plan_fact: KAZNA_SVOD.plan_fact, orders: KAZNA_SVOD.orders };

export const KAZNA_CALENDAR: KaznaCalendarOut = {
  period: PERIOD_M08, calendar: CALENDAR, banks: KAZNA_SVOD.banks,
  requests: [{ branch_id: 3, name: 'Каскад Чирчикских ГЭС', count: 2, amount: 11 }],
};

export const KAZNA_DOGOVORY: KaznaDogovoryOut = {
  period: PERIOD_M08, kpis: KAZNA_KPIS, contracts: KAZNA_SVOD.contracts,
  by_branch: [{ branch_id: 3, name: 'Каскад Чирчикских ГЭС', receivable: 50, payable: 100, overdue_payable: 30 }],
};

export const KAZNA_CELEVYE: KaznaCelevyeOut = {
  period: PERIOD_M08,
  sources: [{ key: 1, name: 'Бюджетные средства на капитальные вложения', allocated: 20, used: 10, share: 0.5 }],
  branches: [{ key: 3, name: 'Каскад Чирчикских ГЭС', allocated: 20, used: 10, share: 0.5 }],
};

export const ITEM_BRANCHES: ItemBranchesOut = {
  period: PERIOD_M08, item: { item_id: 22, code: 'PKM54-O09', name: 'Прочие операционные расходы', activity: 'operating', direction: 'out' },
  total: 40, rows: [{ branch_id: 3, name: 'Каскад Чирчикских ГЭС', fact: 40, plan: 50 }],
};
