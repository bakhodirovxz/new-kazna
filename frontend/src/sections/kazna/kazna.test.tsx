import { screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { expectNoAxeViolations } from '../../test/axe';
import { ME_ADMIN } from '../../test/fixtures';
import { json, mockApi } from '../../test/mockApi';
import { renderWithProviders } from '../../test/render';
import { EMPTY_CALENDAR, ITEM_BRANCHES, KAZNA_CALENDAR, KAZNA_PLATEZHI, KAZNA_SVOD } from '../../test/s1Fixtures';
import KaznaCalendar from './calendar';
import KaznaPlatezhi from './platezhi';
import KaznaSvod from './svod';

const filters = { br: null, per: 'm08' };

describe('Казначейство', () => {
  it('Сводка: KPIs, plan-fact top, orders, calendar, banks and debt', async () => {
    mockApi({ 'GET /kazna/svod': json(KAZNA_SVOD), 'GET /auth/me': json(ME_ADMIN) });
    const { container } = renderWithProviders(<KaznaSvod section="kazna" page="svod" filters={filters} onBranch={vi.fn()} />);
    expect(await screen.findByText('Исполнение плана платежей')).toBeInTheDocument();
    expect(screen.getByText('80,0')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Платёжные поручения' })).toBeInTheDocument();
    expect(screen.getByText('в 8,3 раза')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Платёжный календарь' })).toBeInTheDocument();
    const debt = screen.getByRole('table', { name: 'Задолженность по договорам' });
    expect(within(debt).getByText('просрочка 20 дн.')).toBeInTheDocument();
    expect(within(debt).getByText('до 31.12.2026')).toBeInTheDocument();
    await expectNoAxeViolations(container);
  });

  it('Сводка: debt filter shows overdue only', async () => {
    mockApi({ 'GET /kazna/svod': json(KAZNA_SVOD), 'GET /auth/me': json(ME_ADMIN) });
    const { user } = renderWithProviders(<KaznaSvod section="kazna" page="svod" filters={filters} onBranch={vi.fn()} />);
    await user.click(await screen.findByRole('button', { name: 'Просроченные' }));
    const debt = screen.getByRole('table', { name: 'Задолженность по договорам' });
    expect(within(debt).queryByText('ООО «Гидромонтаж»')).toBeNull();
    expect(within(debt).getByText('ООО «Тест Поставщик»')).toBeInTheDocument();
  });

  it('Исполнение платежей: item row opens branch breakdown', async () => {
    mockApi({ 'GET /kazna/platezhi': json(KAZNA_PLATEZHI), 'GET /auth/me': json(ME_ADMIN), 'GET /kazna/platezhi/items/22': json(ITEM_BRANCHES) });
    const { user } = renderWithProviders(<KaznaPlatezhi section="kazna" page="platezhi" filters={filters} onBranch={vi.fn()} />);
    const table = await screen.findByRole('table', { name: 'Исполнение плана платежей по статьям' });
    expect(within(table).getByText('Итого по всем статьям')).toBeInTheDocument();
    await user.click(within(table).getByText('Прочие операционные расходы'));
    const dialog = await screen.findByRole('dialog', { name: 'Прочие операционные расходы' });
    expect(await within(dialog).findByText('Каскад Чирчикских ГЭС')).toBeInTheDocument();
  });

  it('Платёжный календарь: requests by branch toggle the filter; empty calendar shows a source note', async () => {
    const onBranch = vi.fn();
    mockApi({ 'GET /kazna/calendar': json(KAZNA_CALENDAR), 'GET /auth/me': json(ME_ADMIN) });
    const { user, unmount } = renderWithProviders(<KaznaCalendar section="kazna" page="calendar" filters={filters} onBranch={onBranch} />);
    const requests = await screen.findByRole('list', { name: 'Заявки на оплату в работе' });
    expect(within(requests).getByText('заявок: 2')).toBeInTheDocument();
    await user.click(within(requests).getByRole('button', { name: /Каскад Чирчикских ГЭС/ }));
    expect(onBranch).toHaveBeenCalledWith(3);
    unmount();
    mockApi({ 'GET /kazna/calendar': json({ ...KAZNA_CALENDAR, calendar: EMPTY_CALENDAR, banks: [] }), 'GET /auth/me': json(ME_ADMIN) });
    renderWithProviders(<KaznaCalendar section="kazna" page="calendar" filters={filters} onBranch={onBranch} />);
    expect(await screen.findByText(/Источник данных не подключён: плановые платежи/)).toBeInTheDocument();
    expect(screen.getByText(/Источник данных не подключён: остатки по банковским выпискам/)).toBeInTheDocument();
  });
});
