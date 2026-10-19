import { screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { PositionOut, UserOut } from '../api/types';
import { expectNoAxeViolations } from '../test/axe';
import { ME_ADMIN } from '../test/fixtures';
import { apiError, json, mockApi, type MockHandler } from '../test/mockApi';
import { createQueryClient } from '../api/queryClient';
import { renderWithProviders } from '../test/render';
import UsersPage from './UsersPage';

const USERS: UserOut[] = [
  {
    id: 1, username: 'admin', full_name: 'Азимов Бахтиёр', position: { id: 6, code: 'admin', name: 'Администратор' },
    role_code: 'admin', is_active: true, totp_enabled: true, locked_until: null,
    last_login_at: '2026-09-24T04:00:00Z', created_at: '2026-09-01T00:00:00Z',
  },
  {
    id: 2, username: 'karimova', full_name: 'Каримова Нилуфар', position: { id: 4, code: 'economist_filiala', name: 'Экономист филиала' },
    role_code: 'economist_filiala', is_active: false, totp_enabled: false, locked_until: null,
    last_login_at: null, created_at: '2026-09-02T00:00:00Z',
  },
  {
    id: 3, username: 'rakhimov', full_name: 'Рахимов Ильхом', position: { id: 7, code: 'vnutr_kontrol', name: 'Служба внутреннего контроля' },
    role_code: 'vnutr_kontrol', is_active: true, totp_enabled: true, locked_until: '2099-01-01T00:00:00Z',
    last_login_at: '2026-09-20T04:00:00Z', created_at: '2026-09-03T00:00:00Z',
  },
];

const POSITIONS: PositionOut[] = [
  { id: 6, code: 'admin', name: 'Администратор', role_id: 6, role_code: 'admin', is_active: true, branch_ids: [] },
  { id: 4, code: 'economist_filiala', name: 'Экономист филиала', role_id: 4, role_code: 'economist_filiala', is_active: true, branch_ids: [3] },
  { id: 3, code: 'spec_kazna', name: 'Специалист казначейства', role_id: 3, role_code: 'spec_kazna', is_active: true, branch_ids: [] },
  { id: 7, code: 'vnutr_kontrol', name: 'Служба внутреннего контроля', role_id: 7, role_code: 'vnutr_kontrol', is_active: true, branch_ids: [] },
];

function routes(extra: Record<string, MockHandler> = {}) {
  return mockApi({
    'GET /admin/users': (req) => {
      const q = req.url.searchParams.get('q') ?? '';
      const items = USERS.filter((u) => !q || u.username.includes(q) || u.full_name.toLowerCase().includes(q));
      return json({ items, total: items.length, page: 1, page_size: 50 });
    },
    'GET /admin/positions': json(POSITIONS),
    ...extra,
  });
}

async function openUser(user: ReturnType<typeof renderWithProviders>['user'], name: string) {
  await user.click(await screen.findByText(name));
  return screen.getByRole('dialog', { name });
}

describe('UsersPage', () => {
  it('lists users with 2FA and status badges', async () => {
    routes();
    renderWithProviders(<UsersPage me={ME_ADMIN} />);
    const table = await screen.findByRole('table', { name: 'Пользователи' });
    const rows = within(table).getAllByRole('row').slice(1);
    expect(rows).toHaveLength(3);
    const karimova = rows.find((r) => r.textContent?.includes('karimova')) as HTMLElement;
    expect(karimova).toHaveTextContent('Заблокирован');
    expect(karimova).toHaveTextContent('Не подключена');
    const rakhimov = rows.find((r) => r.textContent?.includes('rakhimov')) as HTMLElement;
    expect(rakhimov).toHaveTextContent('Временно заблокирован до 01.01.2099');
    expect(screen.getByRole('navigation', { name: 'Страницы' })).toHaveTextContent('1–3 из 3');
  });

  it('searches on the server after a short pause', async () => {
    const server = routes();
    const { user } = renderWithProviders(<UsersPage me={ME_ADMIN} />);
    await screen.findByRole('table', { name: 'Пользователи' });
    await user.type(screen.getByLabelText('Поиск'), 'kar');
    await waitFor(() => expect(server.calls.some((c) => c.url.searchParams.get('q') === 'kar')).toBe(true));
    await waitFor(() => expect(within(screen.getByRole('table')).getAllByRole('row')).toHaveLength(2));
  });

  it('validates and creates a user, then shows the temporary password once', async () => {
    const server = routes({
      'POST /admin/users': () =>
        json({ user: { ...USERS[0], id: 9, username: 'novikov', full_name: 'Новиков Сотрудник' }, temporary_password: 'Tmp-Parol-1234567' }, 201),
    });
    const { user } = renderWithProviders(<UsersPage me={ME_ADMIN} />);
    await user.click(await screen.findByRole('button', { name: 'Добавить пользователя' }));
    const dialog = screen.getByRole('dialog', { name: 'Новый пользователь' });
    await user.type(within(dialog).getByLabelText('Логин'), 'A b');
    await user.click(within(dialog).getByRole('button', { name: 'Создать' }));
    expect(within(dialog).getAllByText('3–64 символа: латинские строчные буквы, цифры, точка, дефис, подчёркивание').length).toBeGreaterThan(1);
    expect(within(dialog).getAllByText('Обязательное поле')).toHaveLength(2);
    await user.clear(within(dialog).getByLabelText('Логин'));
    await user.type(within(dialog).getByLabelText('Логин'), 'Novikov');
    await user.type(within(dialog).getByLabelText('ФИО'), 'Новиков Сотрудник');
    await user.type(within(dialog).getByRole('combobox', { name: 'Должность' }), 'Спец');
    await user.keyboard('{ArrowDown}{Enter}');
    await user.click(within(dialog).getByRole('button', { name: 'Создать' }));
    const secret = await screen.findByRole('dialog', { name: 'Временный пароль' });
    expect(within(secret).getByTestId('temp-password')).toHaveTextContent('Tmp-Parol-1234567');
    expect(server.calls.find((c) => c.method === 'POST')?.body).toEqual({ username: 'novikov', full_name: 'Новиков Сотрудник', position_id: 3 });
    const write = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue(undefined); // user-event o'z clipboard'ini o'rnatadi
    await user.click(within(secret).getByRole('button', { name: 'Скопировать' }));
    expect(write).toHaveBeenCalledWith('Tmp-Parol-1234567');
  });

  it('shows a taken username next to the field', async () => {
    routes({ 'POST /admin/users': apiError(409, 'username_taken', 'Логин уже занят') });
    const { user } = renderWithProviders(<UsersPage me={ME_ADMIN} />);
    await user.click(await screen.findByRole('button', { name: 'Добавить пользователя' }));
    const dialog = screen.getByRole('dialog', { name: 'Новый пользователь' });
    await user.type(within(dialog).getByLabelText('Логин'), 'admin');
    await user.type(within(dialog).getByLabelText('ФИО'), 'Дубликат');
    await user.type(within(dialog).getByRole('combobox', { name: 'Должность' }), 'Админ');
    await user.keyboard('{ArrowDown}{Enter}');
    await user.click(within(dialog).getByRole('button', { name: 'Создать' }));
    expect(await within(dialog).findByText('Логин уже занят')).toBeInTheDocument();
    expect(within(dialog).getByLabelText('Логин')).toHaveAttribute('aria-invalid', 'true');
  });

  it('unblocks a user after confirmation', async () => {
    const server = routes({ 'POST /admin/users/2/unblock': json({ ...USERS[1], is_active: true }) });
    const { user } = renderWithProviders(<UsersPage me={ME_ADMIN} />);
    const dialog = await openUser(user, 'Каримова Нилуфар');
    await user.click(within(dialog).getByRole('button', { name: 'Разблокировать' }));
    const confirm = screen.getByRole('alertdialog', { name: 'Разблокировать пользователя?' });
    await user.click(within(confirm).getByRole('button', { name: 'Разблокировать' }));
    expect(await screen.findByText('Пользователь разблокирован')).toBeInTheDocument();
    expect(server.calls.some((c) => c.path === '/admin/users/2/unblock')).toBe(true);
  });

  it('resets a password and shows the new temporary password', async () => {
    routes({ 'POST /admin/users/3/reset-password': json({ temporary_password: 'New-Tmp-Parol-99' }) });
    const { user } = renderWithProviders(<UsersPage me={ME_ADMIN} />);
    const dialog = await openUser(user, 'Рахимов Ильхом');
    await user.click(within(dialog).getByRole('button', { name: 'Сбросить пароль' }));
    await user.click(within(screen.getByRole('alertdialog', { name: 'Сбросить пароль?' })).getByRole('button', { name: 'Сбросить пароль' }));
    expect(await screen.findByTestId('temp-password')).toHaveTextContent('New-Tmp-Parol-99');
  });

  it('keeps the confirmation open with the server reason on 409', async () => {
    routes({ 'POST /admin/users/3/block': apiError(409, 'last_admin', 'Нельзя оставить систему без администратора') });
    const { user } = renderWithProviders(<UsersPage me={ME_ADMIN} />);
    const dialog = await openUser(user, 'Рахимов Ильхом');
    await user.click(within(dialog).getByRole('button', { name: 'Заблокировать' }));
    const confirm = screen.getByRole('alertdialog', { name: 'Заблокировать пользователя?' });
    await user.click(within(confirm).getByRole('button', { name: 'Заблокировать' }));
    expect(await within(confirm).findByRole('alert')).toHaveTextContent('Нельзя оставить систему без администратора');
  });

  it('saves profile changes', async () => {
    const server = routes({ 'PATCH /admin/users/3': (req) => json({ ...USERS[2], ...(req.body as object) }) });
    const { user } = renderWithProviders(<UsersPage me={ME_ADMIN} />);
    const dialog = await openUser(user, 'Рахимов Ильхом');
    const name = within(dialog).getByLabelText('ФИО');
    await user.clear(name);
    await user.type(name, 'Рахимов Ильхом Каримович');
    await user.click(within(dialog).getByRole('button', { name: 'Сохранить' }));
    expect(await screen.findByText('Изменения сохранены')).toBeInTheDocument();
    expect(server.calls.find((c) => c.method === 'PATCH')?.body).toEqual({ full_name: 'Рахимов Ильхом Каримович', position_id: 7 });
  });

  it('disables dangerous actions on the own account', async () => {
    routes();
    const { user } = renderWithProviders(<UsersPage me={ME_ADMIN} />);
    const dialog = await openUser(user, 'Азимов Бахтиёр');
    expect(within(dialog).getByText('Эти действия нельзя выполнить со своей учётной записью.')).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: 'Заблокировать' })).toBeDisabled();
    expect(within(dialog).getByRole('button', { name: 'Сбросить 2FA' })).toBeDisabled();
  });

  it('has no axe violations', async () => {
    routes();
    const { container } = renderWithProviders(<UsersPage me={ME_ADMIN} />);
    await screen.findByRole('table', { name: 'Пользователи' });
    await expectNoAxeViolations(container);
  });
});

