import { screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { expectNoAxeViolations } from '../../test/axe';
import { ME_ADMIN } from '../../test/fixtures';
import { json, mockApi } from '../../test/mockApi';
import { renderWithProviders } from '../../test/render';
import { ZAK_EKONOMIYA, ZAK_LOTY, ZAK_POSTAVSHIKI, ZAK_SVOD } from '../../test/s4Fixtures';
import ZakupkiEkonomiya from './ekonomiya';
import ZakupkiLoty from './loty';
import ZakupkiPostavshiki from './postavshiki';
import ZakupkiSvod from './svod';

const filters = { br: null, per: 'm08' };

describe('Закупки', () => {
  it('Сводка: KPIs, months chart, methods and top lots with the overdue first', async () => {
    mockApi({ 'GET /zakupki/svod': json(ZAK_SVOD), 'GET /auth/me': json(ME_ADMIN) });
    const { container } = renderWithProviders(<ZakupkiSvod section="zakupki" page="svod" filters={filters} onBranch={vi.fn()} />);
    expect(await screen.findByText('Заключено договоров')).toBeInTheDocument();
    expect(screen.getByText('19,7%')).toHaveClass('neg');
    expect(screen.getByText('35,7%')).toHaveClass('neg');
    expect(screen.getByRole('img', { name: 'Заключённые договоры по месяцам' })).toBeInTheDocument();
    expect(within(screen.getByRole('list', { name: 'Способы закупки' })).getAllByRole('listitem')).toHaveLength(2);
    const table = screen.getByRole('table', { name: 'Лоты' });
    expect(within(table).getAllByRole('row')).toHaveLength(1 + 5);
    expect(within(table).getByText('85 дн. (норма 40)')).toHaveClass('badge--neg');
    expect(screen.getByRole('link', { name: 'Все лоты' }).getAttribute('href')).toContain('zakupki/loty');
    await expectNoAxeViolations(container);
  });

  it('Лоты: segment filter by work, overdue and concluded', async () => {
    mockApi({ 'GET /zakupki/loty': json(ZAK_LOTY), 'GET /auth/me': json(ME_ADMIN) });
    const { user } = renderWithProviders(<ZakupkiLoty section="zakupki" page="loty" filters={filters} onBranch={vi.fn()} />);
    const table = await screen.findByRole('table', { name: 'Лоты' });
    expect(within(table).getAllByRole('row')).toHaveLength(1 + 5);
    await user.click(screen.getByRole('button', { name: 'Просроченные' }));
    expect(screen.getByRole('button', { name: 'Просроченные' })).toHaveAttribute('aria-pressed', 'true');
    expect(within(screen.getByRole('table', { name: 'Лоты' })).getAllByRole('row')).toHaveLength(1 + 1);
    await user.click(screen.getByRole('button', { name: 'В работе' }));
    expect(within(screen.getByRole('table', { name: 'Лоты' })).getAllByRole('row')).toHaveLength(1 + 2);
    await user.click(screen.getByRole('button', { name: 'Заключённые' }));
    const done = screen.getByRole('table', { name: 'Лоты' });
    expect(within(done).getAllByRole('row')).toHaveLength(1 + 2);
    expect(within(done).getAllByText('Договор заключён')).toHaveLength(2);
    expect(screen.queryByRole('link', { name: 'Все лоты' })).toBeNull();
  });

  it('Договоры и поставщики: suppliers, subjects and branch table selects a branch', async () => {
    const onBranch = vi.fn();
    mockApi({ 'GET /zakupki/postavshiki': json(ZAK_POSTAVSHIKI), 'GET /auth/me': json(ME_ADMIN) });
    const { user } = renderWithProviders(<ZakupkiPostavshiki section="zakupki" page="postavshiki" filters={filters} onBranch={onBranch} />);
    const suppliers = await screen.findByRole('list', { name: 'Поставщики' });
    expect(within(suppliers).getAllByRole('listitem')[0]).toHaveTextContent('ООО «Гидромонтаж Сервис»');
    expect(screen.getByRole('list', { name: 'Предметы закупок' })).toBeInTheDocument();
    const table = screen.getByRole('table', { name: 'Закупки по филиалам' });
    await user.click(within(table).getByText('Чарвакская ГЭС'));
    expect(onBranch).toHaveBeenCalledWith(2);
  });

  it('Экономия: savings by method, cancelled lots and average duration', async () => {
    mockApi({ 'GET /zakupki/ekonomiya': json(ZAK_EKONOMIYA), 'GET /auth/me': json(ME_ADMIN) });
    renderWithProviders(<ZakupkiEkonomiya section="zakupki" page="ekonomiya" filters={filters} onBranch={vi.fn()} />);
    const table = await screen.findByRole('table', { name: 'Экономия по способам закупки' });
    expect(within(table).getByText('Электронный магазин')).toBeInTheDocument();
    expect(within(table).getByText('10,0%')).toBeInTheDocument();
    expect(within(screen.getByRole('table', { name: 'Отменённые лоты' })).getByText('2026-0105')).toBeInTheDocument();
    expect(screen.getByText('8,5 дн.')).toBeInTheDocument();
    expect(within(screen.getByRole('list', { name: 'Средний срок закупки' })).getAllByRole('listitem')).toHaveLength(2);
  });
});
