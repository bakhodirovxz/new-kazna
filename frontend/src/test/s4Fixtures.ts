import type {
  HrBranchOut,
  HrCategoryOut,
  HrKpisOut,
  HrMonthOut,
  InvCumOut,
  InvKpisOut,
  InvObjectOut,
  InvObjectStagesOut,
  InvSourceOut,
  KadryChislennostOut,
  KadryDvizhenieOut,
  KadryFotOut,
  KadrySvodOut,
  ReportPeriodOut,
  InvIstochnikiOut,
  InvObektyOut,
  InvRiskiOut,
  InvSvodOut,
  ZakEkonomiyaOut,
  ZakKpisOut,
  ZakLotOut,
  ZakLotyOut,
  ZakMethodOut,
  ZakMonthOut,
  ZakPostavshikiOut,
  ZakSvodOut,
} from '../api/types';

export const PERIOD_M08_S4: ReportPeriodOut = { code: 'm08', label: 'Август 2026', date_from: '2026-08-01', date_to: '2026-08-31', open_last: false };

export const ZAK_KPIS: ZakKpisOut = {
  has_data: true, contracted: 140, contracts: 2, start_contracted: 150, savings: 10, savings_share: 0.066667, ytd: 197, plan: 1000,
  plan_execution: 0.197, in_work: 2, in_work_start: 110, overdue: 1, overdue_start: 80, direct: 50, direct_share: 0.357143,
  avg_days: 8.5, cancelled: 1, cancelled_start: 40,
};
export const ZAK_MONTHS: ZakMonthOut[] = Array.from({ length: 9 }, (_, i) => ({ month_id: 202601 + i, contracted: i === 7 ? 140 : 20 + i }));
export const ZAK_METHODS: ZakMethodOut[] = [
  { method: 'eshop', title: 'Электронный магазин', lots: 1, start: 100, contracted: 90, savings: 10, savings_share: 0.1, avg_days: 12, norm_days: 15 },
  { method: 'direct', title: 'Прямой договор', lots: 1, start: 50, contracted: 50, savings: 0, savings_share: 0, avg_days: 5, norm_days: 12 },
];

function lot(no: string, kind: 'work' | 'done' | 'cancelled', extra: Partial<ZakLotOut>): ZakLotOut {
  const status = kind === 'done' ? 'договор заключён' : kind === 'cancelled' ? 'отменён' : 'объявлен';
  return {
    lot_no: no, branch_id: 3, branch_name: 'Каскад Чирчикских ГЭС', date: '2026-08-10', method: 'eshop', method_title: 'Электронный магазин',
    subject: 'Запасные части', status, kind, start_price: 100, contract_price: kind === 'done' ? 90 : null, days: 12, norm_days: 15,
    overdue: false, supplier: kind === 'done' ? 'ООО «Гидромонтаж Сервис»' : null, ...extra,
  };
}

export const LOTS: ZakLotOut[] = [
  lot('2026-0102', 'work', { method: 'contest', method_title: 'Электронный конкурс', start_price: 80, days: 85, norm_days: 40, overdue: true, date: '2026-07-01' }),
  lot('2026-0101', 'done', {}),
  lot('2026-0103', 'done', { method: 'direct', method_title: 'Прямой договор', start_price: 50, contract_price: 50, days: 5, norm_days: 12, branch_id: 2, branch_name: 'Чарвакская ГЭС' }),
  lot('2026-0104', 'work', { status: 'на оценке', start_price: 30, days: 14 }),
  lot('2026-0105', 'cancelled', { method: 'exchange', method_title: 'Биржевые торги', start_price: 40, days: null, norm_days: 20 }),
];