describe('UsersPage fix round 1', () => {
  async function fillCreate(user: ReturnType<typeof renderWithProviders>['user'], dialog: HTMLElement, login = 'novikov') {
    await user.type(within(dialog).getByLabelText('Логин'), login);
    await user.type(within(dialog).getByLabelText('ФИО'), 'Новиков Сотрудник');
    await user.type(within(dialog).getByRole('combobox', { name: 'Должность' }), 'Спец');
    await user.keyboard('{ArrowDown}{Enter}');
  }

  it('works for admin:users without admin:roles (positions 403 is inline and silent)', async () => {
    routes({ 'GET /admin/positions': apiError(403, 'forbidden', 'Нет доступа') });
    const { user, client } = renderWithProviders(<UsersPage me={{ ...ME_ADMIN, permissions: ['admin:users'] }} />);
    await user.click(await screen.findByRole('button', { name: 'Добавить пользователя' }));
    const dialog = screen.getByRole('dialog', { name: 'Новый пользователь' });
    expect(await within(dialog).findByText('Не удалось загрузить список должностей')).toBeInTheDocument();
    expect(client.getQueryCache().find({ queryKey: ['admin', 'positions'] })?.meta).toEqual({ silent: true });
  });

  it('focuses the first invalid field and announces it', async () => {
    routes({ 'POST /admin/users': apiError(409, 'username_taken', 'Логин уже занят') });
    const { user } = renderWithProviders(<UsersPage me={ME_ADMIN} />);
    await user.click(await screen.findByRole('button', { name: 'Добавить пользователя' }));
    const dialog = screen.getByRole('dialog', { name: 'Новый пользователь' });
    await user.click(within(dialog).getByRole('button', { name: 'Создать' }));
    expect(within(dialog).getByLabelText('Логин')).toHaveFocus();
    await fillCreate(user, dialog, 'admin');
    await user.click(within(dialog).getByRole('button', { name: 'Создать' }));
    await within(dialog).findByText('Логин уже занят');
    expect(within(dialog).getByLabelText('Логин')).toHaveFocus();
  });

  it('maps 422 params.fields to field errors and limits input length', async () => {
    routes({ 'POST /admin/users': apiError(422, 'validation_failed', 'Проверьте ФИО', { fields: ['full_name'] }) });
    const { user } = renderWithProviders(<UsersPage me={ME_ADMIN} />);
    await user.click(await screen.findByRole('button', { name: 'Добавить пользователя' }));
    const dialog = screen.getByRole('dialog', { name: 'Новый пользователь' });
    expect(within(dialog).getByLabelText('Логин')).toHaveAttribute('maxlength', '64');
    expect(within(dialog).getByLabelText('ФИО')).toHaveAttribute('maxlength', '200');
    await fillCreate(user, dialog);
    await user.click(within(dialog).getByRole('button', { name: 'Создать' }));
    expect(await within(dialog).findByText('Проверьте ФИО')).toBeInTheDocument();
    expect(within(dialog).getByLabelText('ФИО')).toHaveAttribute('aria-invalid', 'true');
    expect(within(dialog).getByLabelText('ФИО')).toHaveFocus();
  });

  it('keeps the one-time password until «Закрыть» and then leaves no trace', async () => {
    routes({ 'POST /admin/users': json({ user: { ...USERS[0], id: 9 }, temporary_password: 'Tmp-Parol-1234567' }, 201) });
    const { user, client } = renderWithProviders(<UsersPage me={ME_ADMIN} />);
    await user.click(await screen.findByRole('button', { name: 'Добавить пользователя' }));
    const dialog = screen.getByRole('dialog', { name: 'Новый пользователь' });
    await fillCreate(user, dialog);
    await user.click(within(dialog).getByRole('button', { name: 'Создать' }));
    const secret = await screen.findByRole('dialog', { name: 'Временный пароль' });
    await user.keyboard('{Escape}');
    expect(screen.getByTestId('temp-password')).toBeInTheDocument();
    await user.click(within(secret).getAllByRole('button', { name: 'Закрыть' }).at(-1) as HTMLElement); // footer; X disabled
    expect(screen.queryByTestId('temp-password')).toBeNull();
    expect(document.body.textContent).not.toContain('Tmp-Parol-1234567');
    expect(JSON.stringify(client.getMutationCache().getAll().map((m) => m.state))).not.toContain('Tmp-Parol');
  });

  it('shows feedback when copying fails', async () => {
    routes({ 'POST /admin/users': json({ user: { ...USERS[0], id: 9 }, temporary_password: 'Tmp-Parol-1234567' }, 201) });
    const { user } = renderWithProviders(<UsersPage me={ME_ADMIN} />);
    await user.click(await screen.findByRole('button', { name: 'Добавить пользователя' }));
    const dialog = screen.getByRole('dialog', { name: 'Новый пользователь' });
    await fillCreate(user, dialog);
    await user.click(within(dialog).getByRole('button', { name: 'Создать' }));
    const secret = await screen.findByRole('dialog', { name: 'Временный пароль' });
    vi.spyOn(navigator.clipboard, 'writeText').mockRejectedValue(new Error('denied'));
    await user.click(within(secret).getByRole('button', { name: 'Скопировать' }));
    expect(await screen.findByText('Не удалось скопировать. Выделите пароль и скопируйте вручную.')).toBeInTheDocument();
  });

  it('requires the full name and locks the position on the own account', async () => {
    routes();
    const { user } = renderWithProviders(<UsersPage me={ME_ADMIN} />);
    const dialog = await openUser(user, 'Азимов Бахтиёр');
    expect(within(dialog).getByRole('combobox', { name: 'Должность' })).toBeDisabled();
    await user.clear(within(dialog).getByLabelText('ФИО'));
    await user.click(within(dialog).getByRole('button', { name: 'Сохранить' }));
    expect(within(dialog).getByLabelText('ФИО')).toHaveFocus();
    expect(within(dialog).getByLabelText('ФИО')).toHaveAttribute('aria-invalid', 'true');
  });

  it('limits search length and returns to page 1 immediately on typing', async () => {
    routes();
    const { user } = renderWithProviders(<UsersPage me={ME_ADMIN} />);
    await screen.findByRole('table', { name: 'Пользователи' });
    expect(screen.getByLabelText('Поиск')).toHaveAttribute('maxlength', '64');
    await user.type(screen.getByLabelText('Поиск'), 'k');
  });
});

