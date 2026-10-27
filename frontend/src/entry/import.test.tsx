import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { expectNoAxeViolations } from '../test/axe';
import { BRANCHES } from '../test/fixtures';
import { apiError, json, mockApi, type MockHandler } from '../test/mockApi';
import { renderWithProviders } from '../test/render';
import type { EntryEntity } from './api';
import { ImportDialog } from './ImportDialog';

const ENTITY: EntryEntity = {
  id: 'kazna.balance', section: 'kazna', section_title: 'Казначейство', title: 'Остатки на счетах',
  kind: 'fact', layout: 'form', grid: null, can_write: true, can_approve: false,
  fields: [
    { name: 'branch_code', kind: 'ref', title: 'Филиал', required: true, options: [], ref: 'dim_branch', unit: '' },
    { name: 'balance', kind: 'money', title: 'Остаток', required: true, options: [], unit: 'млн сум' },
  ],
};
const BATCH = { batch_id: 9, entity: 'kazna.balance', branch_id: 3, status: 'draft', origin: 'import', rows: 2, version: 1 };

function server(extra: Record<string, MockHandler> = {}) {
  document.cookie = '__Host-ugk_csrf=tok123; Secure; Path=/';
  return mockApi({ 'GET /meta/branches': json(BRANCHES), ...extra });
}

const csv = (name = 'ostatki.csv', body = 'branch_code;balance\nCHIRCHIK;1\n') =>
  new File([body], name, { type: 'text/csv' });

afterEach(() => vi.unstubAllGlobals());

describe('ImportDialog', () => {
  it('uploads csv as raw body with csrf', async () => {
    const srv = server({ 'POST /data/entities/kazna.balance/import': json(BATCH, 201) });
    const { user } = renderWithProviders(<ImportDialog entity={ENTITY} branch={3} onClose={() => undefined} />);
    const dialog = await screen.findByRole('dialog');
    const file = csv('Остатки сентябрь.csv');
    await user.upload(within(dialog).getByLabelText(/Файл/), file);
    await user.click(within(dialog).getByRole('button', { name: 'Загрузить' }));
    expect(await within(dialog).findByText('Создан черновик: 2 строк')).toBeInTheDocument();
    const call = srv.calls.find((c) => c.method === 'POST');
    expect(call?.rawBody).toBe(file);
    expect(call?.url.searchParams.get('branch_id')).toBe('3');
    expect(call?.headers.get('Content-Type')).toBe('text/csv');
    expect(call?.headers.get('X-CSRF-Token')).toBe('tok123');
    expect(call?.headers.get('X-File-Name')).toBe(encodeURIComponent('Остатки сентябрь.csv'));
    expect(within(dialog).getByRole('link', { name: 'Перейти к пакетам' })).toHaveAttribute('href', '#vvod/batches');
  });

  it('shows row errors', async () => {
    server({
      'POST /data/entities/kazna.balance/import': apiError(422, 'import_invalid', 'x', {
        rows: [{ row: 3, field: 'balance', code: 'invalid_value' }, { row: 1, field: '', code: 'bad_header' }],
        fields: ['balance'],
      }),
    });
    const { user } = renderWithProviders(<ImportDialog entity={ENTITY} branch={3} onClose={() => undefined} />);
    const dialog = await screen.findByRole('dialog');
    await user.upload(within(dialog).getByLabelText(/Файл/), csv());
    await user.click(within(dialog).getByRole('button', { name: 'Загрузить' }));
    const table = await within(dialog).findByRole('table');
    expect(within(table).getByText('Остаток')).toBeInTheDocument();
    expect(within(table).getByText('Недопустимое значение')).toBeInTheDocument();
    expect(within(table).getByText('Неверные заголовки столбцов — скачайте шаблон')).toBeInTheDocument();
    expect(within(table).getByText('3')).toBeInTheDocument();
  });

  it('refuses >1 MiB client-side', async () => {
    const srv = server();
    const { user } = renderWithProviders(<ImportDialog entity={ENTITY} branch={3} onClose={() => undefined} />);
    const dialog = await screen.findByRole('dialog');
    const big = csv('big.csv', 'x'.repeat(1_048_577));
    await user.upload(within(dialog).getByLabelText(/Файл/), big);
    expect(await within(dialog).findByText('Файл больше 1 МБ')).toBeInTheDocument();
    await user.click(within(dialog).getByRole('button', { name: 'Загрузить' }));
    expect(srv.calls.some((c) => c.method === 'POST')).toBe(false);
  });

  it('refuses other extensions client-side', async () => {
    const srv = server();
    renderWithProviders(<ImportDialog entity={ENTITY} branch={3} onClose={() => undefined} />);
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText(/Файл/), { target: { files: [new File(['x'], 'a.exe')] } });
    expect(await within(dialog).findByText('Допустимы только файлы .csv и .xlsx')).toBeInTheDocument();
    expect(srv.calls.some((c) => c.method === 'POST')).toBe(false);
  });

  it('downloads template', async () => {
    const srv = server({ 'GET /data/entities/kazna.balance/template.csv': { raw: 'branch_code;balance', headers: { 'Content-Type': 'text/csv' } } });
    const create = vi.fn(() => 'blob:x');
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: create, revokeObjectURL: vi.fn() }));
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    const { user } = renderWithProviders(<ImportDialog entity={ENTITY} branch={3} onClose={() => undefined} />);
    await user.click(await screen.findByRole('button', { name: 'Скачать шаблон (CSV)' }));
    await waitFor(() => expect(click).toHaveBeenCalled());
    expect(create).toHaveBeenCalledTimes(1);
    expect(srv.calls.some((c) => c.path === '/data/entities/kazna.balance/template.csv')).toBe(true);
    click.mockRestore();
  });

  it('has no axe violations', async () => {
    server();
    renderWithProviders(<ImportDialog entity={ENTITY} branch={3} onClose={() => undefined} />);
    const dialog = await screen.findByRole('dialog');
    await expectNoAxeViolations(dialog);
  });
});
