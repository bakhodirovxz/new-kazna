import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { expectNoAxeViolations } from '../test/axe';
import { Pagination } from './Pagination';
import { Table, type Column } from './Table';

interface Row {
  id: number;
  name: string;
  amount: number | null;
}

const ROWS: Row[] = [
  { id: 1, name: 'Чарвакская ГЭС', amount: 120 },
  { id: 2, name: 'Андижанская ГЭС', amount: null },
  { id: 3, name: 'Бозсу', amount: 540 },
];

const COLUMNS: Column<Row>[] = [
  { key: 'name', header: 'Филиал', align: 'left', cell: (r) => r.name, sortValue: (r) => r.name },
  { key: 'amount', header: 'Сумма', cell: (r) => (r.amount === null ? '—' : String(r.amount)), sortValue: (r) => r.amount },
  { key: 'note', header: 'Примечание', cell: () => 'x' },
];

const names = () =>
  screen
    .getAllByRole('row')
    .slice(1)
    .map((row) => within(row).getAllByRole('cell')[0]?.textContent);

describe('Table', () => {
  it('sorts by clickable headers with aria-sort and keeps nulls last', async () => {
    render(<Table caption="Филиалы" columns={COLUMNS} rows={ROWS} rowKey={(r) => r.id} />);
    expect(screen.getByRole('table', { name: 'Филиалы' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Примечание' })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Сумма' }));
    expect(screen.getByRole('columnheader', { name: 'Сумма' })).toHaveAttribute('aria-sort', 'ascending');
    expect(names()).toEqual(['Чарвакская ГЭС', 'Бозсу', 'Андижанская ГЭС']);
    await userEvent.click(screen.getByRole('button', { name: 'Сумма' }));
    expect(screen.getByRole('columnheader', { name: 'Сумма' })).toHaveAttribute('aria-sort', 'descending');
    expect(names()).toEqual(['Бозсу', 'Чарвакская ГЭС', 'Андижанская ГЭС']);
    await userEvent.click(screen.getByRole('button', { name: 'Филиал' }));
    expect(names()).toEqual(['Андижанская ГЭС', 'Бозсу', 'Чарвакская ГЭС']);
  });

  it('activates rows with click, Enter and Space', async () => {
    const onRowClick = vi.fn();
    render(<Table caption="Филиалы" columns={COLUMNS} rows={ROWS} rowKey={(r) => r.id} onRowClick={onRowClick} activeKey={3} />);
    const rows = screen.getAllByRole('row').slice(1);
    await userEvent.click(within(rows[0] as HTMLElement).getByText('Чарвакская ГЭС'));
    expect(onRowClick).toHaveBeenLastCalledWith(ROWS[0]);
    (rows[1] as HTMLElement).focus();
    await userEvent.keyboard('{Enter}');
    expect(onRowClick).toHaveBeenLastCalledWith(ROWS[1]);
    await userEvent.keyboard(' ');
    expect(onRowClick).toHaveBeenCalledTimes(3);
    expect(rows[2]).toHaveClass('active');
    expect(rows[2]).toHaveAttribute('tabindex', '0');
  });

  it('labels every cell for the mobile card layout and shows the empty state', () => {
    const { rerender } = render(<Table caption="Филиалы" columns={COLUMNS} rows={ROWS} rowKey={(r) => r.id} />);
    const firstCell = screen.getAllByRole('cell')[1];
    expect(firstCell).toHaveAttribute('data-label', 'Сумма');
    expect(screen.getByRole('table').parentElement).toHaveClass('tw--cards');
    rerender(<Table caption="Филиалы" columns={COLUMNS} rows={[]} rowKey={(r) => r.id} empty="Пользователи не найдены" />);
    expect(screen.getByText('Пользователи не найдены')).toBeInTheDocument();
  });

  it('has no axe violations', async () => {
    const { container } = render(
      <Table caption="Филиалы" columns={COLUMNS} rows={ROWS} rowKey={(r) => r.id} onRowClick={vi.fn()} />,
    );
    await expectNoAxeViolations(container);
  });
});

const NBSP = String.fromCharCode(0xa0);

describe('Pagination', () => {
  it('shows the range and moves between pages', async () => {
    const onPage = vi.fn();
    render(<Pagination page={2} pageSize={50} total={1234} onPage={onPage} />);
    // toHaveTextContent NBSP'ni oddiy probelga normallashtiradi — xom textContent tekshiriladi.
    expect(screen.getByRole('navigation', { name: 'Страницы' }).textContent).toContain('51–100 из 1' + NBSP + '234');
    await userEvent.click(screen.getByRole('button', { name: 'Предыдущая страница' }));
    expect(onPage).toHaveBeenCalledWith(1);
    await userEvent.click(screen.getByRole('button', { name: 'Следующая страница' }));
    expect(onPage).toHaveBeenCalledWith(3);
  });

  it('disables the edges', () => {
    render(<Pagination page={1} pageSize={50} total={10} onPage={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'Предыдущая страница' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Следующая страница' })).toBeDisabled();
  });
});

describe('Table extras', () => {
  it('announces the sort and ignores clicks/keys from nested action buttons', async () => {
    const onRowClick = vi.fn();
    const cols: Column<Row>[] = [
      ...COLUMNS,
      { key: 'act', header: 'Действия', cell: () => <button type="button">Изменить</button> },
    ];
    render(<Table caption="Филиалы" columns={cols} rows={ROWS} rowKey={(r) => r.id} onRowClick={onRowClick} />);
    await userEvent.click(screen.getByRole('button', { name: 'Сумма' }));
    expect(screen.getByRole('status')).toHaveTextContent('Сортировка: Сумма, по возрастанию');
    onRowClick.mockClear();
    const [btn] = screen.getAllByRole('button', { name: 'Изменить' });
    await userEvent.click(btn as HTMLElement);
    (btn as HTMLElement).focus();
    await userEvent.keyboard('{Enter}');
    expect(onRowClick).not.toHaveBeenCalled();
  });
});
