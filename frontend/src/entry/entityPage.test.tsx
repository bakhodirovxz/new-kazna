import { screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { expectNoAxeViolations } from '../test/axe';
import { BRANCHES } from '../test/fixtures';
import { apiError, json, mockApi, type MockHandler } from '../test/mockApi';
import { renderWithProviders } from '../test/render';
import type { EntryEntity, EntryRecord } from './api';
import { EntityPage } from './EntityPage';

const FILTERS = { br: null, per: 'ytd' };

const BALANCE: EntryEntity = {
  id: 'kazna.balance', section: 'kazna', section_title: 'Казначейство', title: 'Остатки на счетах',
  kind: 'fact', layout: 'form', grid: null, can_write: true, can_approve: false,
  fields: [
    { name: 'branch_code', kind: 'ref', title: 'Филиал', required: true, options: [], ref: 'dim_branch', unit: '' },
    { name: 'date', kind: 'date', title: 'Дата', required: true, options: [], unit: '' },
    { name: 'balance', kind: 'money', title: 'Остаток', required: true, options: [], unit: 'млн сум' },
  ],
};

const ACCOUNT: EntryEntity = {
  id: 'kazna.bank_account', section: 'kazna', section_title: 'Казначейство', title: 'Банковские счета',
  kind: 'dim', layout: 'form', grid: null, can_write: true, can_approve: false,
  fields: [
    { name: 'branch_code', kind: 'ref', title: 'Филиал', required: true, options: [], ref: 'dim_branch', unit: '' },
    { name: 'account_number', kind: 'secret', title: 'Номер счёта', required: true, options: [], unit: '' },
  ],
};

const REC: EntryRecord = {
  entry_id: 7, version: 1, branch_id: 3, status: 'active', pending_batch_id: null, shadowed_by: null,
  values: { branch_code: 'CHIRCHIK', date: '2026-09-30', balance: '1500.00' }, masks: {},
};
const PENDING: EntryRecord = { ...REC, entry_id: 8, version: 2, status: 'pending', pending_batch_id: 5,
  values: { ...REC.values, balance: '9.00' } };
const SECRET_REC: EntryRecord = { entry_id: 9, version: 1, branch_id: 3, status: 'active', pending_batch_id: null,
  shadowed_by: null, values: { branch_code: 'CHIRCHIK' }, masks: { account_number: '…9012' } };

function server(entity: EntryEntity, items: EntryRecord[], extra: Record<string, MockHandler> = {}, branches = BRANCHES) {
  return mockApi({
    [`GET /data/entities/${entity.id}/records`]: json({ items, total: items.length, page: 1 }),
    'GET /meta/branches': json(branches),
    ...extra,
  });
}

describe('EntityPage', () => {
  it('renders records and statuses', async () => {
    server(BALANCE, [REC, PENDING]);
    renderWithProviders(<EntityPage entity={BALANCE} filters={FILTERS} />);
    const table = await screen.findByRole('table', { name: 'Остатки на счетах' });
    expect(within(table).getByText('Действует')).toBeInTheDocument();
    expect(within(table).getByText('На согласовании')).toBeInTheDocument();
    expect(within(table).getByText('1 500,00')).toBeInTheDocument();
    expect(within(table).getAllByText('30.09.2026')).toHaveLength(2);
    expect(within(table).queryByText('2026-09-30')).toBeNull();
    expect(screen.getByText(/Сведения, которые 1С не передаёт/)).toBeInTheDocument();
  });

  it('validates money before submit', async () => {
    const srv = server(BALANCE, []);
    const { user } = renderWithProviders(<EntityPage entity={BALANCE} filters={{ br: 3, per: 'ytd' }} />);
    await user.click(await screen.findByRole('button', { name: 'Добавить' }));
    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByLabelText(/Дата/), '2026-09-30');
    await user.type(within(dialog).getByLabelText(/Остаток/), '1,234');
    await user.click(within(dialog).getByRole('button', { name: 'Отправить на согласование' }));
    expect(await within(dialog).findByText('Не более 2 знаков после запятой')).toBeInTheDocument();
    expect(within(dialog).getByLabelText(/Остаток/)).toHaveAttribute('aria-invalid', 'true');
    expect(srv.calls.some((c) => c.method === 'POST')).toBe(false);
  });

  it('submits a new record with a canonical value and keeps no variables in the mutation cache', async () => {
    const srv = server(BALANCE, [], { 'POST /data/batches': json({ batch_id: 1, version: 2 }, 201) });
    const { user, client } = renderWithProviders(<EntityPage entity={BALANCE} filters={{ br: 3, per: 'ytd' }} />);
    await user.click(await screen.findByRole('button', { name: 'Добавить' }));
    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByLabelText(/Дата/), '2026-09-30');
    await user.type(within(dialog).getByLabelText(/Остаток/), '12 345,67');
    await user.click(within(dialog).getByRole('button', { name: 'Отправить на согласование' }));
    await screen.findByText('Отправлено на согласование');
    await waitFor(() => expect(client.getMutationCache().getAll()).toHaveLength(0));
    expect(srv.calls.find((c) => c.method === 'POST')?.body).toEqual({
      entity: 'kazna.balance', branch_id: 3, origin: 'form', submit: true, reason: null,
      items: [{ entry_id: null, expected_version: null, delete: false,
        values: { branch_code: 'CHIRCHIK', date: '2026-09-30', balance: '12345.67' } }],
    });
  });

  it('confirms a submit with a link and warns when the period filter hides the record', async () => {
    // yozuv ro'yxatda yo'q (davr filtri): server pending_batch_id=1 yozuvni qaytarmaydi
    server(BALANCE, [], { 'POST /data/batches': json({ batch_id: 41, version: 2 }, 201) });
    const { user } = renderWithProviders(<EntityPage entity={BALANCE} filters={{ br: 3, per: 'ytd' }} />);
    await user.click(await screen.findByRole('button', { name: 'Добавить' }));
    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByLabelText(/Дата/), '2026-12-31');
    await user.type(within(dialog).getByLabelText(/Остаток/), '5');
    await user.click(within(dialog).getByRole('button', { name: 'Отправить на согласование' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    const notice = (await screen.findAllByRole('status')).find((n) => n.textContent?.includes('пакет №41'));
    expect(notice).toHaveTextContent('Отправлено на согласование: пакет №41');
    expect(within(notice as HTMLElement).getByRole('link', { name: 'Мои пакеты' })).toHaveAttribute('href', '#vvod/batches');
    expect(notice).toHaveTextContent('вне выбранного периода');
  });

  it('does not warn when the submitted record is in the list', async () => {
    let posted = false;
    mockApi({
      'GET /data/entities/kazna.balance/records': () => json({ items: posted ? [{ ...PENDING, pending_batch_id: 42 }] : [], total: 1, page: 1 }),
      'GET /meta/branches': json(BRANCHES),
      'POST /data/batches': () => { posted = true; return json({ batch_id: 42, version: 2 }, 201); },
    });
    const { user } = renderWithProviders(<EntityPage entity={BALANCE} filters={{ br: 3, per: 'ytd' }} />);
    await user.click(await screen.findByRole('button', { name: 'Добавить' }));
    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByLabelText(/Дата/), '2026-09-30');
    await user.type(within(dialog).getByLabelText(/Остаток/), '9');
    await user.click(within(dialog).getByRole('button', { name: 'Отправить на согласование' }));
    const notice = (await screen.findAllByRole('status')).find((n) => n.textContent?.includes('пакет №42'));
    expect(notice).toBeDefined();
    expect(notice).not.toHaveTextContent('вне выбранного периода');
  });

  it('requires a reason and sends it when editing an approved record', async () => {
    const srv = server(BALANCE, [REC], { 'POST /data/batches': json({ batch_id: 2, version: 2 }, 201) });
    const { user } = renderWithProviders(<EntityPage entity={BALANCE} filters={FILTERS} />);
    await user.click(await screen.findByRole('button', { name: 'Редактировать' }));
    const dialog = await screen.findByRole('dialog');
    const balance = within(dialog).getByLabelText(/Остаток/);
    await user.clear(balance);
    await user.type(balance, '1600');
    await user.click(within(dialog).getByRole('button', { name: 'Отправить на согласование' }));
    expect(await within(dialog).findByText('Укажите причину (не короче 5 символов)')).toBeInTheDocument();
    expect(srv.calls.some((c) => c.method === 'POST')).toBe(false);
    await user.type(within(dialog).getByLabelText(/Причина изменения/), 'Уточнение выписки');
    await user.click(within(dialog).getByRole('button', { name: 'Отправить на согласование' }));
    await screen.findByText('Отправлено на согласование');
    const body = srv.calls.find((c) => c.method === 'POST')?.body as { reason: string; items: Array<Record<string, unknown>> };
    expect(body.reason).toBe('Уточнение выписки');
    expect(body.items[0]).toMatchObject({ entry_id: 7, expected_version: 1 });
  });

  it('shows a conflict banner on 409', async () => {
    server(BALANCE, [REC], { 'POST /data/batches': apiError(409, 'conflict_modified') });
    const { user } = renderWithProviders(<EntityPage entity={BALANCE} filters={FILTERS} />);
    await user.click(await screen.findByRole('button', { name: 'Редактировать' }));
    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByLabelText(/Причина изменения/), 'Уточнение выписки');
    await user.click(within(dialog).getByRole('button', { name: 'Отправить на согласование' }));
    const alert = await within(dialog).findByRole('alert');
    expect(alert).toHaveTextContent('Запись изменена другим пользователем, обновите страницу');
    expect(within(alert).getByRole('button', { name: 'Обновить' })).toBeInTheDocument();
  });

  it('offers the existing record on duplicate_record', async () => {
    server(BALANCE, [REC], { 'POST /data/batches': apiError(409, 'duplicate_record', 'x', { entry_id: 7 }) });
    const { user } = renderWithProviders(<EntityPage entity={BALANCE} filters={{ br: 3, per: 'ytd' }} />);
    await user.click(await screen.findByRole('button', { name: 'Добавить' }));
    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByLabelText(/Дата/), '2026-09-30');
    await user.type(within(dialog).getByLabelText(/Остаток/), '1');
    await user.click(within(dialog).getByRole('button', { name: 'Отправить на согласование' }));
    expect(await within(dialog).findByRole('button', { name: 'Открыть существующую запись' })).toBeInTheDocument();
  });

  it('never prefills a secret field and keeps it write-only', async () => {
    const srv = server(ACCOUNT, [SECRET_REC], { 'POST /data/batches': json({ batch_id: 3, version: 2 }, 201) });
    const { user } = renderWithProviders(<EntityPage entity={ACCOUNT} filters={FILTERS} />);
    expect(await screen.findByText('…9012')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Редактировать' }));
    const dialog = await screen.findByRole('dialog');
    const secret = within(dialog).getByLabelText(/Номер счёта/);
    expect(secret).toHaveValue('');
    expect(secret).toHaveAttribute('type', 'password');
    expect(secret).toHaveAttribute('autocomplete', 'off');
    expect(dialog).toHaveTextContent('…9012 — оставьте пустым, чтобы не менять');
    await user.type(within(dialog).getByLabelText(/Причина изменения/), 'Смена реквизита');
    await user.click(within(dialog).getByRole('button', { name: 'Отправить на согласование' }));
    await screen.findByText('Отправлено на согласование');
    const items = (srv.calls.find((c) => c.method === 'POST')?.body as { items: Array<{ values: object }> }).items;
    expect(items[0]?.values).not.toHaveProperty('account_number');
  });

  it('history shows before and after', async () => {
    server(BALANCE, [REC], {
      'GET /data/records/7/history': json({ versions: [
        { version: 2, batch_id: 2, batch_status: 'approved', created_by_name: 'Иванов', created_at: '2026-10-02T10:00:00Z',
          decided_by_name: 'Петров', decided_at: '2026-10-02T11:00:00Z', reason: 'Уточнение выписки', deleted: false,
          values: { ...REC.values, balance: '1600.00' }, masks: {} },
        { version: 1, batch_id: 1, batch_status: 'approved', created_by_name: 'Иванов', created_at: '2026-10-01T10:00:00Z',
          decided_by_name: 'Петров', decided_at: '2026-10-01T11:00:00Z', reason: null, deleted: false,
          values: REC.values, masks: {} },
      ] }),
    });
    const { user } = renderWithProviders(<EntityPage entity={BALANCE} filters={FILTERS} />);
    await user.click(await screen.findByRole('button', { name: 'История изменений' }));
    const dialog = await screen.findByRole('dialog', { name: 'История изменений' });
    const items = await within(dialog).findAllByRole('listitem');
    expect(items.length).toBeGreaterThan(2);
    expect(dialog.querySelector('del')).toHaveTextContent('1500,00');
    expect(dialog.querySelector('ins')).toHaveTextContent('1600,00');
    expect(dialog).toHaveTextContent('Уточнение выписки');
  });

  it('lets a branch-locked user pick only their own branch', async () => {
    server(BALANCE, [], {}, BRANCHES.filter((b) => b.id === 3));
    const { user } = renderWithProviders(<EntityPage entity={BALANCE} filters={{ br: null, per: 'ytd' }} />);
    await user.click(await screen.findByRole('button', { name: 'Добавить' }));
    const dialog = await screen.findByRole('dialog');
    const select = await within(dialog).findByLabelText(/Филиал/);
    expect(select).toBeDisabled();
    expect(select).toHaveValue('CHIRCHIK');
    expect(within(select).queryByRole('option', { name: 'Андижанская ГЭС' })).toBeNull();
  });

  it('has no axe violations (page and drawer)', async () => {
    server(BALANCE, [REC]);
    const { user, container } = renderWithProviders(<EntityPage entity={BALANCE} filters={FILTERS} />);
    await screen.findByRole('table');
    await expectNoAxeViolations(container);
    await user.click(screen.getByRole('button', { name: 'Редактировать' }));
    await expectNoAxeViolations(await screen.findByRole('dialog'));
  });
});
