import { screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { expectNoAxeViolations } from '../test/axe';
import { BRANCHES, ME_ADMIN } from '../test/fixtures';
import { apiError, json, mockApi, type MockHandler } from '../test/mockApi';
import { renderWithProviders } from '../test/render';
import type { EntryBatch, EntryBatchDetail, EntryEntity } from './api';
import { BatchList } from './BatchList';

const ENTITY: EntryEntity = {
  id: 'kazna.balance', section: 'kazna', section_title: 'Казначейство', title: 'Остатки на счетах',
  kind: 'fact', layout: 'form', grid: null, can_write: true, can_approve: true,
  fields: [
    { name: 'date', kind: 'date', title: 'Дата', required: true, options: [], unit: '' },
    { name: 'balance', kind: 'money', title: 'Остаток', required: true, options: [], unit: 'млн сум' },
  ],
};

const BATCH: EntryBatch = {
  batch_id: 5, entity: 'kazna.balance', branch_id: 3, status: 'submitted', origin: 'form', rows: 1, reason: null,
  created_by: 99, created_at: '2026-10-01T10:00:00Z', submitted_at: '2026-10-01T10:05:00Z',
  decided_by: null, decided_at: null, decision_comment: null, version: 2, etl_request_id: null,
};
const DETAIL: EntryBatchDetail = {
  ...BATCH,
  items: [{ entry_id: 7, version: 2, op: 'change',
    before: { date: '2026-09-30', balance: '1500.00' }, after: { date: '2026-09-30', balance: '1600.00' } }],
  publication: { status: 'none', build_id: null },
};

function server(extra: Record<string, MockHandler> = {}, me = { ...ME_ADMIN, id: 1 }) {
  return mockApi({
    'GET /auth/me': json(me),
    'GET /data/entities': json([ENTITY]),
    'GET /meta/branches': json(BRANCHES),
    'GET /data/batches': json({ items: [BATCH], total: 1, page: 1 }),
    'GET /data/batches/5': json(DETAIL),
    ...extra,
  });
}

async function open(user: ReturnType<typeof renderWithProviders>['user']) {
  await user.click(await screen.findByRole('button', { name: 'Пакет №5' }));
  return screen.findByRole('heading', { name: 'Пакет №5' });
}

describe('batches', () => {
  it('approver sees the inbox and approves', async () => {
    const srv = server({ 'POST /data/batches/5/approve': json({ ...BATCH, status: 'approved', version: 3 }) });
    const { user } = renderWithProviders(<BatchList box="inbox" />);
    expect(await screen.findByRole('table', { name: 'На согласовании' })).toBeInTheDocument();
    await open(user);
    expect(document.querySelector('del')).toHaveTextContent('1 500,00');
    expect(document.querySelector('ins')).toHaveTextContent('1 600,00');
    expect(screen.getByText('изменена')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Утвердить' }));
    await screen.findByText('Утверждено');
    expect(srv.calls.find((c) => c.path === '/data/batches/5/approve')?.body).toEqual({ expected_version: 2, comment: null });
  });

  it('shows «Ошибка публикации» with the failed check on list and page', async () => {
    const failed = { ...BATCH, status: 'failed', publish_error: 'Проверки качества не пройдены: balance_identity (запуск №7)' };
    server({
      'GET /data/batches': json({ items: [failed], total: 1, page: 1 }),
      'GET /data/batches/5': json({ ...DETAIL, ...failed, publication: { status: 'failed', build_id: null } }),
    });
    const { user } = renderWithProviders(<BatchList box="mine" />);
    expect(await screen.findAllByText('Ошибка публикации')).not.toHaveLength(0);
    expect(screen.getByText(/balance_identity/)).toBeInTheDocument();
    await open(user);
    expect(screen.getAllByText('Ошибка публикации').length).toBeGreaterThan(0);
    expect(screen.getByText(/balance_identity/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Утвердить' })).not.toBeInTheDocument();
  });

  it('status filter starts with «Все»', async () => {
    server();
    renderWithProviders(<BatchList box="mine" />);
    const select = await screen.findByRole('combobox', { name: /Статус/ });
    expect(within(select).getAllByRole('option')[0]).toHaveTextContent('Все');
  });

  it('formats dates and money in the diff', async () => {
    const added = { ...DETAIL, items: [{ entry_id: 7, version: 1, op: 'add' as const, before: null, after: { date: '2026-09-30', balance: '1600.00' } }] };
    server({ 'GET /data/batches/5': json(added) });
    const { user } = renderWithProviders(<BatchList box="inbox" />);
    await open(user);
    expect(screen.getByText('30.09.2026')).toBeInTheDocument();
    expect(screen.getByText('1 600,00')).toBeInTheDocument();
    expect(screen.getByText('новая')).toBeInTheDocument();
  });

  it('reject requires a comment', async () => {
    const srv = server({ 'POST /data/batches/5/reject': json({ ...BATCH, status: 'rejected' }) });
    const { user } = renderWithProviders(<BatchList box="inbox" />);
    await open(user);
    await user.click(screen.getByRole('button', { name: 'Отклонить' }));
    const dialog = await screen.findByRole('dialog', { name: 'Отклонить пакет' });
    await user.click(within(dialog).getByRole('button', { name: 'Отклонить' }));
    expect(await within(dialog).findByText('Укажите причину (не короче 5 символов)')).toBeInTheDocument();
    expect(srv.calls.some((c) => c.method === 'POST')).toBe(false);
    await user.type(within(dialog).getByLabelText(/Комментарий/), 'Не сходится с выпиской');
    await user.click(within(dialog).getByRole('button', { name: 'Отклонить' }));
    await screen.findByText('Отклонено');
    expect(srv.calls.find((c) => c.method === 'POST')?.body).toEqual({ expected_version: 2, comment: 'Не сходится с выпиской' });
  });

  it('own batch has no approve button', async () => {
    server({}, { ...ME_ADMIN, id: 99 });
    const { user } = renderWithProviders(<BatchList box="inbox" />);
    await open(user);
    expect(screen.queryByRole('button', { name: 'Утвердить' })).toBeNull();
    expect(screen.getByText('Согласовать может другой сотрудник с правом согласования')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Отозвать' })).toBeInTheDocument();
  });

  it('shows the server error when approval is refused', async () => {
    server({ 'POST /data/batches/5/approve': apiError(409, 'conflict_modified') });
    const { user } = renderWithProviders(<BatchList box="inbox" />);
    await open(user);
    await user.click(screen.getByRole('button', { name: 'Утвердить' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Запись изменена другим пользователем');
  });

  it('publication status polls until published', async () => {
    let n = 0;
    server({
      'GET /data/batches/5': () => {
        n += 1;
        const status = n < 2 ? 'queued' : 'published';
        return json({ ...DETAIL, status: 'approved', publication: { status, build_id: status === 'published' ? 12 : null } });
      },
    });
    // vitest таймеры реальные: интервал 5 с слишком велик, поэтому проверяем только начальный и ручной refetch
    const { user, client } = renderWithProviders(<BatchList box="mine" />);
    await open(user);
    expect(await screen.findByText('Ожидает публикации')).toBeInTheDocument();
    await client.invalidateQueries({ queryKey: ['entry', 'batches', 'one', 5] });
    expect(await screen.findByText('Опубликовано (сборка №12)')).toBeInTheDocument();
  });

  it('has no axe violations', async () => {
    server();
    const { user, container } = renderWithProviders(<BatchList box="inbox" />);
    await screen.findByRole('table');
    await expectNoAxeViolations(container);
    await open(user);
    await expectNoAxeViolations(container);
  });
});
