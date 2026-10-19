import { screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { PermissionOut, PositionOut, RoleOut } from '../api/types';
import { expectNoAxeViolations } from '../test/axe';
import { BRANCHES } from '../test/fixtures';
import { apiError, json, mockApi, type MockHandler } from '../test/mockApi';
import { renderWithProviders } from '../test/render';
import RolesPage from './RolesPage';

const ROLES: RoleOut[] = [
  { id: 6, code: 'admin', name: 'Администратор', scope_all: true, is_system: true, permissions: ['admin:users', 'admin:roles', 'section:obzor:view'] },
  { id: 4, code: 'economist_filiala', name: 'Экономист филиала', scope_all: false, is_system: true, permissions: ['section:obzor:view', 'export:csv'] },
];

const POSITIONS: PositionOut[] = [
  { id: 6, code: 'admin', name: 'Администратор', role_id: 6, role_code: 'admin', is_active: true, branch_ids: [] },
  { id: 4, code: 'economist_filiala', name: 'Экономист филиала', role_id: 4, role_code: 'economist_filiala', is_active: true, branch_ids: [3] },
];

const PERMISSIONS: PermissionOut[] = [
  { code: 'section:obzor:view', description: 'Раздел «Обзор»: просмотр' },
  { code: 'section:kazna:view', description: 'Раздел «Казначейство»: просмотр' },
  { code: 'export:csv', description: 'Выгрузка таблиц в CSV' },
  { code: 'admin:users', description: 'Администрирование: пользователи' },
  { code: 'admin:roles', description: 'Администрирование: должности и роли' },
  { code: 'audit:read', description: 'Просмотр журнала аудита' },
];

function routes(extra: Record<string, MockHandler> = {}) {
  return mockApi({
    'GET /admin/positions': json(POSITIONS),
    'GET /admin/roles': json(ROLES),
    'GET /admin/permissions': json(PERMISSIONS),
    'GET /meta/branches': json(BRANCHES),
    ...extra,
  });
}

describe('positions', () => {
  it('lists positions with role and branch scope', async () => {
    routes();
    renderWithProviders(<RolesPage />);
    const table = await screen.findByRole('table', { name: 'Должности' });
    const rows = within(table).getAllByRole('row').slice(1);
    expect(rows[0]).toHaveTextContent('Все (по роли)');
    expect(await within(table).findByText('Чирчик')).toBeInTheDocument();
  });

  it('edits the branches of a position', async () => {
    const server = routes({ 'PATCH /admin/positions/4': json({ ...POSITIONS[1], branch_ids: [3, 4] }) });
    const { user } = renderWithProviders(<RolesPage />);
    await user.click((await screen.findAllByText('Экономист филиала', { selector: 'td' }))[0] as HTMLElement);
    const dialog = screen.getByRole('dialog', { name: 'Должность: Экономист филиала' });
    const chirchik = within(dialog).getByLabelText('Каскад Чирчикских ГЭС');
    expect(chirchik).toBeChecked();
    await user.click(within(dialog).getByLabelText('Андижанская ГЭС'));
    await user.click(within(dialog).getByRole('button', { name: 'Сохранить' }));
    expect(await screen.findByText('Сохранено. Изменение записано в журнал аудита.')).toBeInTheDocument();
    expect(server.calls.find((c) => c.method === 'PATCH')?.body).toEqual({
      name: 'Экономист филиала',
      role_id: 4,
      branch_ids: [3, 4],
      is_active: true,
    });
  });

  it('validates the code and shows a taken code from the server', async () => {
    routes({ 'POST /admin/positions': apiError(409, 'code_taken', 'Код уже используется') });
    const { user } = renderWithProviders(<RolesPage />);
    await user.click(await screen.findByRole('button', { name: 'Добавить должность' }));
    const dialog = screen.getByRole('dialog', { name: 'Новая должность' });
    await user.type(within(dialog).getByLabelText('Код'), 'Bad Code');
    await user.type(within(dialog).getByLabelText('Название'), 'Экономист Чарвак');
    await user.click(within(dialog).getByRole('button', { name: 'Создать' }));
    expect(within(dialog).getAllByText('Латиница в нижнем регистре, цифры и «_», начинается с буквы').length).toBeGreaterThan(1);
    await user.clear(within(dialog).getByLabelText('Код'));
    await user.type(within(dialog).getByLabelText('Код'), 'econ_charvak');
    await user.selectOptions(within(dialog).getByLabelText('Роль'), '4');
    await user.click(within(dialog).getByLabelText('Чарвакская ГЭС'));
    await user.click(within(dialog).getByRole('button', { name: 'Создать' }));
    expect(await within(dialog).findByText('Код уже используется')).toBeInTheDocument();
  });

  it('disables branch selection for a role with access to all branches', async () => {
    routes();
    const { user } = renderWithProviders(<RolesPage />);
    await user.click(await screen.findByRole('button', { name: 'Добавить должность' }));
    const dialog = screen.getByRole('dialog', { name: 'Новая должность' });
    await user.selectOptions(within(dialog).getByLabelText('Роль'), '6');
    expect(within(dialog).getByText('Роль даёт доступ ко всем филиалам — список не применяется.')).toBeInTheDocument();
    expect(within(dialog).getByLabelText('Чарвакская ГЭС')).toBeDisabled();
  });
});

describe('roles', () => {
  it('creates a role with grouped permissions', async () => {
    const server = routes({
      'POST /admin/roles': (req) => json({ id: 10, is_system: false, ...(req.body as object) }, 201),
    });
    const { user } = renderWithProviders(<RolesPage />);
    await user.click(await screen.findByRole('tab', { name: 'Роли' }));
    expect(await screen.findByRole('table', { name: 'Роли' })).toHaveTextContent('Системная');
    await user.click(screen.getByRole('button', { name: 'Добавить роль' }));
    const dialog = screen.getByRole('dialog', { name: 'Новая роль' });
    expect(within(dialog).getByRole('group', { name: 'Разделы' })).toBeInTheDocument();
    await user.type(within(dialog).getByLabelText('Код'), 'analitik');
    await user.type(within(dialog).getByLabelText('Название'), 'Аналитик');
    await user.click(within(dialog).getByLabelText('Раздел «Обзор»: просмотр'));
    await user.click(within(dialog).getByLabelText('Выгрузка таблиц в CSV'));
    await user.click(within(dialog).getByRole('button', { name: 'Создать' }));
    expect(await screen.findByText('Сохранено. Изменение записано в журнал аудита.')).toBeInTheDocument();
    expect(server.calls.find((c) => c.method === 'POST')?.body).toEqual({
      code: 'analitik',
      name: 'Аналитик',
      scope_all: true,
      permissions: ['export:csv', 'section:obzor:view'],
    });
  });

  it('shows the protection error when stripping admin rights', async () => {
    routes({
      'PATCH /admin/roles/6': apiError(409, 'admin_role_protected', 'У роли администратора нельзя отнять права администрирования'),
    });
    const { user } = renderWithProviders(<RolesPage />);
    await user.click(await screen.findByRole('tab', { name: 'Роли' }));
    await user.click((await screen.findAllByText('Администратор', { selector: 'td' }))[0] as HTMLElement);
    const dialog = screen.getByRole('dialog', { name: 'Роль: Администратор' });
    expect(within(dialog).getByText('Системная роль: код изменить нельзя.')).toBeInTheDocument();
    await user.click(within(dialog).getByLabelText('Администрирование: пользователи'));
    await user.click(within(dialog).getByRole('button', { name: 'Сохранить' }));
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('У роли администратора нельзя отнять');
  });

  it('has no axe violations', async () => {
    routes();
    const { container } = renderWithProviders(<RolesPage />);
    await screen.findByRole('table', { name: 'Должности' });
    await expectNoAxeViolations(container);
  });
});

describe('Task 15 review hardening', () => {
  it('focuses the first invalid field and limits input length', async () => {
    routes();
    const { user } = renderWithProviders(<RolesPage />);
    await user.click(await screen.findByRole('button', { name: 'Добавить должность' }));
    const dialog = screen.getByRole('dialog', { name: 'Новая должность' });
    expect(within(dialog).getByLabelText(/Код/)).toHaveAttribute('maxlength', '64');
    expect(within(dialog).getByLabelText('Название')).toHaveAttribute('maxlength', '200');
    await user.click(within(dialog).getByRole('button', { name: 'Создать' }));
    expect(within(dialog).getByLabelText(/Код/)).toHaveFocus();
  });

  it('maps 422 params.fields to the name field of a role', async () => {
    routes({ 'POST /admin/roles': apiError(422, 'validation_failed', 'Проверьте введённые данные', { fields: ['name'] }) });
    const { user } = renderWithProviders(<RolesPage />);
    await user.click(await screen.findByRole('tab', { name: 'Роли' }));
    await user.click(await screen.findByRole('button', { name: 'Добавить роль' }));
    const dialog = screen.getByRole('dialog', { name: 'Новая роль' });
    await user.type(within(dialog).getByLabelText('Код'), 'analitik');
    await user.type(within(dialog).getByLabelText('Название'), 'Аналитик');
    await user.click(within(dialog).getByRole('button', { name: 'Создать' }));
    expect(await within(dialog).findByText('Проверьте введённые данные')).toBeInTheDocument();
    expect(within(dialog).getByLabelText('Название')).toHaveFocus();
  });
});