export const ZAK_SVOD: ZakSvodOut = { period: PERIOD_M08_S4, kpis: ZAK_KPIS, months: ZAK_MONTHS, methods: ZAK_METHODS, lots: LOTS };
export const ZAK_LOTY: ZakLotyOut = { period: PERIOD_M08_S4, kpis: ZAK_KPIS, lots: LOTS, truncated: false };
export const ZAK_POSTAVSHIKI: ZakPostavshikiOut = {
  period: PERIOD_M08_S4, kpis: ZAK_KPIS,
  suppliers: [{ name: 'ООО «Гидромонтаж Сервис»', amount: 90, count: 1 }, { name: 'ООО «Энерго Проект»', amount: 50, count: 1 }],
  subjects: [{ name: 'Запасные части', amount: 90, count: 1 }, { name: 'Ремонтные услуги', amount: 50, count: 1 }],
  branches: [
    { branch_id: 3, name: 'Каскад Чирчикских ГЭС', plan: 1000, ytd: 197, execution: 0.197, savings: 10 },
    { branch_id: 2, name: 'Чарвакская ГЭС', plan: 500, ytd: 400, execution: 0.8, savings: 25 },
  ],
};
export const ZAK_EKONOMIYA: ZakEkonomiyaOut = { period: PERIOD_M08_S4, kpis: ZAK_KPIS, methods: ZAK_METHODS, cancelled: [LOTS[4]].filter((x): x is ZakLotOut => x !== undefined) };

export const INV_KPIS: InvKpisOut = {
  has_objects: true, objects: 2, total_cost: 1500, program: 440, plan_to_date: 220, fact_ytd: 180, execution: 0.818182, fact_period: 130,
  lagging: 1, threatened: 0, commissioning: 1, year: 2026,
};

function obj(id: number, code: string, name: string, extra: Partial<InvObjectOut>): InvObjectOut {
  return {
    object_id: id, object_code: code, name, program_code: 'АИП-2026-01', work_type: 'modernization', source_name: 'Бюджетные средства',
    commissioning_year: 2026, total_cost: 1000, branch_id: 3, branch_name: 'Каскад Чирчикских ГЭС', plan_year: 240, plan_to_date: 120,
    fact_ytd: 90, fact_period: 40, execution: 0.75, status: 'lag', financial: 0.49, physical: 0.4, gap_pp: 9, advance: 30, advance_days: 91, ...extra,
  };
}

export const INV_OBJECTS: InvObjectOut[] = [
  obj(11, 'OBJ-01', 'Модернизация гидроагрегатов', {}),
  obj(12, 'OBJ-02', 'Реконструкция водоприёмника', {
    work_type: 'reconstruction', source_name: 'Кредиты МФИ', commissioning_year: 2027, total_cost: 500, plan_year: 200, plan_to_date: 100,
    fact_ytd: 90, fact_period: 90, execution: 0.9, status: 'ok', financial: 0.38, physical: 0.05, gap_pp: 33, advance: 20, advance_days: 113,
  }),
];
export const INV_CUM: InvCumOut[] = Array.from({ length: 12 }, (_, i) => ({ month_id: 202601 + i, plan: [0, 0, 0, 0, 0, 0, 60, 220, 380, 440, 440, 440][i] ?? 0, fact: i < 9 ? [0, 0, 0, 0, 0, 0, 50, 180, 230][i] ?? 0 : null }));
export const INV_SOURCES: InvSourceOut[] = [
  { name: 'Бюджетные средства', plan_year: 240, fact_ytd: 90, share: 0.375 },
  { name: 'Кредиты МФИ', plan_year: 200, fact_ytd: 90, share: 0.45 },
];
export const INV_STAGES: InvObjectStagesOut[] = [{
  object_id: 11, name: 'Модернизация гидроагрегатов', branch_id: 3, late: 2,
  stages: [
    { stage_no: 1, name: 'Проектно-сметная документация', plan_date: '2026-03-15', fact_date: '2026-03-10', done: true, late: false },
    { stage_no: 2, name: 'Тендер и договор', plan_date: '2026-06-15', fact_date: '2026-07-20', done: true, late: true },
    { stage_no: 3, name: 'Строительно-монтажные работы', plan_date: '2026-09-15', fact_date: null, done: false, late: true },
    { stage_no: 4, name: 'Ввод в эксплуатацию', plan_date: '2026-12-15', fact_date: null, done: false, late: false },
  ],
}];
export const INV_SVOD: InvSvodOut = { period: PERIOD_M08_S4, kpis: INV_KPIS, cumulative: INV_CUM, sources: INV_SOURCES, objects: INV_OBJECTS };
export const INV_OBEKTY: InvObektyOut = { period: PERIOD_M08_S4, kpis: INV_KPIS, objects: INV_OBJECTS };
export const INV_ISTOCHNIKI: InvIstochnikiOut = { period: PERIOD_M08_S4, kpis: INV_KPIS, sources: INV_SOURCES, objects: INV_OBJECTS, cumulative: INV_CUM };
export const INV_RISKI: InvRiskiOut = {
  period: PERIOD_M08_S4, kpis: INV_KPIS, lagging: INV_OBJECTS.slice(0, 1), gaps: INV_OBJECTS.slice(1), stages: INV_STAGES, advances: INV_OBJECTS,
};
const NO_OBJECTS: InvKpisOut = { ...INV_KPIS, has_objects: false, objects: 0, program: 0, plan_to_date: 0, fact_ytd: 0, execution: null, fact_period: 0, lagging: 0, commissioning: 0, total_cost: 0 };
export const INV_NONE: InvSvodOut = { period: PERIOD_M08_S4, kpis: NO_OBJECTS, cumulative: INV_CUM.map((p) => ({ ...p, plan: 0, fact: p.fact === null ? null : 0 })), sources: [], objects: [] };

