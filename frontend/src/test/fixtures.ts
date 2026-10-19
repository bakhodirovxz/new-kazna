import type { BranchOut, FreshnessOut, MeOut, MenuOut, MenuSectionOut, PeriodsOut } from '../api/types';
import { json, type MockHandler } from './mockApi';

const SECTION_IDS = ['obzor', 'kazna', 'kredity', 'finmodel', 'zakupki', 'sklad', 'proizvodstvo', 'investicii', 'kadry'];

export const ALL_PERMISSIONS = [
  ...SECTION_IDS.map((id) => `section:${id}:view`),
  'export:csv',
  'export:xlsx',
  'admin:users',
  'admin:roles',
  'admin:settings',
  'admin:etl',
  'admin:keys',
  'audit:read',
];

export const ME_ADMIN: MeOut = {
  id: 1,
  username: 'admin',
  full_name: 'Азимов Бахтиёр',
  role_code: 'admin',
  permissions: ALL_PERMISSIONS,
  branch_ids: null,
  must_change_password: false,
};

export const ME_BRANCH: MeOut = {
  id: 7,
  username: 'econ3',
  full_name: 'Каримова Нилуфар',
  role_code: 'economist_filiala',
  permissions: ['section:obzor:view', 'section:kazna:view', 'section:proizvodstvo:view', 'section:sklad:view', 'section:kadry:view', 'export:csv', 'export:xlsx'],
  branch_ids: [3],
  must_change_password: false,
};

export const ME_AUDITOR: MeOut = {
  id: 9,
  username: 'audit',
  full_name: 'Рахимов Ильхом',
  role_code: 'vnutr_kontrol',
  permissions: ['section:obzor:view', 'audit:read'],
  branch_ids: null,
  must_change_password: false,
};

const SVOD = { id: 'svod', title: 'Сводка' };
const SECTIONS: Record<string, MenuSectionOut> = {
  obzor: {
    id: 'obzor',
    title: 'Обзор',
    pages: [SVOD, { id: 'vnimanie', title: 'Требует внимания' }, { id: 'postup', title: 'Поступления' }, { id: 'rasxod', title: 'Расходование' }, { id: 'excel', title: 'Таблица Excel' }],
  },
  kazna: {
    id: 'kazna',
    title: 'Казначейство',
    pages: [SVOD, { id: 'platezhi', title: 'Исполнение платежей' }, { id: 'calendar', title: 'Платёжный календарь' }, { id: 'dogovory', title: 'Договоры и задолженность' }, { id: 'celevye', title: 'Целевые средства' }],
  },
  kredity: { id: 'kredity', title: 'Кредиты', pages: [SVOD, { id: 'reestr', title: 'Реестр кредитов' }, { id: 'grafik', title: 'График платежей' }] },
  finmodel: { id: 'finmodel', title: 'Финмодель', pages: [SVOD, { id: 'dohody', title: 'Доходы и расходы' }, { id: 'dolg', title: 'Инвестиции и долг' }, { id: 'scenarii', title: 'Сценарии' }] },
  zakupki: { id: 'zakupki', title: 'Закупки', pages: [SVOD, { id: 'loty', title: 'Лоты' }, { id: 'postavshiki', title: 'Договоры и поставщики' }, { id: 'ekonomiya', title: 'Экономия' }] },
  sklad: { id: 'sklad', title: 'Склад', pages: [SVOD, { id: 'ostatki', title: 'Остатки по складам' }, { id: 'minimum', title: 'Минимальный запас' }, { id: 'nelikvid', title: 'Неликвиды' }] },
  proizvodstvo: { id: 'proizvodstvo', title: 'Производство', pages: [SVOD, { id: 'stancii', title: 'Выработка по станциям' }, { id: 'realiz', title: 'Реализация' }] },
  investicii: { id: 'investicii', title: 'Инвестиции', pages: [SVOD, { id: 'obekty', title: 'Объекты' }, { id: 'istochniki', title: 'Источники и освоение' }, { id: 'riski', title: 'Сроки и риски' }] },
  kadry: { id: 'kadry', title: 'Кадры', pages: [SVOD, { id: 'chislennost', title: 'Численность' }, { id: 'fot', title: 'Оплата труда' }, { id: 'dvizhenie', title: 'Движение кадров' }] },
};

