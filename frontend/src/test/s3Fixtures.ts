import type {
  AgeBucketOut,
  GenMonthOut,
  MapStationOut,
  PowerOut,
  ProdKpisOut,
  ProizvRealizOut,
  ProizvStanciiOut,
  ProizvSvodOut,
  ReportPeriodOut,
  SalesMonthOut,
  SkladMinimumOut,
  SkladNelikvidOut,
  SkladOstatkiOut,
  SkladSvodOut,
  StationGenOut,
  StockBranchOut,
  StockKpisOut,
  StockMonthOut,
  StockPositionOut,
} from '../api/types';

export const PERIOD_M08_S3: ReportPeriodOut = { code: 'm08', label: 'Август 2026', date_from: '2026-08-01', date_to: '2026-08-31', open_last: false };

export const PROD_KPIS: ProdKpisOut = {
  has_data: true, generation: 2400.5, generation_prev: 2200, plan: 2500, execution: 0.9602, capacity_mw: 2027, stations: 15,
  kium: 0.52, own_needs: 36, own_share: 0.015, supply: 2364.5, accrued: 1650000, paid: 1320000, payment_level: 0.8,
};

function station(id: number, name: string, short: string, capacity: number, generation: number, plan: number, accrued: number, paid: number): StationGenOut {
  return {
    branch_id: id, name, short_name: short, capacity_mw: capacity, generation, generation_prev: generation * 0.9, plan,
    execution: generation / plan, kium: (generation * 1000) / (capacity * 744), supply: generation * 0.985, own_share: 0.015,
    accrued, paid, payment_level: paid / accrued,
  };
}

export const STATIONS: StationGenOut[] = [
  station(2, 'Чарвакская ГЭС', 'Чарвак', 666, 310, 300, 210000, 190000),
  station(3, 'Каскад Чирчикских ГЭС', 'Чирчик', 190, 80, 100, 55000, 40000),
  station(4, 'Андижанская ГЭС', 'Андижан', 190, 95, 98, 60000, 57000),
];

export const GEN_MONTHS: GenMonthOut[] = Array.from({ length: 9 }, (_, i) => ({ month_id: 202601 + i, generation: 200 + i * 20, plan: 210 + i * 20, generation_prev: 190 + i * 18 }));
export const SALES_MONTHS: SalesMonthOut[] = Array.from({ length: 9 }, (_, i) => ({ month_id: 202601 + i, accrued: 150000 + i * 5000, paid: 120000 + i * 4000 }));

export const MAP: MapStationOut[] = [
  { branch_id: 1, code: 'UGE-01', name: 'АО «Узбекгидроэнерго»', short_name: 'Узбекгидроэнерго', kind: 'head', capacity_mw: null, lat: 41.3111, lon: 69.2797, production: null },
  { branch_id: 2, code: 'UGE-02', name: 'Чарвакская ГЭС', short_name: 'Чарвак', kind: 'ges', capacity_mw: 666, lat: 41.626, lon: 70.029, production: { generation: 310, plan: 300, execution: 310 / 300, kium: 0.63, payment_level: 0.905 } },
  { branch_id: 3, code: 'UGE-03', name: 'Каскад Чирчикских ГЭС', short_name: 'Чирчик', kind: 'cascade', capacity_mw: 190, lat: 41.47, lon: 69.58, production: { generation: 80, plan: 100, execution: 0.8, kium: 0.57, payment_level: 0.727 } },
];

export const PROIZV_SVOD: ProizvSvodOut = { period: PERIOD_M08_S3, has_stations: true, kpis: PROD_KPIS, months: GEN_MONTHS, stations: STATIONS, map: MAP };
export const PROIZV_STANCII: ProizvStanciiOut = { period: PERIOD_M08_S3, has_stations: true, kpis: PROD_KPIS, stations: STATIONS };
export const PROIZV_REALIZ: ProizvRealizOut = {
  period: PERIOD_M08_S3, has_stations: true, kpis: PROD_KPIS, months: SALES_MONTHS,
  stations: [STATIONS[1], STATIONS[0], STATIONS[2]].filter((s): s is StationGenOut => s !== undefined),
};
export const PROIZV_HQ: ProizvStanciiOut = { period: PERIOD_M08_S3, has_stations: false, kpis: { ...PROD_KPIS, has_data: false }, stations: [] };

