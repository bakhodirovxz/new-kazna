import { screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { FinAssumptionOut } from '../api/types';
import { ME_ADMIN } from '../test/fixtures';
import { json, mockApi } from '../test/mockApi';
import { renderWithProviders } from '../test/render';
import FinAssumptionsPage from './FinAssumptionsPage';

const at = '2026-09-01T00:00:00Z';
const row = (year: number, key: string, value: number): FinAssumptionOut => ({ scenario: 'base', year, key, value, version: 1, updated_by: null, updated_at: at });
const FIN: FinAssumptionOut[] = [
  row(2026, 'tariff_growth', 0.08), row(2027, 'tariff_growth', 0.08),
  row(2026, 'capacity_add_mw', 0), row(2027, 'capacity_add_mw', 120),
  row(2026, 'tariff_start', 705),
];

describe('FinAssumptionsPage (S5)', () => {
  it('shows new keys, scalar keys only in 2026 and the second-year note', async () => {
    mockApi({ 'GET /admin/fin-assumptions': json(FIN) });
    renderWithProviders(<FinAssumptionsPage me={ME_ADMIN} />);
    expect(await screen.findByLabelText('Ввод мощностей по АИП, МВт, 2027')).toHaveValue('120');
    expect(screen.getByLabelText('Тариф 2026 года, сум/кВт·ч, 2026')).toHaveValue('705');
    expect(screen.queryByLabelText('Тариф 2026 года, сум/кВт·ч, 2027')).toBeNull();
    const tariffRow = screen.getByRole('row', { name: /Тариф 2026 года/ });
    expect(within(tariffRow).getAllByText('—')).toHaveLength(1);
    expect(screen.getByText(/применяются со второго года модели \(2027\)/)).toBeInTheDocument();
  });

  it('validates each key against its own range', async () => {
    const server = mockApi({ 'GET /admin/fin-assumptions': json(FIN), 'PUT /admin/fin-assumptions': json(FIN) });
    const { user } = renderWithProviders(<FinAssumptionsPage me={ME_ADMIN} />);
    const tariff = await screen.findByLabelText('Тариф 2026 года, сум/кВт·ч, 2026');
    await user.clear(tariff);
    await user.type(tariff, '0');
    await user.click(screen.getByRole('button', { name: 'Сохранить изменения' }));
    expect(screen.getByRole('alert')).toHaveTextContent('Значение вне допустимого диапазона: Базовый · Тариф 2026 года, сум/кВт·ч · 2026');
    await user.clear(tariff);
    await user.type(tariff, '750');
    await user.click(screen.getByRole('button', { name: 'Сохранить изменения' }));
    expect(await screen.findByText('Допущения сохранены. Изменение записано в журнал аудита.')).toBeInTheDocument();
    expect(server.calls.find((c) => c.method === 'PUT')?.body).toEqual({ items: [{ scenario: 'base', year: 2026, key: 'tariff_start', value: 750 }] });
  });

  it('requests a rebuild only for users with admin:etl', async () => {
    const server = mockApi({ 'GET /admin/fin-assumptions': json(FIN), 'POST /admin/etl/run': json({ request_id: 5, status: 'pending' }, 202) });
    const { user, unmount } = renderWithProviders(<FinAssumptionsPage me={ME_ADMIN} />);
    await user.click(await screen.findByRole('button', { name: 'Пересчитать модель' }));
    expect(await screen.findByText(/Пересчёт поставлен в очередь загрузок/)).toBeInTheDocument();
    expect(server.calls.find((c) => c.method === 'POST')?.body).toEqual({ source: 'rebuild', mode: 'full' });
    unmount();
    const noEtl = { ...ME_ADMIN, permissions: ME_ADMIN.permissions.filter((p) => p !== 'admin:etl') };
    renderWithProviders(<FinAssumptionsPage me={noEtl} />);
    await screen.findByLabelText('Рост тарифа, 2027');
    expect(screen.queryByRole('button', { name: 'Пересчитать модель' })).toBeNull();
  });
});
