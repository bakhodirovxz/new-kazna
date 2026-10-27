import { screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type * as Download from './download';
import { apiError, json, mockApi } from '../test/mockApi';
import { ME_ADMIN, ME_AUDITOR } from '../test/fixtures';
import { renderWithProviders } from '../test/render';
import { CardExport } from './CardExport';

const saved = vi.hoisted(() => vi.fn());
vi.mock('./download', async (importOriginal) => ({
  ...(await importOriginal<typeof Download>()),
  saveBlob: (blob: Blob, name: string) => saved(blob, name),
}));

// jsdom Blob'da text() yo'q.
const readBlob = (blob: Blob) =>
  new Promise<string>((resolve) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.readAsText(blob);
  });
const ctx = { section: 'obzor', page: 'svod', br: 3, per: 'm08' };
const table = () => ({ headers: ['Филиал', 'Сумма'], rows: [['Чарвак', 10]] as Array<Array<string | number | null>> });

describe('CardExport', () => {
  beforeEach(() => saved.mockReset());

  it('logs the export before saving the CSV file', async () => {
    const { calls } = mockApi({ 'GET /auth/me': json(ME_ADMIN), 'POST /exports/log': { status: 204 } });
    const { user } = renderWithProviders(<CardExport title="Расходование по филиалам" ctx={ctx} csv={table} />);
    await user.click(await screen.findByRole('button', { name: 'Выгрузить таблицу «Расходование по филиалам» в CSV' }));
    await waitFor(() => expect(saved).toHaveBeenCalledTimes(1));
    const log = calls.find((c) => c.path === '/exports/log');
    expect(log?.body).toEqual({ kind: 'csv', section: 'obzor', page: 'svod', card: 'Расходование по филиалам', br: 3, per: 'm08', rows: 1 });
    const [blob, name] = saved.mock.calls[0] as [Blob, string];
    expect(name).toBe('Расходование_по_филиалам.csv');
    expect(await readBlob(blob)).toContain('Чарвак;10');
  });

  it('does not save when the audit log is rejected', async () => {
    mockApi({ 'GET /auth/me': json(ME_ADMIN), 'POST /exports/log': apiError(403, 'forbidden', 'Недостаточно прав') });
    const { user } = renderWithProviders(<CardExport title="T" ctx={ctx} csv={table} />);
    await user.click(await screen.findByRole('button', { name: 'Выгрузить таблицу «T» в CSV' }));
    expect(await screen.findByText('Выгрузка не выполнена: Недостаточно прав')).toBeInTheDocument();
    expect(saved).not.toHaveBeenCalled();
  });

  it('renders nothing without export permission', async () => {
    mockApi({ 'GET /auth/me': json({ ...ME_AUDITOR, permissions: ['section:obzor:view'] }) });
    const { container } = renderWithProviders(<CardExport title="T" ctx={ctx} csv={table} />);
    await waitFor(() => expect(container.querySelector('button')).toBeNull());
  });
});
