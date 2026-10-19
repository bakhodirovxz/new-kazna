import { screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { PositionOut, UserOut } from '../api/types';
import { expectNoAxeViolations } from '../test/axe';
import { ME_ADMIN } from '../test/fixtures';
import { apiError, json, mockApi, type MockHandler } from '../test/mockApi';
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
