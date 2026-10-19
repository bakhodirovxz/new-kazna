import { screen, waitFor } from '@testing-library/react';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { makeQueryClient } from '../app/queryClient';
import { expectNoAxeViolations } from '../test/axe';
import { ME_ADMIN } from '../test/fixtures';
import { apiError, json, mockApi } from '../test/mockApi';
import { renderWithProviders } from '../test/render';
import { useAuthFlow, type Challenge } from './AuthFlow';
import { LoginPage } from './LoginPage';
import { MfaVerifyPage } from './MfaVerifyPage';
import { PasswordChangePage } from './PasswordChangePage';

const TOKEN = 't'.repeat(32);

function WithChallenge({ step = 'mfa_verify', returnTo = null, children }: { step?: Challenge['step']; returnTo?: string | null; children: ReactNode }) {
  const flow = useAuthFlow();
  const started = useRef(false);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    flow.begin({ mfaToken: TOKEN, step, username: 'admin', returnTo });
    setReady(true);
  }, [flow, step, returnTo]);
  return ready ? <>{children}</> : null;
}

describe('LoginPage', () => {
  it('validates empty fields without calling the API', async () => {
    const server = mockApi({});
    const { user } = renderWithProviders(<LoginPage next={null} />, { hash: '#login' });
    await user.click(screen.getByRole('button', { name: 'Войти' }));
    expect(screen.getByText('Введите логин')).toBeInTheDocument();
    expect(screen.getByText('Введите пароль')).toBeInTheDocument();
    expect(server.calls).toHaveLength(0);
  });

  it('shows the server message on bad credentials and clears the password', async () => {
    mockApi({ 'POST /auth/login': apiError(401, 'invalid_credentials', 'Неверный логин или пароль') });
    const { user } = renderWithProviders(<LoginPage next={null} />, { hash: '#login' });
    await user.type(screen.getByLabelText('Логин'), 'admin');
    await user.type(screen.getByLabelText('Пароль'), 'wrong-password');
    await user.click(screen.getByRole('button', { name: 'Войти' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Неверный логин или пароль');
    expect(screen.getByLabelText('Пароль')).toHaveValue('');
    expect(window.location.hash).toBe('#login');
  });

  it('shows retry time on 429', async () => {
    mockApi({
      'POST /auth/login': apiError(429, 'rate_limited', 'Слишком много запросов', { retry_after: 42 }, { 'Retry-After': '42' }),
    });
    const { user } = renderWithProviders(<LoginPage next={null} />, { hash: '#login' });
    await user.type(screen.getByLabelText('Логин'), 'admin');
    await user.type(screen.getByLabelText('Пароль'), 'x');
    await user.click(screen.getByRole('button', { name: 'Войти' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Слишком много запросов. Повторите через 42 с.');
    expect(window.location.hash).toBe('#login');
    expect(screen.getByLabelText('Пароль')).toHaveValue('');
  });

  it('trims the username and goes to 2FA enrollment when required', async () => {
    const server = mockApi({ 'POST /auth/login': json({ next: 'mfa_enroll', mfa_token: TOKEN }) });
    const { user } = renderWithProviders(<LoginPage next="kazna/svod" />, { hash: '#login?next=kazna%2Fsvod' });
    await user.type(screen.getByLabelText('Логин'), '  Admin  ');
    await user.type(screen.getByLabelText('Пароль'), 'Secret-Parol-1');
    await user.click(screen.getByRole('button', { name: 'Войти' }));
    await waitFor(() => expect(window.location.hash).toBe('#2fa/setup'));
    expect(server.calls[0]?.body).toEqual({ username: 'Admin', password: 'Secret-Parol-1' });
  });

  it('has no axe violations', async () => {
    const { container } = renderWithProviders(<LoginPage next={null} />, { hash: '#login' });
    await expectNoAxeViolations(container);
  });

  it('exposes a contentinfo landmark and focuses the first invalid field', async () => {
    const { user } = renderWithProviders(<LoginPage next={null} />, { hash: '#login' });
    expect(screen.getByRole('contentinfo')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Войти' }));
    expect(screen.getByLabelText('Логин')).toHaveFocus();
  });
});

describe('auth hardening (review round 1)', () => {
  it('leaves no password in the mutation cache after a failed login (M1) and focuses the password (M2)', async () => {
    mockApi({ 'POST /auth/login': apiError(401, 'invalid_credentials', 'Неверный логин или пароль') });
    const { user, client } = renderWithProviders(<LoginPage next={null} />, { hash: '#login' });
    expect(screen.getByLabelText('Логин')).toHaveFocus();
    await user.type(screen.getByLabelText('Логин'), 'admin');
    await user.type(screen.getByLabelText('Пароль'), 'Wrong-Secret-9');
    await user.click(screen.getByRole('button', { name: 'Войти' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Неверный логин');
    expect(screen.getByLabelText('Пароль')).toHaveFocus();
    expect(JSON.stringify(client.getMutationCache().getAll().map((m) => m.state.variables))).not.toContain('Wrong-Secret-9');
  });

  it('does not toast a rate limit that the password form shows inline (M5)', async () => {
    mockApi({ 'POST /auth/password/change': apiError(429, 'rate_limited', 'Слишком много запросов', undefined, { 'Retry-After': '30' }) });
    const notify = vi.fn();
    const { user } = renderWithProviders(<PasswordChangePage me={{ ...ME_ADMIN, must_change_password: true }} />, {
      hash: '#password',
      client: makeQueryClient(notify),
    });
    await user.type(screen.getByLabelText('Текущий пароль'), 'Old-Parol-2025!');
    await user.type(screen.getByLabelText('Новый пароль'), 'Yangi-Mustahkam-77');
    await user.type(screen.getByLabelText('Повторите новый пароль'), 'Yangi-Mustahkam-77');
    await user.click(screen.getByRole('button', { name: 'Сохранить пароль' }));
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(notify).not.toHaveBeenCalled();
  });

  it('has a hidden username field for password managers (M9)', () => {
    renderWithProviders(<PasswordChangePage me={ME_ADMIN} />, { hash: '#password' });
    const hidden = document.querySelector('input[autocomplete="username"]');
    expect(hidden).toHaveValue('admin');
    expect(hidden).toHaveAttribute('readonly');
  });
});

describe('MfaVerifyPage', () => {
  it('disables the code input once the challenge expired (M6)', async () => {
    mockApi({ 'POST /auth/2fa/verify': apiError(401, 'mfa_expired', 'Время подтверждения истекло, войдите снова') });
    const { user } = renderWithProviders(
      <WithChallenge>
        <MfaVerifyPage />
      </WithChallenge>,
      { hash: '#2fa' },
    );
    await user.type(await screen.findByLabelText('Код из приложения'), '123456');
    expect(await screen.findByRole('alert')).toHaveTextContent('Время подтверждения истекло');
    expect(screen.getByLabelText('Код из приложения')).toBeDisabled();
  });

  it('refocuses the code input after a wrong code (M2) and keeps no code in the cache (M1)', async () => {
    mockApi({ 'POST /auth/2fa/verify': apiError(401, 'invalid_mfa_code', 'Неверный код подтверждения') });
    const { user, client } = renderWithProviders(
      <WithChallenge>
        <MfaVerifyPage />
      </WithChallenge>,
      { hash: '#2fa' },
    );
    const input = await screen.findByLabelText('Код из приложения');
    await user.type(input, '654321');
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(input).toHaveFocus();
    expect(JSON.stringify(client.getMutationCache().getAll().map((m) => m.state.variables))).not.toContain('654321');
  });

  it('sends the user back to login without a challenge', async () => {
    renderWithProviders(<MfaVerifyPage />, { hash: '#2fa' });
    await waitFor(() => expect(window.location.hash).toBe('#login'));
  });

  it('submits the code only once', async () => {
    let release: () => void = () => undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const server = mockApi({
      'POST /auth/2fa/verify': async () => {
        await gate;
        return json(ME_ADMIN);
      },
    });
    const { user } = renderWithProviders(
      <WithChallenge returnTo="kazna/svod?br=3">
        <MfaVerifyPage />
      </WithChallenge>,
      { hash: '#2fa' },
    );
    const input = await screen.findByLabelText('Код из приложения');
    expect(input).toHaveFocus();
    await user.type(input, '123456');
    await user.keyboard('{Enter}');
    await user.click(screen.getByRole('button', { name: 'Подтвердить' }));
    release();
    await waitFor(() => expect(window.location.hash).toBe('#kazna/svod?br=3'));
    expect(server.calls.filter((c) => c.path === '/auth/2fa/verify')).toHaveLength(1);
    expect(server.calls[0]?.body).toEqual({ mfa_token: TOKEN, code: '123456' });
  });

  it('shows an error on a wrong code, clears it and allows another try', async () => {
    let attempts = 0;
    mockApi({
      'POST /auth/2fa/verify': () => {
        attempts += 1;
        return attempts === 1 ? apiError(401, 'invalid_mfa_code', 'Неверный код подтверждения') : json(ME_ADMIN);
      },
    });
    const { user } = renderWithProviders(
      <WithChallenge>
        <MfaVerifyPage />
      </WithChallenge>,
      { hash: '#2fa' },
    );
    const input = await screen.findByLabelText('Код из приложения');
    await user.type(input, '111111');
    expect(await screen.findByRole('alert')).toHaveTextContent('Неверный код подтверждения');
    expect(input).toHaveValue('');
    await user.type(input, '222222');
    // returnTo yo'q → bosh sahifa ('#' → location.hash === '')
    await waitFor(() => expect(window.location.hash).toBe(''));
  });

  it('accepts a backup code', async () => {
    const server = mockApi({ 'POST /auth/2fa/verify': json({ ...ME_ADMIN, must_change_password: true }) });
    const { user } = renderWithProviders(
      <WithChallenge>
        <MfaVerifyPage />
      </WithChallenge>,
      { hash: '#2fa' },
    );
    await user.click(await screen.findByRole('button', { name: 'Использовать резервный код' }));
    await user.type(screen.getByLabelText('Резервный код'), 'abcd-efgh-jkmn');
    await user.keyboard('{Enter}');
    await waitFor(() => expect(window.location.hash).toBe('#password'));
    expect(server.calls[0]?.body).toEqual({ mfa_token: TOKEN, code: 'ABCD-EFGH-JKMN' });
  });

  it('offers a new sign-in when the challenge expired', async () => {
    mockApi({ 'POST /auth/2fa/verify': apiError(401, 'mfa_expired', 'Время подтверждения истекло, войдите снова') });
    const { user } = renderWithProviders(
      <WithChallenge returnTo="obzor/svod">
        <MfaVerifyPage />
      </WithChallenge>,
      { hash: '#2fa' },
    );
    await user.type(await screen.findByLabelText('Код из приложения'), '123456');
    expect(await screen.findByRole('alert')).toHaveTextContent('Время подтверждения истекло');
    await user.click(screen.getByRole('button', { name: 'Войти заново' }));
    await waitFor(() => expect(window.location.hash).toBe('#login?next=obzor%2Fsvod'));
  });
});

describe('PasswordChangePage', () => {
  const forcedMe = { ...ME_ADMIN, must_change_password: true };

  it('shows live rules and client-side errors', async () => {
    const server = mockApi({});
    const { user } = renderWithProviders(<PasswordChangePage me={forcedMe} />, { hash: '#password' });
    expect(screen.getByRole('heading', { name: 'Необходимо сменить пароль' })).toBeInTheDocument();
    const rules = screen.getByRole('list', { name: 'Требования к паролю' });
    await user.type(screen.getByLabelText('Новый пароль'), 'Admin-Parol-2026');
    expect(rules.querySelector('[data-rule="length"]')).toHaveAttribute('data-ok', 'true');
    expect(rules.querySelector('[data-rule="username"]')).toHaveAttribute('data-ok', 'false');
    await user.type(screen.getByLabelText('Повторите новый пароль'), 'другое');
    await user.click(screen.getByRole('button', { name: 'Сохранить пароль' }));
    expect(screen.getByText('Пароль не соответствует требованиям')).toBeInTheDocument();
    expect(screen.getByText('Пароли не совпадают')).toBeInTheDocument();
    expect(screen.getAllByText('Обязательное поле')).toHaveLength(1);
    expect(server.calls).toHaveLength(0);
  });

  it('lists server policy problems and marks a wrong current password', async () => {
    let call = 0;
    mockApi({
      'POST /auth/password/change': () => {
        call += 1;
        return call === 1
          ? apiError(422, 'password_policy', 'Пароль не соответствует политике', { problems: ['password_common', 'password_reused'] })
          : apiError(422, 'invalid_current_password', 'Текущий пароль указан неверно');
      },
    });
    const { user } = renderWithProviders(<PasswordChangePage me={forcedMe} />, { hash: '#password' });
    await user.type(screen.getByLabelText('Текущий пароль'), 'Old-Parol-2025!');
    await user.type(screen.getByLabelText('Новый пароль'), 'Yangi-Mustahkam-77');
    await user.type(screen.getByLabelText('Повторите новый пароль'), 'Yangi-Mustahkam-77');
    await user.click(screen.getByRole('button', { name: 'Сохранить пароль' }));
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Пароль слишком распространён');
    expect(alert).toHaveTextContent('Пароль совпадает с одним из пяти последних');
    await user.click(screen.getByRole('button', { name: 'Сохранить пароль' }));
    expect(await screen.findByText('Текущий пароль указан неверно')).toBeInTheDocument();
    expect(screen.getByLabelText('Текущий пароль')).toHaveAttribute('aria-invalid', 'true');
  });

  it('changes the password and continues', async () => {
    const server = mockApi({ 'POST /auth/password/change': { status: 204 }, 'GET /auth/me': json(ME_ADMIN) });
    const { user } = renderWithProviders(<PasswordChangePage me={forcedMe} />, { hash: '#password' });
    await user.type(screen.getByLabelText('Текущий пароль'), 'Old-Parol-2025!');
    await user.type(screen.getByLabelText('Новый пароль'), 'Yangi-Mustahkam-77');
    await user.type(screen.getByLabelText('Повторите новый пароль'), 'Yangi-Mustahkam-77');
    await user.click(screen.getByRole('button', { name: 'Сохранить пароль' }));
    await waitFor(() => expect(window.location.hash).toBe(''));
    expect(server.calls[0]?.body).toEqual({ current_password: 'Old-Parol-2025!', new_password: 'Yangi-Mustahkam-77' });
    expect(await screen.findByText('Пароль изменён')).toBeInTheDocument();
  });
});
