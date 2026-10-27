import { screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Routes } from '../app/Routes';
import { expectNoAxeViolations } from '../test/axe';
import { ME_ADMIN, shellRoutes } from '../test/fixtures';
import { apiError, json, mockApi } from '../test/mockApi';
import { renderWithProviders } from '../test/render';
import { LoginPage } from './LoginPage';
import { EnrollLink } from './EnrollLink';

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

  it('"Подключить" asks for the current password, then shows the QR and finishes bound to the session', async () => {
    const server = mockApi({
      ...shellRoutes(),
      'GET /auth/me': json(ME_OFFER),
      'POST /auth/2fa/enroll/begin': json({ otpauth_uri: 'otpauth://totp/x', qr_svg_data_uri: 'data:image/svg+xml;base64,PHN2Zy8+', secret: 'JBSWY3DPEHPK3PXP' }),
      'POST /auth/2fa/enroll/finish': json({ user: { ...ME_ADMIN, mfa_enabled: true }, backup_codes: ['AAAA-BBBB-CCCC'] }),
    });
    const { user } = renderWithProviders(<Routes />, { hash: '#obzor/svod' });
    await user.click(await screen.findByRole('button', { name: 'Подключить' }));
    await waitFor(() => expect(window.location.hash).toBe('#2fa/setup'));
    await user.type(await screen.findByLabelText('Текущий пароль'), 'Secret-Parol-1');
    await user.click(screen.getByRole('button', { name: 'Продолжить' }));
    expect(await screen.findByTestId('totp-secret')).toBeInTheDocument();
    await user.type(screen.getByLabelText('Код из приложения'), '123456');
    await user.click(screen.getByRole('button', { name: 'Подтвердить' }));
    expect(await screen.findByText('AAAA-BBBB-CCCC')).toBeInTheDocument();
    expect(server.calls.find((c) => c.path === '/auth/2fa/enroll/begin')?.body).toEqual({ password: 'Secret-Parol-1' });
    expect(server.calls.find((c) => c.path === '/auth/2fa/enroll/finish')?.body).toEqual({ code: '123456' });
  });

  it('shows a wrong current password inline and cancelling returns to the app, not to login', async () => {
    mockApi({
      ...shellRoutes(),
      'GET /auth/me': json(ME_OFFER),
      'POST /auth/2fa/enroll/begin': apiError(422, 'invalid_current_password', 'Текущий пароль указан неверно'),
    });
    const { user } = renderWithProviders(<Routes />, { hash: '#obzor/svod' });
    await user.click(await screen.findByRole('button', { name: 'Подключить' }));
    await user.type(await screen.findByLabelText('Текущий пароль'), 'Wrong-Parol-1');
    await user.click(screen.getByRole('button', { name: 'Продолжить' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Текущий пароль указан неверно');
    await user.click(screen.getByRole('button', { name: 'Отмена' }));
    await waitFor(() => expect(window.location.hash).not.toMatch(/login|2fa/));
  });

  it('reloading the enroll page for a signed-in user returns to the app', async () => {
    mockApi({ ...shellRoutes() });
    renderWithProviders(<Routes />, { hash: '#2fa/setup' });
    await waitFor(() => expect(window.location.hash).not.toMatch(/login|2fa/));
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
    mockApi({ 'GET /auth/me': json(ME_ADMIN) });
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
