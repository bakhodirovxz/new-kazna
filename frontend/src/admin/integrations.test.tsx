import { screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { IntegrationOut, SettingOut } from '../api/types';
import { expectNoAxeViolations } from '../test/axe';
import { json, mockApi } from '../test/mockApi';
import { renderWithProviders } from '../test/render';
import IntegrationsPage from './IntegrationsPage';

function field(key: string, title: string, kind: string, value: unknown, extra: Partial<SettingOut> = {}): SettingOut {
  return { key, title, kind, value, default: value, version: 0, updated_by: null, updated_at: null, source: 'env', category: 'integrations', perm: 'admin:integrations', guarded: true, step_up: true, apply: 'live', unit: '', lo: null, hi: null, ...extra };
}

const SMTP: IntegrationOut = {
  name: 'smtp',
  title: 'Почтовый сервер (SMTP)',
  check_in: 'worker',
  endpoint: ['smtp.host', 'smtp.port'],
  fields: [field('smtp.host', 'Сервер SMTP', 'str', 'relay.uge.uz'), field('smtp.port', 'Порт', 'int', 587, { lo: 1, hi: 65535 })],
  secrets: [{ name: 'smtp.password', title: 'Пароль SMTP', state: 'env', updated_at: null, updated_by: null }],
  last_check: null,
};

describe('IntegrationsPage', () => {
  it('shows secret state without a value and runs a connection check', async () => {
    const server = mockApi({
      'GET /admin/integrations': json([SMTP]),
      'POST /admin/integrations/smtp/check': json({ id: 7, name: 'smtp', status: 'pending', code: null, requested_at: '2026-10-26T05:00:00Z', finished_at: null }, 202),
      'GET /admin/integrations/checks/7': json({ id: 7, name: 'smtp', status: 'failed', code: 'auth_failed', requested_at: '2026-10-26T05:00:00Z', finished_at: '2026-10-26T05:00:05Z' }),
    });
    const { user, container } = renderWithProviders(<IntegrationsPage />);
    const card = await screen.findByRole('region', { name: 'Почтовый сервер (SMTP)' });
    expect(within(card).getByText('Из конфигурации сервера')).toBeInTheDocument();
    await expectNoAxeViolations(container);
    await user.click(within(card).getByRole('button', { name: 'Проверить подключение' }));
    expect(await within(card).findByText('Неверные учётные данные')).toBeInTheDocument();
    expect(server.calls.filter((c) => c.method === 'POST')).toHaveLength(1);
  });

  it('sends only changed fields, warns on endpoint change and never pre-fills the password', async () => {
    const server = mockApi({
      'GET /admin/integrations': json([SMTP]),
      'GET /admin/settings/smtp.host/history': json([]),
      'PUT /admin/integrations/smtp': json({ ...SMTP, secrets: [{ ...SMTP.secrets[0], state: 'none' }] }),
    });
    const { user } = renderWithProviders(<IntegrationsPage />);
    await user.click(await screen.findByRole('button', { name: 'Изменить' }));
    const dialog = screen.getByRole('dialog', { name: 'Интеграция: Почтовый сервер (SMTP)' });
    const password = within(dialog).getByLabelText('Пароль SMTP');
    expect(password).toHaveValue('');
    const host = within(dialog).getByLabelText('Сервер SMTP');
    await user.clear(host);
    await user.type(host, 'mail.uge.uz');
    expect(within(dialog).getByText('Адрес изменён: сохранённые учётные данные будут удалены, если не ввести новые.')).toBeInTheDocument();
    await user.type(within(dialog).getByLabelText('Причина изменения'), 'Заявка ИТ-42');
    await user.type(within(dialog).getByLabelText('Код из приложения'), '654321');
    await user.click(within(dialog).getByRole('button', { name: 'Сохранить' }));
    const put = server.calls.find((c) => c.method === 'PUT');
    expect(put?.body).toEqual({ values: { 'smtp.host': 'mail.uge.uz' }, secrets: {}, reason: 'Заявка ИТ-42', otp: '654321' });
  });
});
