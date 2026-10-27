import { screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { expectNoAxeViolations } from '../../test/axe';
import { ME_ADMIN } from '../../test/fixtures';
import { json, mockApi } from '../../test/mockApi';
import { renderWithProviders } from '../../test/render';
import { KREDITY_EMPTY_GRAFIK, KREDITY_GRAFIK, KREDITY_REESTR, KREDITY_SVOD } from '../../test/s2Fixtures';
import KredityGrafik from './grafik';
import KredityReestr from './reestr';
import KreditySvod from './svod';

const filters = { br: null, per: 'm08' };

describe('Кредиты', () => {
  it('Сводка: KPIs, schedule, currency structure, five payments and DSCR', async () => {
    mockApi({ 'GET /kredity/svod': json(KREDITY_SVOD), 'GET /auth/me': json(ME_ADMIN) });
    const { container } = renderWithProviders(<KreditySvod section="kredity" page="svod" filters={filters} onBranch={vi.fn()} />);
    expect(await screen.findByText('Кредитный портфель')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'График погашения' })).toBeInTheDocument();
    const currencies = screen.getByRole('list', { name: 'Валютная структура' });
    expect(within(currencies).getByText('Доллар США (USD)')).toBeInTheDocument();
    const upcoming = screen.getByRole('table', { name: 'Ближайшие платежи' });
    expect(within(upcoming).getAllByRole('row')).toHaveLength(1 + 5);
    expect(screen.getByRole('heading', { name: 'Покрытие обслуживания долга (DSCR)' })).toBeInTheDocument();
    await expectNoAxeViolations(container);
  });

  it('Реестр: registry, creditors and currencies; row click selects the branch', async () => {
    const onBranch = vi.fn();
    mockApi({ 'GET /kredity/reestr': json(KREDITY_REESTR), 'GET /auth/me': json(ME_ADMIN) });
    const { user } = renderWithProviders(<KredityReestr section="kredity" page="reestr" filters={filters} onBranch={onBranch} />);
    const table = await screen.findByRole('table', { name: 'Кредиты' });
    expect(screen.getByRole('list', { name: 'Остаток по кредиторам' })).toBeInTheDocument();
    expect(screen.getByRole('list', { name: 'Валютная структура' })).toBeInTheDocument();
    await user.click(within(table).getByText('Азиатский банк развития'));
    expect(onBranch).toHaveBeenCalledWith(2);
  });

  it('График платежей: schedule and upcoming; branch without loans shows an explanation', async () => {
    mockApi({ 'GET /kredity/grafik': json(KREDITY_GRAFIK), 'GET /auth/me': json(ME_ADMIN) });
    const { unmount } = renderWithProviders(<KredityGrafik section="kredity" page="grafik" filters={filters} onBranch={vi.fn()} />);
    const table = await screen.findByRole('table', { name: 'Предстоящие платежи' });
    expect(within(table).getAllByRole('row')).toHaveLength(1 + 5);
    expect(screen.getByRole('img', { name: 'График погашения' })).toBeInTheDocument();
    unmount();
    mockApi({ 'GET /kredity/grafik': json(KREDITY_EMPTY_GRAFIK), 'GET /auth/me': json(ME_ADMIN) });
    renderWithProviders(<KredityGrafik section="kredity" page="grafik" filters={{ br: 1, per: 'm08' }} onBranch={vi.fn()} />);
    expect(await screen.findByText(/У выбранного филиала нет кредитов/)).toBeInTheDocument();
    expect(screen.queryByRole('img', { name: 'График погашения' })).toBeNull();
  });
});
