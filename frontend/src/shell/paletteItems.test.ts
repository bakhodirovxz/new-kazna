import { describe, expect, it } from 'vitest';
import { BRANCHES, ME_ADMIN, ME_AUDITOR, MENU_AUDITOR, MENU_FULL, PERIODS } from '../test/fixtures';
import { buildPaletteItems, filterPalette } from './paletteItems';

const base = {
  menu: MENU_FULL,
  permissions: ME_ADMIN.permissions,
  branches: BRANCHES,
  periods: PERIODS.items,
  defaultPeriod: 'ytd',
  locked: false,
  route: { kind: 'section', section: 'kazna', page: 'platezhi', br: 2, per: 'q1' } as const,
};

describe('buildPaletteItems', () => {
  it('lists pages with current filters, admin pages, account, branches and periods', () => {
    const items = buildPaletteItems(base);
    expect(items.find((i) => i.label === 'Кредиты: Реестр кредитов')?.target).toEqual({
      kind: 'section', section: 'kredity', page: 'reestr', br: 2, per: 'q1',
    });
    expect(items.find((i) => i.label === 'Андижанская ГЭС')?.target).toEqual({
      kind: 'section', section: 'kazna', page: 'platezhi', br: 4, per: 'q1',
    });
    expect(items.find((i) => i.label === 'Все филиалы')?.target).toMatchObject({ br: null });
    expect(items.find((i) => i.label === 'Январь – сентябрь 2026')?.target).toMatchObject({ per: null, br: 2 });
    expect(items.find((i) => i.label === 'Администрирование: Журнал аудита')?.target).toEqual({ kind: 'admin', page: 'audit' });
    expect(items.find((i) => i.label === 'Мои сеансы')?.target).toEqual({ kind: 'sessions' });
  });

  it('hides branches for a locked user and admin pages without permissions', () => {
    const items = buildPaletteItems({ ...base, menu: MENU_AUDITOR, permissions: ['section:obzor:view'], locked: true, route: { kind: 'admin', page: null } });
    expect(items.some((i) => i.kind === 'branch')).toBe(false);
    expect(items.some((i) => i.kind === 'admin')).toBe(false);
    expect(items.find((i) => i.kind === 'period')?.target).toMatchObject({ kind: 'section', section: 'obzor', page: 'svod' });
  });

  it('shows only the audit page to internal control', () => {
    const items = buildPaletteItems({ ...base, menu: MENU_AUDITOR, permissions: ME_AUDITOR.permissions });
    expect(items.filter((i) => i.kind === 'admin').map((i) => i.label)).toEqual(['Администрирование: Журнал аудита']);
  });
});

it('filters case-insensitively and treats ё as е', () => {
  const items = buildPaletteItems(base);
  expect(filterPalette(items, 'ПЛАТЁЖНЫЙ').map((i) => i.label)).toEqual(['Казначейство: Платёжный календарь']);
  expect(filterPalette(items, '').length).toBeLessThanOrEqual(50);
});