export const POWER: PowerOut = {
  has_source: true, snap_at: '2026-09-25T05:40:00Z', source_date: '25.09.2026 10:40', stale: false, total_mw: 412.5,
  units_working: 5, units_reserve: 1, units_repair: 1,
  stations: [
    { branch_id: 2, branch_name: 'Чарвакская ГЭС', station: 'CHARVAK-1', station_name: 'Chorvoq GES', cascade_name: 'Чирчик-Бозсу', power_mw: 380.5, units_working: 3, units_reserve: 1, units_repair: 0 },
    { branch_id: 3, branch_name: 'Каскад Чирчикских ГЭС', station: 'CHIRCHIQ-7', station_name: 'Chirchiq GES-7', cascade_name: 'Чирчик-Бозсу', power_mw: 32, units_working: 2, units_reserve: 0, units_repair: 1 },
  ],
};
export const POWER_STALE: PowerOut = { ...POWER, stale: true };
export const POWER_NONE: PowerOut = { has_source: false, snap_at: null, source_date: null, stale: false, total_mw: 0, units_working: 0, units_reserve: 0, units_repair: 0, stations: [] };

export const STOCK_KPIS: StockKpisOut = {
  as_of: '2026-08-31', has_data: true, value: 120, turnover_days: 26.6, positions: 3, below_min: 1, has_minimum: true,
  idle_value: 80, idle_share: 0.6667, has_age: true, inflow: 100, outflow: 140,
};
export const STOCK_MONTHS: StockMonthOut[] = Array.from({ length: 9 }, (_, i) => ({ month_id: 202601 + i, inflow: 90 + i, outflow: 95 + i }));
export const CATEGORIES = [{ name: 'Запасные части', amount: 100 }, { name: 'Масла и ГСМ', amount: 20 }];

function position(nom: string, name: string, unit: string, qty: number, min: number | null, value: number, age: number | null, branchId = 3): StockPositionOut {
  return {
    branch_id: branchId, branch_name: branchId === 3 ? 'Каскад Чирчикских ГЭС' : 'Чарвакская ГЭС', warehouse: 'Склад Чирчик', nom_code: nom, name,
    category: 'Запасные части', unit, qty, min_qty: min, coverage: min ? qty / min : null, value, age_days: age,
  };
}

export const BELOW: StockPositionOut[] = [position('NOM-001', 'Подшипник SKF 23140', 'шт', 4, 10, 192, 11)];
export const IDLE: StockPositionOut[] = [
  position('NOM-004', 'Задвижка DN200', 'шт', 2, null, 56, 456, 2),
  position('NOM-010', 'Трансформаторное масло ГК', 'л', 500, 100, 19, 233),
];
export const STOCK_BRANCHES: StockBranchOut[] = [
  { branch_id: 2, name: 'Чарвакская ГЭС', value: 80, positions: 10, below_min: 2, idle_value: 30 },
  { branch_id: 3, name: 'Каскад Чирчикских ГЭС', value: 40, positions: 8, below_min: 0, idle_value: 5 },
];
export const AGES: AgeBucketOut[] = [
  { key: 'le90', value: 40 }, { key: 'd91_180', value: 0 }, { key: 'd181_365', value: 20 }, { key: 'gt365', value: 60 }, { key: 'unknown', value: 0 },
];

export const SKLAD_SVOD: SkladSvodOut = { period: PERIOD_M08_S3, kpis: STOCK_KPIS, months: STOCK_MONTHS, categories: CATEGORIES, below: BELOW };
export const SKLAD_OSTATKI: SkladOstatkiOut = { period: PERIOD_M08_S3, kpis: STOCK_KPIS, branches: STOCK_BRANCHES, categories: CATEGORIES };
export const SKLAD_MINIMUM: SkladMinimumOut = { period: PERIOD_M08_S3, kpis: STOCK_KPIS, below: BELOW };
export const SKLAD_NELIKVID: SkladNelikvidOut = { period: PERIOD_M08_S3, kpis: STOCK_KPIS, ages: AGES, illiquid: IDLE };
const NO_SOURCE_KPIS: StockKpisOut = { ...STOCK_KPIS, below_min: 0, has_minimum: false, idle_value: 0, idle_share: null, has_age: false };
export const SKLAD_NO_MIN: SkladMinimumOut = { period: PERIOD_M08_S3, kpis: NO_SOURCE_KPIS, below: [] };
export const SKLAD_NO_AGE: SkladNelikvidOut = {
  period: PERIOD_M08_S3, kpis: NO_SOURCE_KPIS, ages: AGES.map((a) => ({ ...a, value: a.key === 'unknown' ? 120 : 0 })), illiquid: [],
};
