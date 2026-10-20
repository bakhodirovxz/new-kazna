import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { AuditOut } from '../api/types';
import { expectNoAxeViolations } from '../test/axe';
import { apiError, json, mockApi, type MockHandler } from '../test/mockApi';
import { renderWithProviders } from '../test/render';
import AuditPage from './AuditPage';

const ROWS: AuditOut[] = [
  {
    id: 101, ts: '2026-09-24T05:07:00Z', user_id: 1, username: 'admin', action: 'auth.login.success', result: 'ok',
    object_type: null, object_id: null, request_id: 'r1', details: { method: 'totp' }, ip: '10.0.0.5',
  },
  {
    id: 100, ts: '2026-09-24T05:06:00Z', user_id: null, username: null, action: 'auth.login.fail', result: 'fail',
    object_type: 'user', object_id: 'ghost', request_id: 'r0', details: { reason: 'bad_password' }, ip: null,
  },
];

function routes(extra: Record<string, MockHandler> = {}) {
  return mockApi({ 'GET /audit': json({ items: ROWS, total: 2, page: 1, page_size: 100 }), ...extra });
}

describe('AuditPage', () => {
  it('lists records and shows details', async () => {
    routes();
    const { user } = renderWithProviders(<AuditPage />);
    const table = await screen.findByRole('table', { name: 'Журнал аудита' });
    expect(table).toHaveTextContent('24.09.2026 10:07');
    expect(table).toHaveTextContent('auth.login.fail');
    expect(table).toHaveTextContent('Ошибка');
    expect(table).toHaveTextContent('user:ghost');
    await user.click(within(table).getByText('auth.login.success'));
    const dialog = screen.getByRole('dialog', { name: 'Запись журнала №101' });
    expect(dialog).toHaveTextContent('"method": "totp"');
  });

  it('applies filters to the query', async () => {
    const server = routes();
    const { user } = renderWithProviders(<AuditPage />);
    await screen.findByRole('table', { name: 'Журнал аудита' });
    fireEvent.change(screen.getByLabelText('С'), { target: { value: '2026-09-01' } });
    fireEvent.change(screen.getByLabelText('По'), { target: { value: '2026-09-24' } });
    await user.type(screen.getByLabelText('Действие (начало кода)'), 'auth.login');
    await user.selectOptions(screen.getByLabelText('Результат'), 'fail');
    await user.click(screen.getByRole('button', { name: 'Применить' }));
    await waitFor(() => expect(server.calls.some((c) => c.url.searchParams.get('action') === 'auth.login')).toBe(true));
    const call = server.calls.filter((c) => c.path === '/audit').at(-1);
    expect(call?.url.searchParams.get('from_ts')).toBe('2026-08-31T19:00:00.000Z');
    expect(call?.url.searchParams.get('to_ts')).toBe('2026-09-24T19:00:00.000Z');
    expect(call?.url.searchParams.get('result')).toBe('fail');
  });

  describe('CSV export', () => {
    function stubDownload() {
      const create = vi.fn(() => 'blob:mock-1');
      const revoke = vi.fn();
      vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: create, revokeObjectURL: revoke }));
      const names: string[] = [];
      const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
        names.push(`${this.download}|${this.href}`);
      });
      return { create, revoke, names, click };
    }

    it('downloads through fetch and a revoked object URL with the applied filters, no data in the page URL', async () => {
      const dl = stubDownload();
      const server = routes({
        'GET /audit/export.csv': { status: 200, body: undefined, headers: { 'Content-Type': 'text/csv' } },
      });
      const { user } = renderWithProviders(<AuditPage />);
      await screen.findByRole('table', { name: 'Журнал аудита' });
      expect(screen.queryByRole('link', { name: 'Выгрузить CSV' })).not.toBeInTheDocument();
      await user.type(screen.getByLabelText('Действие (начало кода)'), 'auth.login');
      await user.click(screen.getByRole('button', { name: 'Применить' }));
      await user.click(screen.getByRole('button', { name: 'Выгрузить CSV' }));
      expect(dl.revoke).not.toHaveBeenCalled(); // darhol emas: brauzerga yuklashni boshlashga vaqt
      await waitFor(() => expect(dl.revoke).toHaveBeenCalledWith('blob:mock-1'), { timeout: 3000 });
      const call = server.calls.find((c) => c.path === '/audit/export.csv');
      expect(call?.url.searchParams.get('action')).toBe('auth.login');
      expect(call?.url.searchParams.has('page')).toBe(false);
      expect(dl.names[0]).toMatch(/^audit_\d{8}_\d{4}\.csv\|blob:mock-1$/);
      expect(window.location.href).not.toContain('export');
      dl.click.mockRestore();
    });

    it('shows the retry time on 429 and a notice when the file is truncated', async () => {
      const dl = stubDownload();
      let call = 0;
      routes({
        'GET /audit/export.csv': () => {
          call += 1;
          return call === 1
            ? apiError(429, 'rate_limited', 'Слишком много запросов', undefined, { 'Retry-After': '42' })
            : { status: 200, headers: { 'Content-Type': 'text/csv', 'X-Export-Truncated': 'true' } };
        },
      });
      const { user } = renderWithProviders(<AuditPage />);
      await user.click(await screen.findByRole('button', { name: 'Выгрузить CSV' }));
      expect(await screen.findByRole('alert')).toHaveTextContent('Повторите через 42 с');
      await user.click(screen.getByRole('button', { name: 'Выгрузить CSV' }));
      expect(await screen.findByText(/усечена/)).toBeInTheDocument();
      await waitFor(() => expect(dl.revoke).toHaveBeenCalledTimes(1), { timeout: 3000 });
      dl.click.mockRestore();
    });
  });

  it('validates filters before querying', async () => {
    const server = routes();
    const { user } = renderWithProviders(<AuditPage />);
    await screen.findByRole('table', { name: 'Журнал аудита' });
    const before = server.calls.length;
    await user.type(screen.getByLabelText('Действие (начало кода)'), 'Auth Login');
    fireEvent.change(screen.getByLabelText('С'), { target: { value: '2026-09-24' } });
    fireEvent.change(screen.getByLabelText('По'), { target: { value: '2026-09-01' } });
    await user.click(screen.getByRole('button', { name: 'Применить' }));
    expect(screen.getByText('Латинские строчные буквы, точка и «_»', { selector: '.field__error' })).toBeInTheDocument();
    expect(screen.getByText('Дата «С» позже даты «По»')).toBeInTheDocument();
    expect(server.calls.length).toBe(before);
  });

  it('verifies the hash chain', async () => {
    let call = 0;
    routes({
      'POST /audit/verify': () => {
        call += 1;
        return call === 1
          ? json({ ok: true, checked: 2, first_bad_id: null, bad_ids: [] })
          : json({ ok: false, checked: 10, first_bad_id: 7, bad_ids: [7, 8] });
      },
    });
    const { user } = renderWithProviders(<AuditPage />);
    await user.click(await screen.findByRole('button', { name: 'Проверить целостность' }));
    expect(await screen.findByText('Цепочка записей не нарушена. Проверено записей: 2.')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Проверить целостность' }));
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('первая изменённая запись №7');
    expect(alert).toHaveTextContent('Записи с нарушениями: 7, 8');
  });

  it('has no axe violations', async () => {
    routes();
    const { container } = renderWithProviders(<AuditPage />);
    await screen.findByRole('table', { name: 'Журнал аудита' });
    await expectNoAxeViolations(container);
  });
});

describe('AuditPage filters', () => {
  it('rejects user id 0 and keeps verify output bounded', async () => {
    const ids = Array.from({ length: 80 }, (_, i) => i + 1);
    const server = routes({ 'POST /audit/verify': json({ ok: false, checked: 100, first_bad_id: 1, bad_ids: ids }) });
    const { user } = renderWithProviders(<AuditPage />);
    await screen.findByRole('table', { name: 'Журнал аудита' });
    const before = server.calls.length;
    await user.type(screen.getByLabelText('ID пользователя'), '0');
    await user.click(screen.getByRole('button', { name: 'Применить' }));
    expect(screen.getByText('Только цифры')).toBeInTheDocument();
    expect(server.calls.length).toBe(before);
    await user.click(screen.getByRole('button', { name: 'Проверить целостность' }));
    const alert = await screen.findByRole('alert', {}, { timeout: 3000 });
    expect(alert).toHaveTextContent('и ещё 30');
  });
});
