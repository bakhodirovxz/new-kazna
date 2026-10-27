import { screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { expectNoAxeViolations } from '../../test/axe';
import { ME_ADMIN } from '../../test/fixtures';
import { apiError, json, mockApi } from '../../test/mockApi';
import { renderWithProviders } from '../../test/render';
import { ITEM_BRANCHES, SVOD } from '../../test/s1Fixtures';
import ObzorSvod from './svod';

const filters = { br: null, per: 'm08' };

describe('Обзор / Сводка', () => {
  it('shows six KPIs with YoY and formula hints, comparison, map and rankings', async () => {
    mockApi({ 'GET /obzor/svod': json(SVOD), 'GET /auth/me': json(ME_ADMIN) });
    const { container } = renderWithProviders(<ObzorSvod section="obzor" page="svod" filters={filters} onBranch={vi.fn()} />);
    expect(await screen.findByText('Начальный остаток')).toBeInTheDocument();
    for (const label of ['Поступления', 'Расходование', 'Чистый денежный поток', 'Конечный остаток', 'Разница']) {
      expect(screen.getAllByText(label).length).toBeGreaterThan(0);
    }
    expect(screen.getByText(/к 2025: \+25,0%/)).toBeInTheDocument();
    expect(screen.getByText(/Разница = конечный остаток − \(начальный остаток \+ ЧДП\)/)).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Сравнение с 2025 годом' })).toBeInTheDocument();
    expect(screen.getByRole('group', { name: 'Карта Узбекистана с расположением ГЭС' })).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Движение денежных средств по месяцам' })).toBeInTheDocument();
    await expectNoAxeViolations(container);
  });

  it('selects a branch from the ranking and opens an item breakdown', async () => {
    const onBranch = vi.fn();
    mockApi({ 'GET /obzor/svod': json(SVOD), 'GET /auth/me': json(ME_ADMIN), 'GET /obzor/items/22': json(ITEM_BRANCHES) });
    const { user } = renderWithProviders(<ObzorSvod section="obzor" page="svod" filters={filters} onBranch={onBranch} />);
    const ranking = await screen.findByRole('list', { name: 'Расходование по филиалам' });
    await user.click(within(ranking).getByRole('button', { name: /Чарвакская ГЭС/ }));
    expect(onBranch).toHaveBeenCalledWith(2);
    const top = screen.getByRole('list', { name: 'Топ-5 статей расходования' });
    await user.click(within(top).getByRole('button', { name: /Прочие операционные расходы/ }));
    const dialog = await screen.findByRole('dialog', { name: 'Прочие операционные расходы' });
    expect(await within(dialog).findByText('Каскад Чирчикских ГЭС')).toBeInTheDocument();
  });

  it('shows the error banner with retry', async () => {
    mockApi({ 'GET /obzor/svod': apiError(500, 'internal_error', 'Внутренняя ошибка сервера'), 'GET /auth/me': json(ME_ADMIN) });
    renderWithProviders(<ObzorSvod section="obzor" page="svod" filters={filters} onBranch={vi.fn()} />);
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Повторить' })).toBeInTheDocument();
  });

  it('shows no-data states when the period is empty and balances are missing', async () => {
    const empty = { ...SVOD, kpis: { ...SVOD.kpis, has_data: false, opening: null, closing: null, diff: null } };
    mockApi({ 'GET /obzor/svod': json(empty), 'GET /auth/me': json(ME_ADMIN) });
    renderWithProviders(<ObzorSvod section="obzor" page="svod" filters={filters} onBranch={vi.fn()} />);
    expect(await screen.findByText('Нет данных за выбранный период. Выберите другой период или филиал в фильтрах.')).toBeInTheDocument();
    expect(screen.getAllByText('нет данных').length).toBeGreaterThanOrEqual(3);
  });
});