function menu(groups: Array<[string | null, string[]]>): MenuOut {
  return {
    groups: groups.map(([title, ids]) => ({ title, sections: ids.map((id) => SECTIONS[id] as MenuSectionOut) })),
  };
}

export const MENU_FULL = menu([
  [null, ['obzor']],
  ['Финансы', ['kazna', 'kredity', 'finmodel']],
  ['Обеспечение', ['zakupki', 'sklad']],
  ['Производство', ['proizvodstvo', 'investicii']],
  ['Персонал', ['kadry']],
]);

export const MENU_BRANCH = menu([
  [null, ['obzor']],
  ['Финансы', ['kazna']],
  ['Обеспечение', ['sklad']],
  ['Производство', ['proizvodstvo']],
  ['Персонал', ['kadry']],
]);

export const MENU_AUDITOR = menu([[null, ['obzor']]]);

export const BRANCHES: BranchOut[] = [
  { id: 1, code: 'HQ', name: 'АО «Узбекгидроэнерго»', short_name: 'Головная', kind: 'head', is_hq: true, capacity_mw: null, lat: 41.31, lon: 69.28 },
  { id: 2, code: 'CHARVAK', name: 'Чарвакская ГЭС', short_name: 'Чарвак', kind: 'ges', is_hq: false, capacity_mw: 666, lat: 41.63, lon: 70.02 },
  { id: 3, code: 'CHIRCHIK', name: 'Каскад Чирчикских ГЭС', short_name: 'Чирчик', kind: 'cascade', is_hq: false, capacity_mw: 190, lat: 41.47, lon: 69.58 },
  { id: 4, code: 'ANDIJAN', name: 'Андижанская ГЭС', short_name: 'Андижан', kind: 'ges', is_hq: false, capacity_mw: 190, lat: 40.76, lon: 72.99 },
];

export const PERIODS: PeriodsOut = {
  default: 'ytd',
  today: '2026-09-24',
  items: [
    { code: 'ytd', kind: 'ytd', label: 'Январь – сентябрь 2026', date_from: '2026-01-01', date_to: '2026-09-24' },
    { code: 'q1', kind: 'quarter', label: 'I квартал 2026', date_from: '2026-01-01', date_to: '2026-03-31' },
    { code: 'q2', kind: 'quarter', label: 'II квартал 2026', date_from: '2026-04-01', date_to: '2026-06-30' },
    { code: 'q3', kind: 'quarter', label: 'III квартал 2026', date_from: '2026-07-01', date_to: '2026-09-24' },
    { code: 'm01', kind: 'month', label: 'Январь 2026', date_from: '2026-01-01', date_to: '2026-01-31' },
    { code: 'm05', kind: 'month', label: 'Май 2026', date_from: '2026-05-01', date_to: '2026-05-31' },
    { code: 'm09', kind: 'month', label: 'Сентябрь 2026', date_from: '2026-09-01', date_to: '2026-09-24' },
  ],
};

export const FRESH_OK: FreshnessOut = { last_success_at: '2026-09-24T05:10:00Z', stale: false, max_age_hours: 6, active_build_id: 12 };
export const FRESH_STALE: FreshnessOut = { last_success_at: '2026-09-23T20:00:00Z', stale: true, max_age_hours: 6, active_build_id: 11 };

/** Qobiq uchun kerakli barcha GET'lar (me, menyu, filiallar RLS bo'yicha, davrlar, freshness). */
export function shellRoutes(me: MeOut = ME_ADMIN, menuOut: MenuOut = MENU_FULL): Record<string, MockHandler> {
  const scope = me.branch_ids;
  return {
    'GET /auth/me': json(me),
    'GET /meta/menu': json(menuOut),
    'GET /meta/branches': json(scope === null ? BRANCHES : BRANCHES.filter((b) => scope.includes(b.id))),
    'GET /meta/periods': json(PERIODS),
    'GET /meta/freshness': json(FRESH_OK),
  };
}
