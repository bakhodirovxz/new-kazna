import { screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Routes } from '../app/Routes';
import { expectNoAxeViolations } from '../test/axe';
import { ME_ADMIN, shellRoutes } from '../test/fixtures';
import { apiError, json, mockApi } from '../test/mockApi';
import { renderWithProviders } from '../test/render';
import { LoginPage } from './LoginPage';
import { EnrollLink } from './EnrollLink';

const TOKEN = 't'.repeat(32);
const ME_OFFER = { ...ME_ADMIN, mfa_enabled: false, mfa_offer: true };

describe('2FA необязательна', () => {
  it('login without 2FA opens the session and skips the 2FA step', async () => {
    const server = mockApi({ 'POST /auth/login': json({ next: 'done', mfa_token: null, user: ME_ADMIN }) });
    const { user, client } = renderWithProviders(<LoginPage next="kazna/svod" />, { hash: '#login?next=kazna%2Fsvod' });
    await user.type(screen.getByLabelText('Логин'), 'admin');
    await user.type(screen.getByLabelText('Пароль'), 'Secret-Parol-1');
    await user.click(screen.getByRole('button', { name: 'Войти' }));
    await waitFor(() => expect(window.location.hash).toBe('#kazna/svod'));
    expect(client.getQueryData(['auth', 'me'])).toEqual(ME_ADMIN);
    expect(server.calls).toHaveLength(1);
  });

  it('login with forced password change still goes to #password', async () => {
    mockApi({ 'POST /auth/login': json({ next: 'done', mfa_token: null, user: { ...ME_OFFER, must_change_password: true } }) });
    const { user } = renderWithProviders(<LoginPage next={null} />, { hash: '#login' });
    await user.type(screen.getByLabelText('Логин'), 'admin');
    await user.type(screen.getByLabelText('Пароль'), 'Secret-Parol-1');
    await user.click(screen.getByRole('button', { name: 'Войти' }));
    await waitFor(() => expect(window.location.hash).toBe('#password'));
  });

  it('offers enrollment and "Позже" dismisses it and opens the app', async () => {
    let offer = true;
    const server = mockApi({
      ...shellRoutes(),
      'GET /auth/me': () => json({ ...ME_OFFER, mfa_offer: offer }),
      'POST /auth/2fa/offer/dismiss': () => {
        offer = false;
        return { status: 204 };
      },
    });
    const { user } = renderWithProviders(<Routes />, { hash: '#obzor/svod' });
    expect(await screen.findByRole('heading', { name: 'Подключить двухфакторную аутентификацию?' })).toBeInTheDocument();
    await expectNoAxeViolations(document.body);
    await user.click(screen.getByRole('button', { name: 'Позже' }));
    await waitFor(() => expect(screen.queryByRole('heading', { name: 'Подключить двухфакторную аутентификацию?' })).not.toBeInTheDocument());
    expect(server.calls.some((c) => c.method === 'POST' && c.path === '/auth/2fa/offer/dismiss')).toBe(true);
  });

  it('"Подключить" opens a challenge and goes to the enroll flow', async () => {
    mockApi({
      ...shellRoutes(),
      'GET /auth/me': json(ME_OFFER),
      'POST /auth/2fa/enroll/begin': json({ mfa_token: TOKEN }),
    });
    const { user } = renderWithProviders(<Routes />, { hash: '#obzor/svod' });
    await user.click(await screen.findByRole('button', { name: 'Подключить' }));
    await waitFor(() => expect(window.location.hash).toBe('#2fa/setup'));
  });

  it('user menu offers «Подключить 2FA» only without 2FA', async () => {
    mockApi({ ...shellRoutes(ME_ADMIN), 'GET /auth/me': json({ ...ME_ADMIN, mfa_enabled: false }) });
    const { user } = renderWithProviders(<Routes />, { hash: '#obzor/svod' });
    await user.click(await screen.findByRole('button', { name: /Меню пользователя/ }));
    expect(screen.getByRole('menuitem', { name: 'Подключить 2FA' })).toBeInTheDocument();
  });

  it('user menu hides «Подключить 2FA» when 2FA is on', async () => {
    mockApi(shellRoutes());
    const { user } = renderWithProviders(<Routes />, { hash: '#obzor/svod' });
    await user.click(await screen.findByRole('button', { name: /Меню пользователя/ }));
    expect(screen.getByRole('menuitem', { name: 'Мои сеансы' })).toBeInTheDocument();
    expect(screen.queryByRole('menuitem', { name: 'Подключить 2FA' })).not.toBeInTheDocument();
  });

  it('EnrollLink starts enrollment', async () => {
    mockApi({ 'GET /auth/me': json(ME_ADMIN), 'POST /auth/2fa/enroll/begin': json({ mfa_token: TOKEN }) });
    const { user } = renderWithProviders(<EnrollLink />, { hash: '#admin/security' });
    await user.click(screen.getByRole('button', { name: 'Подключить 2FA' }));
    await waitFor(() => expect(window.location.hash).toBe('#2fa/setup'));
  });

  it('offer screen shows a failed dismiss', async () => {
    mockApi({
      ...shellRoutes(),
      'GET /auth/me': json(ME_OFFER),
      'POST /auth/2fa/offer/dismiss': apiError(500, 'internal_error', 'Внутренняя ошибка сервера'),
    });
    const { user } = renderWithProviders(<Routes />, { hash: '#obzor/svod' });
    await user.click(await screen.findByRole('button', { name: 'Позже' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Внутренняя ошибка сервера');
  });
});
