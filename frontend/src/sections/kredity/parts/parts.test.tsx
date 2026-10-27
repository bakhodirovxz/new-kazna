import { screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { expectNoAxeViolations } from '../../../test/axe';
import { ME_ADMIN } from '../../../test/fixtures';
import { json, mockApi } from '../../../test/mockApi';
import { renderWithProviders } from '../../../test/render';
import { LOAN_KPIS, LOAN_ROWS, SCHEDULE, UPCOMING } from '../../../test/s2Fixtures';
import { currencyName } from './currency';
import { DscrCard } from './DscrCard';
import { LoanKpis } from './LoanKpis';
import { LoanRegistry } from './LoanRegistry';
import { NoLoans } from './NoLoans';
import { ScheduleCard } from './ScheduleCard';
import { UpcomingCard } from './UpcomingCard';

const ctx = { section: 'kredity', page: 'svod', br: null, per: 'm08' };
const filters = { br: null, per: 'm08' };

describe('Кредиты: карточки', () => {
  it('KPIs show portfolio, rate, service, next payment and peak year', async () => {
    const { container } = renderWithProviders(<LoanKpis kpis={LOAN_KPIS} />);
    expect(screen.getByText('Кредитный портфель')).toBeInTheDocument();
    expect(screen.getByText('9,4')).toBeInTheDocument();
    expect(screen.getByText('5,55%')).toBeInTheDocument();
    expect(screen.getByText('Обслуживание долга 2026')).toBeInTheDocument();
    expect(screen.getByText('15.09.2026')).toBeInTheDocument();
    expect(screen.getByText('2028')).toBeInTheDocument();
    expect(screen.getByText('на 31.08.2026, кредитов: 2')).toBeInTheDocument();
    await expectNoAxeViolations(container);
  });

  it('KPIs warn about currencies without a CBU rate', () => {
    renderWithProviders(<LoanKpis kpis={{ ...LOAN_KPIS, missing_fx: ['CNY'] }} />);
    expect(screen.getByText('нет курса ЦБ: CNY')).toBeInTheDocument();
  });

  it('schedule chart is accessible and upcoming payments show missing rates', async () => {
    mockApi({ 'GET /auth/me': json(ME_ADMIN) });
    renderWithProviders(
      <>
        <ScheduleCard years={SCHEDULE} ctx={ctx} />
        <UpcomingCard payments={UPCOMING} title="Ближайшие платежи" sub="Пять" ctx={ctx} more />
      </>,
    );
    expect(screen.getByRole('img', { name: 'График погашения' })).toBeInTheDocument();
    const table = screen.getByRole('table', { name: 'Ближайшие платежи' });
    expect(within(table).getAllByRole('row')).toHaveLength(1 + UPCOMING.length);
    expect(within(table).getAllByText('нет курса').length).toBeGreaterThan(0);
    expect(screen.getByRole('link', { name: 'Весь график' }).getAttribute('href')).toContain('kredity/grafik');
    expect(await screen.findByRole('button', { name: 'Выгрузить таблицу «Ближайшие платежи» в CSV' })).toBeInTheDocument();
  });

  it('registry shows grace badge, total and toggles the branch filter', async () => {
    const onBranch = vi.fn();
    mockApi({ 'GET /auth/me': json(ME_ADMIN) });
    const { user } = renderWithProviders(<LoanRegistry loans={LOAN_ROWS} asOf="2026-08-31" ctx={ctx} filters={filters} onBranch={onBranch} />);
    const table = screen.getByRole('table', { name: 'Кредиты' });
    expect(within(table).getByText('до 2027 года')).toBeInTheDocument();
    expect(within(table).getByText('Итого')).toBeInTheDocument();
    await user.click(within(table).getByText('Национальный банк'));
    expect(onBranch).toHaveBeenCalledWith(3);
  });

  it('DSCR gap, no-loans message and currency names', () => {
    renderWithProviders(
      <>
        <DscrCard dscr={null} />
        <NoLoans />
      </>,
    );
    expect(screen.getByText(/Источник данных не подключён: финансовая модель/)).toBeInTheDocument();
    expect(screen.getByText(/У выбранного филиала нет кредитов/)).toBeInTheDocument();
    expect(currencyName('USD')).toBe('Доллар США (USD)');
    expect(currencyName('XTL')).toBe('XTL');
  });
});
