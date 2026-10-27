import { screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { expectNoAxeViolations } from '../../test/axe';
import { ME_ADMIN } from '../../test/fixtures';
import { json, mockApi } from '../../test/mockApi';
import { renderWithProviders } from '../../test/render';
import { POWER, POWER_NONE, POWER_STALE, PROIZV_HQ, PROIZV_REALIZ, PROIZV_STANCII, PROIZV_SVOD } from '../../test/s3Fixtures';
import { PowerCard } from './parts/PowerCard';
import ProizvodstvoRealiz from './realiz';
import ProizvodstvoStancii from './stancii';
import ProizvodstvoSvod from './svod';

const filters = { br: null, per: 'm08' };

describe('Производство', () => {
  it('Сводка: KPIs, months chart, station rank, map with panel and current power', async () => {
    const onBranch = vi.fn();
    mockApi({ 'GET /proizvodstvo/svod': json(PROIZV_SVOD), 'GET /proizvodstvo/moshchnost': json(POWER), 'GET /auth/me': json(ME_ADMIN) });
    const { container, user } = renderWithProviders(<ProizvodstvoSvod section="proizvodstvo" page="svod" filters={filters} onBranch={onBranch} />);
    expect(await screen.findByText('Выработка электроэнергии')).toBeInTheDocument();
    expect(screen.getByText('96,0%')).toBeInTheDocument();
    expect(screen.getByText('52,0%')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Выработка по месяцам' })).toBeInTheDocument();
    const rank = screen.getByRole('list', { name: 'Выработка по станциям' });
    await user.click(within(rank).getByText('Чарвакская ГЭС'));
    expect(onBranch).toHaveBeenCalledWith(2);
    expect(screen.getByRole('link', { name: 'Все станции' }).getAttribute('href')).toContain('proizvodstvo/stancii');
    expect(screen.getByRole('group', { name: 'Карта Узбекистана с расположением ГЭС' })).toBeInTheDocument();
    expect(await screen.findByText('412,5 МВт')).toBeInTheDocument();
    expect(screen.getByText('по данным на 25.09.2026 10:40')).toBeInTheDocument();
    expect(screen.getByText('Агрегаты: в работе 5, в резерве 1, в ремонте 1')).toBeInTheDocument();
    await expectNoAxeViolations(container);
  });

  it('Сводка: selecting a station on the map shows its production and opens its data', async () => {
    const onBranch = vi.fn();
    mockApi({ 'GET /proizvodstvo/svod': json(PROIZV_SVOD), 'GET /proizvodstvo/moshchnost': json(POWER), 'GET /auth/me': json(ME_ADMIN) });
    const { user } = renderWithProviders(<ProizvodstvoSvod section="proizvodstvo" page="svod" filters={filters} onBranch={onBranch} />);
    await user.click(await screen.findByRole('button', { name: /Каскад Чирчикских ГЭС: 190 МВт, выработка 80,0 млн кВт·ч, 80% плана/ }));
    const panel = screen.getByRole('heading', { name: 'Каскад Чирчикских ГЭС' }).closest('.gp');
    expect(panel).not.toBeNull();
    expect(within(panel as HTMLElement).getByText('80% плана')).toHaveClass('neg');
    await user.click(screen.getByRole('button', { name: 'Открыть данные станции' }));
    expect(onBranch).toHaveBeenCalledWith(3);
  });

  it('HQ selected shows the no-stations message instead of cards', async () => {
    mockApi({ 'GET /proizvodstvo/svod': json({ ...PROIZV_SVOD, has_stations: false, stations: [] }), 'GET /auth/me': json(ME_ADMIN) });
    const first = renderWithProviders(<ProizvodstvoSvod section="proizvodstvo" page="svod" filters={{ br: 1, per: 'm08' }} onBranch={vi.fn()} />);
    expect(await screen.findByText(/Головная организация не эксплуатирует станции/)).toBeInTheDocument();
    first.unmount();
    expect(screen.queryByRole('img', { name: 'Выработка по месяцам' })).toBeNull();
    mockApi({ 'GET /proizvodstvo/stancii': json(PROIZV_HQ), 'GET /auth/me': json(ME_ADMIN) });
    renderWithProviders(<ProizvodstvoStancii section="proizvodstvo" page="stancii" filters={{ br: 1, per: 'm08' }} onBranch={vi.fn()} />);
    expect(await screen.findByText(/Головная организация не эксплуатирует станции/)).toBeInTheDocument();
  });

  it('Выработка по станциям: table with totals, low execution in red, row click selects the branch', async () => {
    const onBranch = vi.fn();
    mockApi({ 'GET /proizvodstvo/stancii': json(PROIZV_STANCII), 'GET /auth/me': json(ME_ADMIN) });
    const { user } = renderWithProviders(<ProizvodstvoStancii section="proizvodstvo" page="stancii" filters={filters} onBranch={onBranch} />);
    const table = await screen.findByRole('table', { name: 'Станции' });
    expect(within(table).getAllByRole('row')).toHaveLength(1 + 3 + 1);
    expect(within(table).getByText('Итого')).toBeInTheDocument();
    expect(within(table).getByText('80%').closest('.exec')).toHaveClass('neg');
    await user.click(within(table).getByText('Каскад Чирчикских ГЭС'));
    expect(onBranch).toHaveBeenCalledWith(3);
    expect(await screen.findByRole('button', { name: 'Выгрузить таблицу «Станции» в CSV' })).toBeInTheDocument();
  });

  it('Реализация: sales chart and stations by payment level', async () => {
    mockApi({ 'GET /proizvodstvo/realiz': json(PROIZV_REALIZ), 'GET /auth/me': json(ME_ADMIN) });
    renderWithProviders(<ProizvodstvoRealiz section="proizvodstvo" page="realiz" filters={filters} onBranch={vi.fn()} />);
    expect(await screen.findByRole('img', { name: 'Реализация электроэнергии по месяцам' })).toBeInTheDocument();
    const rank = screen.getByRole('list', { name: 'Уровень оплаты по станциям' });
    const first = within(rank).getAllByRole('listitem')[0];
    expect(first).toHaveTextContent('Каскад Чирчикских ГЭС');
    expect(first).toHaveTextContent('73% оплаты');
  });

  it('PowerCard shows stale and missing source', async () => {
    mockApi({ 'GET /proizvodstvo/moshchnost': json(POWER_STALE), 'GET /auth/me': json(ME_ADMIN) });
    const { unmount } = renderWithProviders(<PowerCard filters={filters} />);
    expect(await screen.findByText('Данные устарели')).toBeInTheDocument();
    unmount();
    mockApi({ 'GET /proizvodstvo/moshchnost': json(POWER_NONE), 'GET /auth/me': json(ME_ADMIN) });
    renderWithProviders(<PowerCard filters={filters} />);
    expect(await screen.findByText(/Источник данных не подключён: онлайн-мониторинг ГЭС/)).toBeInTheDocument();
  });
});