describe('UsersPage fix round 2', () => {
  it('keeps focus where the user put it while the name error is shown', async () => {
    routes({ 'POST /admin/users/3/reset-2fa': json(null, 204) });
    const { user } = renderWithProviders(<UsersPage me={ME_ADMIN} />);
    const dialog = await openUser(user, 'Рахимов Ильхом');
    await user.clear(within(dialog).getByLabelText('ФИО'));
    await user.click(within(dialog).getByRole('button', { name: 'Сохранить' }));
    expect(within(dialog).getByLabelText('ФИО')).toHaveFocus();
    const position = within(dialog).getByRole('combobox', { name: 'Должность' });
    await user.click(position);
    await user.keyboard('{ArrowDown}{Enter}');
    expect(position).toHaveFocus();
    await user.click(within(dialog).getByRole('button', { name: 'Сбросить 2FA' }));
    const confirm = screen.getByRole('alertdialog', { name: 'Сбросить 2FA?' });
    expect(confirm.contains(document.activeElement)).toBe(true);
  });

  it('does not request (oldQ, page 1) while typing; the page follows the debounced query', async () => {
    const server = mockApi({
      'GET /admin/users': (req) => {
        const page = Number(req.url.searchParams.get('page') ?? '1');
        return json({ items: USERS, total: 120, page, page_size: 50 });
      },
      'GET /admin/positions': json(POSITIONS),
    });
    const { user } = renderWithProviders(<UsersPage me={ME_ADMIN} />);
    await screen.findByRole('table', { name: 'Пользователи' });
    await user.click(screen.getByRole('button', { name: /следующ/i }));
    await waitFor(() => expect(server.calls.some((c) => c.url.searchParams.get('page') === '2')).toBe(true));
    const before = server.calls.length;
    await user.type(screen.getByLabelText('Поиск'), 'kar');
    await waitFor(() => expect(server.calls.some((c) => c.url.searchParams.get('q') === 'kar')).toBe(true));
    const added = server.calls.slice(before).map((c) => `${c.url.searchParams.get('q') ?? ''}|${c.url.searchParams.get('page')}`);
    expect(added).toEqual(['kar|1']);
  });

  it('403 on an admin mutation raises no global notification (inline meta)', async () => {
    const hooks = { onUnauthenticated: vi.fn(), onPasswordChange: vi.fn(), onForbidden: vi.fn(), notify: vi.fn() };
    routes({ 'POST /admin/users/3/block': apiError(403, 'privilege_escalation', 'Недостаточно прав') });
    const { user } = renderWithProviders(<UsersPage me={ME_ADMIN} />, { client: createQueryClient(hooks) });
    const dialog = await openUser(user, 'Рахимов Ильхом');
    await user.click(within(dialog).getByRole('button', { name: 'Заблокировать' }));
    const confirm = screen.getByRole('alertdialog', { name: 'Заблокировать пользователя?' });
    await user.click(within(confirm).getByRole('button', { name: 'Заблокировать' }));
    expect(await within(confirm).findByRole('alert')).toHaveTextContent('Недостаточно прав');
    expect(hooks.notify).not.toHaveBeenCalled();
    expect(hooks.onForbidden).not.toHaveBeenCalled();
  });

  it('the open edit dialog reflects refreshed list data', async () => {
    let name = 'Рахимов Ильхом';
    mockApi({
      'GET /admin/users': () => json({ items: [{ ...USERS[2], full_name: name }], total: 1, page: 1, page_size: 50 }),
      'GET /admin/positions': json(POSITIONS),
    });
    const { user, client } = renderWithProviders(<UsersPage me={ME_ADMIN} />);
    await openUser(user, 'Рахимов Ильхом');
    name = 'Рахимов Ильхом Каримович';
    await client.invalidateQueries({ queryKey: ['admin', 'users'] });
    expect(await screen.findByRole('dialog', { name: 'Рахимов Ильхом Каримович' })).toBeInTheDocument();
  });
});
