import { screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { expectNoAxeViolations } from '../../test/axe';
import { ME_ADMIN } from '../../test/fixtures';
import { json, mockApi } from '../../test/mockApi';
import { renderWithProviders } from '../../test/render';
import { SKLAD_MINIMUM, SKLAD_NELIKVID, SKLAD_NO_AGE, SKLAD_NO_MIN, SKLAD_OSTATKI, SKLAD_SVOD } from '../../test/s3Fixtures';
import SkladMinimum from './minimum';
import SkladNelikvid from './nelikvid';
import SkladOstatki from './ostatki';
import SkladSvod from './svod';

const filters = { br: null, per: 'm08' };

describe('Склад', () => {
  it('Сводка: KPIs, movement chart, categories and top deficit positions', async () => {
    mockApi({ 'GET /sklad/svod': json(SKLAD_SVOD), 'GET /auth/me': json(ME_ADMIN) });
    const { container } = renderWithProviders(<SkladSvod section="sklad" page="svod" filters={filters} onBranch={vi.fn()} />);
    expect(await screen.findByText('Стоимость запасов')).toBeInTheDocument();
    expect(screen.getByText('27')).toBeInTheDocument();
    expect(screen.getByText('66,7%')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Движение запасов по месяцам' })).toBeInTheDocument();
    expect(within(screen.getByRole('list', { name: 'Запасы по категориям' })).getByText('Запасные части')).toBeInTheDocument();
    const below = screen.getByRole('table', { name: 'Ниже минимального запаса' });
    expect(within(below).getAllByRole('row')).toHaveLength(1 + 1);
    expect(screen.getByRole('link', { name: 'Все позиции' }).getAttribute('href')).toContain('sklad/minimum');
    await expectNoAxeViolations(container);
  });

  it('Остатки по складам: branches table selects a branch', async () => {
    const onBranch = vi.fn();
    mockApi({ 'GET /sklad/ostatki': json(SKLAD_OSTATKI), 'GET /auth/me': json(ME_ADMIN) });
    const { user } = renderWithProviders(<SkladOstatki section="sklad" page="ostatki" filters={filters} onBranch={onBranch} />);
    const table = await screen.findByRole('table', { name: 'Склады' });
    expect(within(table).getAllByRole('row')).toHaveLength(1 + 2);
    await user.click(within(table).getByText('Каскад Чирчикских ГЭС'));
    expect(onBranch).toHaveBeenCalledWith(3);
    expect(screen.getByRole('list', { name: 'Запасы по категориям' })).toBeInTheDocument();
  });

  it('Минимальный запас: coverage bar and missing minimum data', async () => {
    mockApi({ 'GET /sklad/minimum': json(SKLAD_MINIMUM), 'GET /auth/me': json(ME_ADMIN) });
    const { unmount } = renderWithProviders(<SkladMinimum section="sklad" page="minimum" filters={filters} onBranch={vi.fn()} />);
    const table = await screen.findByRole('table', { name: 'Ниже минимального запаса' });
    expect(within(table).getByText('40%').closest('.exec')).toHaveClass('neg');
    expect(within(table).getByText('4 шт')).toBeInTheDocument();
    unmount();
    mockApi({ 'GET /sklad/minimum': json(SKLAD_NO_MIN), 'GET /auth/me': json(ME_ADMIN) });
    renderWithProviders(<SkladMinimum section="sklad" page="minimum" filters={filters} onBranch={vi.fn()} />);
    expect(await screen.findByText(/Источник данных не подключён: минимальный запас \(1С\)/)).toBeInTheDocument();
    expect(screen.getAllByText('нет данных в 1С').length).toBeGreaterThan(0);
  });

  it('Неликвиды: age buckets, idle list and missing movement dates', async () => {
    mockApi({ 'GET /sklad/nelikvid': json(SKLAD_NELIKVID), 'GET /auth/me': json(ME_ADMIN) });
    const { unmount } = renderWithProviders(<SkladNelikvid section="sklad" page="nelikvid" filters={filters} onBranch={vi.fn()} />);
    const ages = await screen.findByRole('list', { name: 'Возраст запасов' });
    expect(within(ages).getByText('более 365 дней')).toBeInTheDocument();
    expect(within(ages).queryByText('нет даты движения')).toBeNull();
    const table = screen.getByRole('table', { name: 'Без движения более 180 дней' });
    expect(within(table).getByText('456 дн.')).toBeInTheDocument();
    unmount();
    mockApi({ 'GET /sklad/nelikvid': json(SKLAD_NO_AGE), 'GET /auth/me': json(ME_ADMIN) });
    renderWithProviders(<SkladNelikvid section="sklad" page="nelikvid" filters={filters} onBranch={vi.fn()} />);
    expect(await screen.findAllByText(/Источник данных не подключён: дата последнего движения \(1С\)/)).toHaveLength(2);
  });
});
