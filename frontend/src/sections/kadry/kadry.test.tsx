import { screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { expectNoAxeViolations } from '../../test/axe';
import { ME_ADMIN } from '../../test/fixtures';
import { json, mockApi } from '../../test/mockApi';
import { renderWithProviders } from '../../test/render';
import { KADRY_CHISL, KADRY_DVIZH, KADRY_EMPTY, KADRY_FOT, KADRY_SVOD, KADRY_YAVKA, KADRY_YAVKA_HIDDEN, KADRY_YAVKA_NONE, KADRY_YAVKA_STALE } from '../../test/s4Fixtures';
import KadryChislennost from './chislennost';
import KadryDvizhenie from './dvizhenie';
import KadryFot from './fot';
import KadrySvod from './svod';

const filters = { br: null, per: 'm08' };

describe('Кадры', () => {
  it('Сводка: KPIs, payroll chart, staff structure and branch table', async () => {
    const onBranch = vi.fn();
    mockApi({ 'GET /kadry/svod': json(KADRY_SVOD), 'GET /kadry/yavka': json(KADRY_YAVKA), 'GET /auth/me': json(ME_ADMIN) });
    const { container, user } = renderWithProviders(<KadrySvod section="kadry" page="svod" filters={filters} onBranch={onBranch} />);
    expect(await screen.findByText('Штатная численность')).toBeInTheDocument();
    expect(screen.getByText('укомплектованность 90,0%')).toBeInTheDocument();
    expect(screen.getByText('за период, 30,0% расходования')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Фонд оплаты труда по месяцам' })).toBeInTheDocument();
    expect(screen.getByText('90,0% персонала')).toBeInTheDocument();
    const table = screen.getByRole('table', { name: 'Численность по филиалам' });
    expect(within(table).getAllByRole('row')).toHaveLength(1 + 2 + 1);
    expect(within(table).getByText('Итого')).toBeInTheDocument();
    await user.click(within(table).getByText('Чарвакская ГЭС'));
    expect(onBranch).toHaveBeenCalledWith(2);
    await expectNoAxeViolations(container);
  });

  it('Сводка: «Явка сегодня» — итоги, причины, время данных и таблица по филиалам', async () => {
    const onBranch = vi.fn();
    mockApi({ 'GET /kadry/svod': json(KADRY_SVOD), 'GET /kadry/yavka': json(KADRY_YAVKA), 'GET /auth/me': json(ME_ADMIN) });
    const { container, user } = renderWithProviders(<KadrySvod section="kadry" page="svod" filters={filters} onBranch={onBranch} />);
    const card = (await screen.findByRole('heading', { name: 'Явка сегодня' })).closest('section') as HTMLElement;
    expect(within(card).getByText('Данные на 11:12')).toBeInTheDocument();
    expect(within(card).queryByText('Данные устарели')).not.toBeInTheDocument();
    expect(within(card).getByText(/На работе, явка 85,7%/)).toBeInTheDocument();
    expect(within(card).getByText('В командировке').nextElementSibling).toHaveTextContent('2');
    expect(within(card).getByText('Прочие причины').nextElementSibling).toHaveTextContent('1');
    const others = within(card).getByRole('list', { name: 'Прочие причины по видам' });
    expect(within(others).getByText('Yangi sabab')).toBeInTheDocument(); // неизвестный код — подпись API
    expect(within(others).queryByText("Tug'ruq")).not.toBeInTheDocument(); // нулевые не показываем
    const table = screen.getByRole('table', { name: 'Явка по филиалам' });
    const first = within(table).getAllByRole('row')[1] as HTMLElement;
    expect(first).toHaveTextContent('Каскад Чирчикских ГЭС');
    expect(first).toHaveTextContent('90,0%');
    await user.click(within(table).getByText('Чарвакская ГЭС'));
    expect(onBranch).toHaveBeenCalledWith(2);
    await expectNoAxeViolations(container);
  });

  it('Сводка: явка устарела или источник не подключён', async () => {
    mockApi({ 'GET /kadry/svod': json(KADRY_SVOD), 'GET /kadry/yavka': json(KADRY_YAVKA_STALE), 'GET /auth/me': json(ME_ADMIN) });
    const { unmount } = renderWithProviders(<KadrySvod section="kadry" page="svod" filters={filters} onBranch={vi.fn()} />);
    expect(await screen.findByText('Данные устарели')).toBeInTheDocument();
    unmount();
    mockApi({ 'GET /kadry/svod': json(KADRY_SVOD), 'GET /kadry/yavka': json(KADRY_YAVKA_NONE), 'GET /auth/me': json(ME_ADMIN) });
    renderWithProviders(<KadrySvod section="kadry" page="svod" filters={filters} onBranch={vi.fn()} />);
    expect(await screen.findByText(/Источник данных не подключён: кадровая система \(HR API, явка\)/)).toBeInTheDocument();
  });

  it('Сводка: явка малой группы скрыта', async () => {
    mockApi({ 'GET /kadry/svod': json(KADRY_SVOD), 'GET /kadry/yavka': json(KADRY_YAVKA_HIDDEN), 'GET /auth/me': json(ME_ADMIN) });
    renderWithProviders(<KadrySvod section="kadry" page="svod" filters={filters} onBranch={vi.fn()} />);
    const card = (await screen.findByRole('heading', { name: 'Явка сегодня' })).closest('section') as HTMLElement;
    expect(within(card).getByText('В командировке').nextElementSibling).toHaveTextContent('скрыто (малая группа)');
    const table = screen.getByRole('table', { name: 'Явка по филиалам' });
    expect(within(table).getAllByText('скрыто (малая группа)').length).toBeGreaterThan(0);
  });

  it('Численность: vacancies by branch, largest first', async () => {
    mockApi({ 'GET /kadry/chislennost': json(KADRY_CHISL), 'GET /auth/me': json(ME_ADMIN) });
    renderWithProviders(<KadryChislennost section="kadry" page="chislennost" filters={filters} onBranch={vi.fn()} />);
    const rank = await screen.findByRole('list', { name: 'Вакансии по филиалам' });
    const items = within(rank).getAllByRole('listitem');
    expect(items[0]).toHaveTextContent('Чарвакская ГЭС');
    expect(items[0]).toHaveTextContent('30 чел.');
    expect(items[0]).toHaveTextContent('20,0% штата');
  });

  it('Оплата труда: payroll share, average salary and payroll by branch', async () => {
    mockApi({ 'GET /kadry/fot': json(KADRY_FOT), 'GET /auth/me': json(ME_ADMIN) });
    renderWithProviders(<KadryFot section="kadry" page="fot" filters={filters} onBranch={vi.fn()} />);
    expect(await screen.findByText('30,0%')).toBeInTheDocument();
    const avg = within(screen.getByRole('list', { name: 'Средняя зарплата по филиалам' })).getAllByRole('listitem');
    expect(avg[0]).toHaveTextContent('Чарвакская ГЭС');
    expect(avg[0]).toHaveTextContent('2,1 млн');
    expect(within(screen.getByRole('list', { name: 'ФОТ по филиалам' })).getAllByRole('listitem')).toHaveLength(2);
  });

  it('Движение кадров: hires and fires chart, overtime and turnover table', async () => {
    mockApi({ 'GET /kadry/dvizhenie': json(KADRY_DVIZH), 'GET /auth/me': json(ME_ADMIN) });
    const { container } = renderWithProviders(<KadryDvizhenie section="kadry" page="dvizhenie" filters={filters} onBranch={vi.fn()} />);
    expect(await screen.findByRole('img', { name: 'Приём и увольнение по месяцам' })).toBeInTheDocument();
    expect(container.querySelector('.bigline b')).toHaveTextContent('420 ч');
    expect(screen.getByText('4,7 ч на работника')).toBeInTheDocument();
    const table = screen.getByRole('table', { name: 'Текучесть по филиалам' });
    const first = within(table).getAllByRole('row')[1];
    expect(first).toHaveTextContent('Чарвакская ГЭС');
    expect(within(first as HTMLElement).getByText('10,0%').closest('.exec')).toHaveClass('neg');
  });

  it('No staff data: KPIs show dashes and the source message', async () => {
    mockApi({ 'GET /kadry/svod': json(KADRY_EMPTY), 'GET /kadry/yavka': json(KADRY_YAVKA_NONE), 'GET /auth/me': json(ME_ADMIN) });
    renderWithProviders(<KadrySvod section="kadry" page="svod" filters={filters} onBranch={vi.fn()} />);
    expect(await screen.findByText(/кадровые данные \(HR API или файл численности\)/)).toBeInTheDocument();
    expect(screen.getAllByText('штат не загружен').length).toBeGreaterThan(0);
  });
});
