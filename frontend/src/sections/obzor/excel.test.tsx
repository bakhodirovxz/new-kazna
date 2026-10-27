import { act, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { expectNoAxeViolations } from '../../test/axe';
import { ME_ADMIN, ME_BRANCH } from '../../test/fixtures';
import { json, mockApi } from '../../test/mockApi';
import { renderWithProviders } from '../../test/render';
import { EXCEL } from '../../test/s1Fixtures';
import ObzorExcel from './excel';

describe('Обзор / Таблица Excel', () => {
  it('shows the branch summary with totals and an xlsx link', async () => {
    const onBranch = vi.fn();
    mockApi({ 'GET /obzor/excel': json(EXCEL), 'GET /auth/me': json(ME_ADMIN) });
    const { user, container } = renderWithProviders(<ObzorExcel section="obzor" page="excel" filters={{ br: null, per: 'm08' }} onBranch={onBranch} />);
    const summary = await screen.findByRole('table', { name: 'Сводка по филиалам' });
    expect(within(summary).getByText('Итого')).toBeInTheDocument();
    expect(within(summary).getAllByText('1 060,0').length).toBeGreaterThan(0);
    const link = screen.getByRole('link', { name: 'Скачать Excel' });
    expect(link.getAttribute('href')).toBe('/api/v1/obzor/excel.xlsx?per=m08');
    await user.click(within(summary).getByText('Чарвакская ГЭС'));
    expect(onBranch).toHaveBeenCalledWith(2);
    await expectNoAxeViolations(container);
  });

  it('filters detail by direction and search', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    mockApi({ 'GET /obzor/excel': json(EXCEL), 'GET /auth/me': json(ME_ADMIN) });
    const { user } = renderWithProviders(<ObzorExcel section="obzor" page="excel" filters={{ br: null, per: 'm08' }} onBranch={vi.fn()} />);
    const detail = await screen.findByRole('table', { name: 'Детализация по статьям' });
    expect(within(detail).getByText('Строк: 3')).toBeInTheDocument();
    await user.click(within(screen.getByRole('group', { name: 'Направление' })).getByRole('button', { name: 'Расходование' })); // в сводке есть одноимённая кнопка сортировки
    expect(within(detail).getByText('Строк: 2')).toBeInTheDocument();
    await user.type(screen.getByRole('searchbox', { name: 'Поиск по филиалу или статье' }), 'чирчик');
    await act(() => vi.advanceTimersByTimeAsync(300));
    expect(within(detail).getByText('Строк: 1')).toBeInTheDocument();
    vi.useRealTimers();
  });

  it('hides the xlsx link without export permission', async () => {
    mockApi({ 'GET /obzor/excel': json(EXCEL), 'GET /auth/me': json({ ...ME_BRANCH, permissions: ['section:obzor:view'] }) });
    renderWithProviders(<ObzorExcel section="obzor" page="excel" filters={{ br: 3, per: 'm08' }} onBranch={vi.fn()} />);
    await screen.findByRole('table', { name: 'Сводка по филиалам' });
    expect(screen.queryByRole('link', { name: 'Скачать Excel' })).toBeNull();
  });
});
