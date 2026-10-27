import { screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { PermissionOut, PositionOut, RoleOut } from '../api/types';
import { expectNoAxeViolations } from '../test/axe';
import { BRANCHES } from '../test/fixtures';
import { apiError, json, mockApi, type MockHandler } from '../test/mockApi';
import { renderWithProviders } from '../test/render';
import RolesPage from './RolesPage';

const ROLES: RoleOut[] = [
  { id: 6, code: 'admin', name: 'Администратор', scope_all: true, is_system: true, permissions: ['admin:users', 'admin:roles'] },
];
const POSITIONS: PositionOut[] = [
  { id: 6, code: 'admin', name: 'Администратор', role_id: 6, role_code: 'admin', is_active: true, branch_ids: [] },
];
const PERMISSIONS: PermissionOut[] = [
  { code: 'section:obzor:view', description: 'Раздел «Обзор»: просмотр' },
  { code: 'data:kazna:approve', description: 'Ввод данных «Казначейство»: согласование' },
  { code: 'admin:users', description: 'Администрирование: пользователи' },
];

function routes(extra: Record<string, MockHandler>) {
  return mockApi({
    'GET /admin/positions': json(POSITIONS),
    'GET /admin/roles': json(ROLES),
    'GET /admin/permissions': json(PERMISSIONS),
    'GET /meta/branches': json(BRANCHES),
    ...extra,
  });
}

async function fillRole(user: ReturnType<typeof renderWithProviders>['user']) {
  await user.click(await screen.findByRole('tab', { name: 'Роли' }));
  await user.click(await screen.findByRole('button', { name: 'Добавить роль' }));
  const dialog = screen.getByRole('dialog', { name: 'Новая роль' });
  await user.type(within(dialog).getByLabelText('Код'), 'checker');
  await user.type(within(dialog).getByLabelText('Название'), 'Контролёр');
  await user.click(within(dialog).getByLabelText('Ввод данных «Казначейство»: согласование'));
  return dialog;
}

describe('step-up for data approve grants', () => {
  it('asks for the 2FA code when the server requires it and resends with otp', async () => {
    let calls = 0;
    const server = routes({
      'POST /admin/roles': (req) => {
        calls += 1;
        const body = req.body as { otp?: string };
        if (!body.otp) return apiError(422, 'step_up_required', 'Подтвердите изменение кодом из приложения', { fields: ['otp'] });
        return json({ id: 10, is_system: false, code: 'checker', name: 'Контролёр', scope_all: false, permissions: ['data:kazna:approve'] }, 201);
      },
    });
    const { user, client } = renderWithProviders(<RolesPage />);
    const dialog = await fillRole(user);
    expect(within(dialog).queryByLabelText('Код из приложения')).toBeNull();
    await user.click(within(dialog).getByRole('button', { name: 'Создать' }));
    const otp = await within(dialog).findByLabelText('Код из приложения');
    expect(dialog).toHaveTextContent('Выдача права согласования ввода данных подтверждается кодом 2FA');
    await expectNoAxeViolations(dialog);
    await user.type(otp, '123456');
    await user.click(within(dialog).getByRole('button', { name: 'Создать' }));
    expect(await screen.findByText('Сохранено. Изменение записано в журнал аудита.')).toBeInTheDocument();
    expect(calls).toBe(2);
    const posts = server.calls.filter((c) => c.method === 'POST');
    expect(posts[0]?.body).not.toHaveProperty('otp');
    expect(posts[1]?.body).toMatchObject({ otp: '123456', permissions: ['data:kazna:approve'] });
    await waitFor(() => expect(client.getMutationCache().getAll()).toHaveLength(0));
  });

  it('shows a wrong code inline and clears the field', async () => {
    routes({
      'POST /admin/roles': (req) =>
        (req.body as { otp?: string }).otp
          ? apiError(422, 'step_up_failed', 'Неверный код подтверждения', { fields: ['otp'] })
          : apiError(422, 'step_up_required', 'Подтвердите изменение кодом из приложения', { fields: ['otp'] }),
    });
    const { user } = renderWithProviders(<RolesPage />);
    const dialog = await fillRole(user);
    await user.click(within(dialog).getByRole('button', { name: 'Создать' }));
    await user.type(await within(dialog).findByLabelText('Код из приложения'), '000000');
    await user.click(within(dialog).getByRole('button', { name: 'Создать' }));
    expect(await within(dialog).findByText('Неверный код подтверждения')).toBeInTheDocument();
    expect(within(dialog).getByLabelText('Код из приложения')).toHaveValue('');
  });
});
