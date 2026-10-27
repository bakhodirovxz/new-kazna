import { screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { expectNoAxeViolations } from '../../test/axe';
import { ME_ADMIN } from '../../test/fixtures';
import { json, mockApi } from '../../test/mockApi';
import { renderWithProviders } from '../../test/render';
import { CASH_KPIS, EXCEL, FLOW_IN, FLOW_OUT, SVOD } from '../../test/s1Fixtures';
import ObzorExcel from './excel';
import ObzorPostup from './postup';
import ObzorRasxod from './rasxod';
import ObzorSvod from './svod';

const filters = { br: null, per: 'm08' };
const EMPTY_KPIS = { ...CASH_KPIS, has_data: false, opening: null, closing: null, diff: null };
const NO_DATA = 'Нет данных за выбранный период. Выберите другой период или филиал в фильтрах.';

describe('empty states (has_data = false)', () => {
  it('Поступления: «—» with a reason instead of zeros, no YoY', async () => {
    mockApi({ 'GET /obzor/postup': json({ ...FLOW_IN, kpis: EMPTY_KPIS, items: [], banks: [], branches: [] }), 'GET /auth/me': json(ME_ADMIN) });
    const { container } = renderWithProviders(<ObzorPostup section="obzor" page="postup" filters={filters} onBranch={vi.fn()} />);
    expect(await screen.findAllByText(NO_DATA)).not.toHaveLength(0);
    expect(screen.getAllByText('нет данных').length).toBe(6);
    expect(screen.queryByText(/к 2025/)).toBeNull();
    expect(screen.getAllByText('за период нет движения средств').length).toBe(3);
    await expectNoAxeViolations(container);
  });

  it('Расходование: empty activity split and rankings show the reason', async () => {
    mockApi({ 'GET /obzor/rasxod': json({ ...FLOW_OUT, kpis: EMPTY_KPIS, items: [], banks: [], branches: [], activity: [{ activity: 'operating', amount: 0 }] }), 'GET /auth/me': json(ME_ADMIN) });
    const { container } = renderWithProviders(<ObzorRasxod section="obzor" page="rasxod" filters={filters} onBranch={vi.fn()} />);
    expect(await screen.findAllByText(NO_DATA)).not.toHaveLength(0);
    expect(screen.queryByText(/0,0 млн/)).toBeNull();
    await expectNoAxeViolations(container);
  });

  it('Таблица Excel: KPI reason and a «no data» detail note, not «nothing found»', async () => {
    mockApi({ 'GET /obzor/excel': json({ ...EXCEL, kpis: EMPTY_KPIS, detail: [] }), 'GET /auth/me': json(ME_ADMIN) });
    renderWithProviders(<ObzorExcel section="obzor" page="excel" filters={filters} onBranch={vi.fn()} />);
    expect(await screen.findAllByText(NO_DATA)).not.toHaveLength(0);
    expect(screen.getByText('Нет данных по статьям за выбранный период.')).toBeInTheDocument();
    expect(screen.queryByText('Ничего не найдено. Измените условия поиска.')).toBeNull();
  });
});

describe('KPI year-over-year', () => {
  it('colours only the delta, treats lower spending as good and has no YoY on Разница', async () => {
    const kpis = { ...CASH_KPIS, outflow: 60, outflow_prev: 50, diff: 5, diff_prev: 4, net: 60, net_prev: 30 };
    mockApi({ 'GET /obzor/svod': json({ ...SVOD, kpis }), 'GET /auth/me': json(ME_ADMIN) });
    renderWithProviders(<ObzorSvod section="obzor" page="svod" filters={filters} onBranch={vi.fn()} />);
    const bad = await screen.findByText('к 2025: +20,0%');
    expect(bad).toHaveClass('yoy--bad'); // трат больше, чем год назад
    expect(screen.getByText('к 2025: +25,0%')).toHaveClass('yoy--good');
    expect(bad.parentElement?.textContent).toContain('за период');
    expect(bad.parentElement).not.toHaveClass('yoy--bad');
    expect(screen.getAllByText(/к 2025/)).toHaveLength(4); // Начальный остаток (нет прошлого года) и Разница — без YoY
    expect(screen.getByText('+5,0')).toBeInTheDocument(); // знак «+»
  });

  it('lower spending than last year is green', async () => {
    mockApi({ 'GET /obzor/svod': json(SVOD), 'GET /auth/me': json(ME_ADMIN) });
    renderWithProviders(<ObzorSvod section="obzor" page="svod" filters={filters} onBranch={vi.fn()} />);
    expect(await screen.findByText('к 2025: −20,0%')).toHaveClass('yoy--good');
  });
});

describe('card header', () => {
  it('keeps the export buttons in the header flow, next to the card actions', async () => {
    mockApi({ 'GET /obzor/excel': json(EXCEL), 'GET /auth/me': json(ME_ADMIN) });
    renderWithProviders(<ObzorExcel section="obzor" page="excel" filters={filters} onBranch={vi.fn()} />);
    const detail = (await screen.findByRole('table', { name: 'Детализация по статьям' })).closest('section') as HTMLElement;
    const head = detail.querySelector('.card__head') as HTMLElement;
    expect(within(head).getByRole('searchbox')).toBeInTheDocument();
    expect(head.querySelector('.card__actions .card__exp')).not.toBeNull();
    // числовые колонки справа, текстовые слева
    expect(within(detail).getAllByRole('columnheader')[0]).toHaveClass('l');
  });
});
