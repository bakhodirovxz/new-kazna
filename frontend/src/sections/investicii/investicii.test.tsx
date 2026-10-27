import { screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { expectNoAxeViolations } from '../../test/axe';
import { ME_ADMIN } from '../../test/fixtures';
import { json, mockApi } from '../../test/mockApi';
import { renderWithProviders } from '../../test/render';
import { INV_ISTOCHNIKI, INV_NONE, INV_OBEKTY, INV_RISKI, INV_SVOD } from '../../test/s4Fixtures';
import InvesticiiIstochniki from './istochniki';
import InvesticiiObekty from './obekty';
import InvesticiiRiski from './riski';
import InvesticiiSvod from './svod';

const filters = { br: null, per: 'm08' };

describe('Инвестиции', () => {
  it('Сводка: KPIs, cumulative chart, sources and the object registry', async () => {
    mockApi({ 'GET /investicii/svod': json(INV_SVOD), 'GET /auth/me': json(ME_ADMIN) });
    const { container } = renderWithProviders(<InvesticiiSvod section="investicii" page="svod" filters={filters} onBranch={vi.fn()} />);
    expect(await screen.findByText('Программа 2026')).toBeInTheDocument();
    expect(screen.getByText('81,8%')).toHaveClass('neg');
    expect(screen.getByRole('img', { name: 'Освоение нарастающим итогом' })).toBeInTheDocument();
    expect(screen.getByText('Кредиты МФИ')).toBeInTheDocument();
    const table = screen.getByRole('table', { name: 'Объекты программы' });
    expect(within(table).getAllByRole('row')).toHaveLength(1 + 2);
    expect(within(table).getByText('75%, отстаёт')).toHaveClass('badge--warn');
    expect(within(table).getByText('физ. 5%')).toHaveClass('neg');
    expect(screen.getByRole('link', { name: 'Все объекты' }).getAttribute('href')).toContain('investicii/obekty');
    await expectNoAxeViolations(container);
  });

  it('Сводка: branch without objects shows the explanation', async () => {
    mockApi({ 'GET /investicii/svod': json(INV_NONE), 'GET /auth/me': json(ME_ADMIN) });
    renderWithProviders(<InvesticiiSvod section="investicii" page="svod" filters={{ br: 1, per: 'm08' }} onBranch={vi.fn()} />);
    expect(await screen.findByText('У выбранного филиала нет объектов адресной программы.')).toBeInTheDocument();
    expect(screen.queryByRole('img', { name: 'Освоение нарастающим итогом' })).toBeNull();
  });

  it('Объекты: full registry, row click selects the branch', async () => {
    const onBranch = vi.fn();
    mockApi({ 'GET /investicii/obekty': json(INV_OBEKTY), 'GET /auth/me': json(ME_ADMIN) });
    const { user } = renderWithProviders(<InvesticiiObekty section="investicii" page="obekty" filters={filters} onBranch={onBranch} />);
    const table = await screen.findByRole('table', { name: 'Реестр объектов' });
    await user.click(within(table).getByText('Реконструкция водоприёмника'));
    expect(onBranch).toHaveBeenCalledWith(3);
    expect(screen.queryByRole('link', { name: 'Все объекты' })).toBeNull();
  });

  it('Источники и освоение: sources, objects rank with plan mark, cumulative chart', async () => {
    mockApi({ 'GET /investicii/istochniki': json(INV_ISTOCHNIKI), 'GET /auth/me': json(ME_ADMIN) });
    renderWithProviders(<InvesticiiIstochniki section="investicii" page="istochniki" filters={filters} onBranch={vi.fn()} />);
    const rank = await screen.findByRole('list', { name: 'Освоение по объектам' });
    const items = within(rank).getAllByRole('listitem');
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent('38% годового плана');
    expect(screen.getByRole('img', { name: 'Освоение нарастающим итогом' })).toBeInTheDocument();
  });

  it('Сроки и риски: lagging, gaps, stages strip and old advances', async () => {
    mockApi({ 'GET /investicii/riski': json(INV_RISKI), 'GET /auth/me': json(ME_ADMIN) });
    const { container } = renderWithProviders(<InvesticiiRiski section="investicii" page="riski" filters={filters} onBranch={vi.fn()} />);
    const lagging = await screen.findByRole('list', { name: 'Объекты с отставанием' });
    expect(within(lagging).getByText('75% графика')).toBeInTheDocument();
    expect(within(screen.getByRole('list', { name: 'Разрыв финансирования и физического выполнения' })).getByText('33 п.п.')).toBeInTheDocument();
    expect(container.querySelectorAll('.stg span')).toHaveLength(4);
    expect(container.querySelectorAll('.stg span.is-late')).toHaveLength(1);
    expect(screen.getByText('этапов с отставанием: 2')).toBeInTheDocument();
    expect(screen.getByText('Строительно-монтажные работы')).toBeInTheDocument();
    const advances = screen.getByRole('table', { name: 'Незакрытые авансы' });
    expect(within(advances).getAllByRole('row')).toHaveLength(1 + 2);
    expect(within(advances).getByText('113 дн.')).toHaveClass('badge--neg');
    await expectNoAxeViolations(container);
  });
});
