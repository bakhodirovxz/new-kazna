import { screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { SettingOut } from '../api/types';
import { expectNoAxeViolations } from '../test/axe';
import { apiError, json, mockApi } from '../test/mockApi';
import { renderWithProviders } from '../test/render';
import { SettingsList } from './SettingsList';

const BASE: Omit<SettingOut, 'key' | 'title' | 'value' | 'default' | 'category' | 'kind' | 'perm' | 'lo' | 'hi' | 'unit'> = {
  version: 0,
  updated_by: null,
  updated_at: null,
  source: 'default',
  guarded: false,
  step_up: false,
  apply: 'live',
};
const KEEP: SettingOut = { ...BASE, key: 'builds.keep', title: 'Хранить сборок витрины', value: 3, default: 3, category: 'data', kind: 'int', perm: 'admin:settings', lo: 2, hi: 10, unit: '', apply: 'next_run' };
const IDLE: SettingOut = { ...BASE, key: 'security.session_idle_minutes', title: 'Завершение сеанса при бездействии', value: 30, default: 30, category: 'security', kind: 'int', perm: 'admin:security', lo: 5, hi: 30, unit: 'мин', guarded: true, step_up: true, version: 2, source: 'panel', updated_at: '2026-10-20T05:00:00Z' };

describe('SettingsList', () => {
  it('shows only settings of its permission grouped by category', async () => {
    mockApi({ 'GET /admin/settings': json([KEEP, IDLE]) });
    const { container } = renderWithProviders(<SettingsList perm="admin:settings" />);
    const table = await screen.findByRole('table', { name: 'Витрина и сборки' });
    expect(table).toHaveTextContent('Хранить сборок витрины');
    expect(table).toHaveTextContent('По умолчанию');
    expect(screen.queryByText('Завершение сеанса при бездействии')).not.toBeInTheDocument();
    await expectNoAxeViolations(container);
  });

  it('saves an unguarded value with expected_version and no reason', async () => {
    const server = mockApi({
      'GET /admin/settings': json([KEEP]),
      'GET /admin/settings/builds.keep/history': json([]),
      'PUT /admin/settings/builds.keep': json({ ...KEEP, value: 4, version: 1, source: 'panel' }),
    });
    const { user } = renderWithProviders(<SettingsList perm="admin:settings" />);
    await user.click(await screen.findByText('Хранить сборок витрины'));
    const dialog = screen.getByRole('dialog', { name: 'Настройка: Хранить сборок витрины' });
    expect(within(dialog).getByText('Применяется со следующей загрузки или обслуживания')).toBeInTheDocument();
    expect(within(dialog).queryByLabelText('Причина изменения')).not.toBeInTheDocument();
    const input = within(dialog).getByLabelText('Значение');
    await user.clear(input);
    await user.type(input, '11');
    await user.click(within(dialog).getByRole('button', { name: 'Сохранить' }));
    expect(within(dialog).getByText('Допустимо от 2 до 10')).toBeInTheDocument();
    await user.clear(input);
    await user.type(input, '4');
    await user.click(within(dialog).getByRole('button', { name: 'Сохранить' }));
    const put = server.calls.find((c) => c.method === 'PUT');
    expect(put?.body).toEqual({ value: 4, expected_version: 0 });
  });

  it('requires reason and TOTP for a security setting and shows a server OTP error', async () => {
    const server = mockApi({
      'GET /admin/settings': json([IDLE]),
      'GET /admin/settings/security.session_idle_minutes/history': json([{ version: 2, value: 30, updated_by: 1, updated_at: '2026-10-20T05:00:00Z' }]),
      'PUT /admin/settings/security.session_idle_minutes': apiError(422, 'step_up_failed', 'Неверный код подтверждения', { fields: ['otp'] }),
    });
    const { user } = renderWithProviders(<SettingsList perm="admin:security" />);
    await user.click(await screen.findByText('Завершение сеанса при бездействии'));
    const dialog = screen.getByRole('dialog', { name: 'Настройка: Завершение сеанса при бездействии' });
    expect(await within(dialog).findByRole('table', { name: 'История изменений' })).toBeInTheDocument();
    const input = within(dialog).getByLabelText('Значение');
    await user.clear(input);
    await user.type(input, '20');
    await user.click(within(dialog).getByRole('button', { name: 'Сохранить' }));
    expect(within(dialog).getByText('Укажите причину (не менее 5 символов)')).toBeInTheDocument();
    expect(within(dialog).getByText('Введите 6-значный код')).toBeInTheDocument();
    expect(server.calls.some((c) => c.method === 'PUT')).toBe(false);
    await user.type(within(dialog).getByLabelText('Причина изменения'), 'Письмо ИБ №7');
    await user.type(within(dialog).getByLabelText('Код из приложения'), '123456');
    await user.click(within(dialog).getByRole('button', { name: 'Сохранить' }));
    expect(await within(dialog).findByText('Неверный код подтверждения')).toBeInTheDocument();
    expect(server.calls.find((c) => c.method === 'PUT')?.body).toEqual({ value: 20, expected_version: 2, reason: 'Письмо ИБ №7', otp: '123456' });
  });

  it('explains a missing 2FA and links to enrollment (step_up_unavailable)', async () => {
    mockApi({
      'GET /admin/settings': json([IDLE]),
      'GET /admin/settings/security.session_idle_minutes/history': json([]),
      'PUT /admin/settings/security.session_idle_minutes': apiError(403, 'step_up_unavailable', 'Для изменения этих настроек подключите двухфакторную аутентификацию'),
    });
    const { user } = renderWithProviders(<SettingsList perm="admin:security" />);
    await user.click(await screen.findByText('Завершение сеанса при бездействии'));
    const dialog = screen.getByRole('dialog', { name: 'Настройка: Завершение сеанса при бездействии' });
    await user.type(within(dialog).getByLabelText('Причина изменения'), 'Письмо ИБ №7');
    await user.type(within(dialog).getByLabelText('Код из приложения'), '123456');
    await user.click(within(dialog).getByRole('button', { name: 'Сохранить' }));
    expect(await within(dialog).findByText('Для изменения этих настроек подключите двухфакторную аутентификацию')).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: 'Подключить 2FA' })).toBeInTheDocument();
  });

  it('refreshes the dialog version after a 409 so a retry can succeed (M5)', async () => {
    let listCalls = 0;
    const server = mockApi({
      'GET /admin/settings': () => json([listCalls++ === 0 ? KEEP : { ...KEEP, value: 5, version: 3, source: 'panel' }]),
      'GET /admin/settings/builds.keep/history': json([]),
      'PUT /admin/settings/builds.keep': (req) =>
        (req.body as { expected_version: number }).expected_version === 3
          ? json({ ...KEEP, value: 4, version: 4, source: 'panel' })
          : apiError(409, 'conflict_modified', 'Запись изменена другим пользователем, обновите страницу'),
    });
    const { user } = renderWithProviders(<SettingsList perm="admin:settings" />);
    await user.click(await screen.findByText('Хранить сборок витрины'));
    const dialog = screen.getByRole('dialog', { name: 'Настройка: Хранить сборок витрины' });
    const input = within(dialog).getByLabelText('Значение');
    await user.clear(input);
    await user.type(input, '4');
    await user.click(within(dialog).getByRole('button', { name: 'Сохранить' }));
    expect(await within(dialog).findByText('Запись изменена другим пользователем, обновите страницу')).toBeInTheDocument();
    await waitFor(() => expect(listCalls).toBeGreaterThan(1));
    await user.click(within(dialog).getByRole('button', { name: 'Сохранить' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    const bodies = server.calls.filter((c) => c.method === 'PUT').map((c) => (c.body as { expected_version: number }).expected_version);
    expect(bodies).toEqual([0, 3]);
  });

  it('keeps no OTP in the mutation cache after saving a setting (I1)', async () => {
    mockApi({
      'GET /admin/settings': json([IDLE]),
      'GET /admin/settings/security.session_idle_minutes/history': json([]),
      'PUT /admin/settings/security.session_idle_minutes': json({ ...IDLE, value: 20 }),
    });
    const { user, client } = renderWithProviders(<SettingsList perm="admin:security" />);
    await user.click(await screen.findByText('Завершение сеанса при бездействии'));
    const dialog = screen.getByRole('dialog', { name: 'Настройка: Завершение сеанса при бездействии' });
    const input = within(dialog).getByLabelText('Значение');
    await user.clear(input);
    await user.type(input, '20');
    await user.type(within(dialog).getByLabelText('Причина изменения'), 'Письмо ИБ №7');
    await user.type(within(dialog).getByLabelText('Код из приложения'), '123456');
    await user.click(within(dialog).getByRole('button', { name: 'Сохранить' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    await waitFor(() => expect(client.getMutationCache().getAll()).toHaveLength(0));
  });
});