export const HR_KPIS: HrKpisOut = {
  has_data: true, snap_month: 202608, plan: 100, fact: 90, vacancies: 10, vacancy_share: 0.1, fill: 0.9, payroll: 180, outflow: 600,
  payroll_share: 0.3, avg_salary: 2, hired: 3, fired: 3, turnover: 0.033333, overtime: 420, overtime_per_employee: 4.666667, suppressed: false,
};
export const HR_MONTHS: HrMonthOut[] = Array.from({ length: 9 }, (_, i) => ({
  month_id: 202601 + i, payroll: 160 + i * 3, fact: 90, avg_salary: (160 + i * 3) / 90, hired: i % 3, fired: (i + 1) % 3, overtime: 300 + i * 10, suppressed: false,
}));
export const HR_CATEGORIES: HrCategoryOut[] = [{ name: 'Оперативный персонал', value: 81, suppressed: false }, { name: 'Руководители', value: 9, suppressed: false }];
export const HR_BRANCHES: HrBranchOut[] = [
  { branch_id: 3, name: 'Каскад Чирчикских ГЭС', plan: 100, fact: 90, vacancies: 10, fill: 0.9, payroll: 180, avg_salary: 2, hired: 3, fired: 3, turnover: 0.033333, overtime: 420, overtime_per_employee: 4.666667, suppressed: false },
  { branch_id: 2, name: 'Чарвакская ГЭС', plan: 150, fact: 120, vacancies: 30, fill: 0.8, payroll: 250, avg_salary: 2.083333, hired: 1, fired: 12, turnover: 0.1, overtime: 3000, overtime_per_employee: 25, suppressed: false },
];
export const KADRY_SVOD: KadrySvodOut = { period: PERIOD_M08_S4, kpis: HR_KPIS, months: HR_MONTHS, categories: HR_CATEGORIES, branches: HR_BRANCHES };
export const KADRY_CHISL: KadryChislennostOut = { period: PERIOD_M08_S4, kpis: HR_KPIS, branches: HR_BRANCHES, categories: HR_CATEGORIES };
export const KADRY_FOT: KadryFotOut = { period: PERIOD_M08_S4, kpis: HR_KPIS, months: HR_MONTHS, branches: HR_BRANCHES };
export const KADRY_DVIZH: KadryDvizhenieOut = { period: PERIOD_M08_S4, kpis: HR_KPIS, months: HR_MONTHS, branches: [...HR_BRANCHES].reverse() };
const NO_STAFF: HrKpisOut = {
  ...HR_KPIS, has_data: false, snap_month: null, plan: 0, fact: 0, vacancies: null, vacancy_share: null, fill: null, avg_salary: null,
  turnover: null, overtime_per_employee: null,
};
export const KADRY_EMPTY: KadrySvodOut = { period: PERIOD_M08_S4, kpis: NO_STAFF, months: HR_MONTHS, categories: [], branches: [] };
