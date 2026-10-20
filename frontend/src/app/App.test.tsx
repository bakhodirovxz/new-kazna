import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { FRESH_OK, ME_ADMIN, shellRoutes } from '../test/fixtures';
import { apiError, json, mockApi, type MockHandler } from '../test/mockApi';
import { App } from './App';
import type * as RoutesModule from './Routes';

const crash = vi.hoisted(() => ({ on: false }));
vi.mock('./Routes', async () => {
  const actual = await vi.importActual<typeof RoutesModule>('./Routes');
  return {
    Routes: () => {
      if (crash.on) throw new Error('boom');
      return actual.Routes();
    },
  };
});

const TOKEN = 't'.repeat(32);

function withMe(handler: MockHandler): Record<string, MockHandler> {
  return { ...shellRoutes(), 'GET /auth/me': handler };
}

describe('App root boundary', () => {
  it('shows the full-page error instead of a white screen when rendering throws', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    mockApi(withMe(json(ME_ADMIN)));
    crash.on = true;
    try {
      render(<App />);
      expect(await screen.findByRole('alert')).toHaveTextContent('Не удалось загрузить приложение');
      expect(screen.getByRole('button', { name: 'Повторить' })).toBeInTheDocument();
    } finally {
      crash.on = false;
    }
  });
});

describe('App routing', () => {
  it('redirects an anonymous visitor to login with the return path', async () => {
    mockApi(withMe(apiError(401, 'unauthenticated', 'Требуется вход в систему')));
    window.history.replaceState(null, '', '#kazna/svod?br=3');
    render(<App />);
    await waitFor(() => expect(window.location.hash).toBe('#login?next=kazna%2Fsvod%3Fbr%3D3'));
    expect(await screen.findByRole('heading', { name: 'Вход в систему' })).toBeInTheDocument();
  });

  it('returns to the original page with filters after re-login', async () => {
    let signedIn = false;
    mockApi({
      ...withMe(() => (signedIn ? json(ME_ADMIN) : apiError(401, 'session_expired', 'Сеанс завершён, войдите снова'))),
      'POST /auth/login': json({ next: 'mfa_verify', mfa_token: TOKEN }),
      'POST /auth/2fa/verify': () => {
        signedIn = true;
        return json(ME_ADMIN);
      },
    });
    window.history.replaceState(null, '', '#kazna/svod?br=3');
    const user = userEvent.setup();
    render(<App />);
    await user.type(await screen.findByLabelText('Логин'), 'admin');
    await user.type(screen.getByLabelText('Пароль'), 'Secret-Parol-1');
    await user.click(screen.getByRole('button', { name: 'Войти' }));
    await user.type(await screen.findByLabelText('Код из приложения'), '123456');
    expect(await screen.findByRole('heading', { level: 1, name: 'Казначейство: сводка' })).toBeInTheDocument();
    expect(window.location.hash).toBe('#kazna/svod?br=3');
    expect(screen.getByRole('button', { name: 'Меню пользователя: Азимов Бахтиёр' })).toBeInTheDocument();
  });

  it('forces the password change before anything else', async () => {
    let changed = false;
    mockApi({
      ...withMe(() => json({ ...ME_ADMIN, must_change_password: !changed })),
      'POST /auth/password/change': () => {
        changed = true;
        return { status: 204 };
      },
    });
    window.history.replaceState(null, '', '#obzor/svod');
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => expect(window.location.hash).toBe('#password'));
    await user.type(await screen.findByLabelText('Текущий пароль'), 'Temp-Parol-2026!');
    await user.type(screen.getByLabelText('Новый пароль'), 'Yangi-Mustahkam-77');
    await user.type(screen.getByLabelText('Повторите новый пароль'), 'Yangi-Mustahkam-77');
    await user.click(screen.getByRole('button', { name: 'Сохранить пароль' }));
    await waitFor(() => expect(window.location.hash).toBe('#obzor/svod'));
    expect(await screen.findByRole('heading', { level: 1, name: 'Обзор: сводка' })).toBeInTheDocument();
  });

  it('sends password_change_required from any request to the password page', async () => {
    mockApi({
      ...withMe(json(ME_ADMIN)),
      'GET /meta/menu': apiError(403, 'password_change_required', 'Необходимо сменить пароль'),
    });
    window.history.replaceState(null, '', '#obzor/svod');
    render(<App />);
    await waitFor(() => expect(window.location.hash).toBe('#password'));
    // M4: kesh yangilanadi, majburiy rejim («Назад» yo'q)
    expect(await screen.findByRole('heading', { name: 'Необходимо сменить пароль' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Назад' })).not.toBeInTheDocument();
  });

  it('returns to the original page with filters after a mid-session 401 from a non-silent query', async () => {
    let signedIn = false;
    mockApi({
      ...withMe(json(ME_ADMIN)),
      'GET /meta/freshness': () => (signedIn ? json(FRESH_OK) : apiError(401, 'session_expired', 'Сеанс завершён, войдите снова')),
      'POST /auth/login': json({ next: 'mfa_verify', mfa_token: TOKEN }),
      'POST /auth/2fa/verify': () => {
        signedIn = true;
        return json(ME_ADMIN);
      },
    });
    window.history.replaceState(null, '', '#kazna/svod?br=3');
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => expect(window.location.hash).toBe('#login?next=kazna%2Fsvod%3Fbr%3D3'));
    await user.type(await screen.findByLabelText('Логин'), 'admin');
    await user.type(screen.getByLabelText('Пароль'), 'Secret-Parol-1');
    await user.click(screen.getByRole('button', { name: 'Войти' }));
    await user.type(await screen.findByLabelText('Код из приложения'), '123456');
    expect(await screen.findByRole('heading', { level: 1, name: 'Казначейство: сводка' })).toBeInTheDocument();
    expect(window.location.hash).toBe('#kazna/svod?br=3');
  });

  it('keeps the original target through the forced password change', async () => {
    let changed = false;
    mockApi({
      ...withMe(() => json({ ...ME_ADMIN, must_change_password: !changed })),
      'POST /auth/password/change': () => {
        changed = true;
        return { status: 204 };
      },
    });
    window.history.replaceState(null, '', '#kazna/svod?br=3');
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => expect(window.location.hash).toBe('#password'));
    await user.type(await screen.findByLabelText('Текущий пароль'), 'Temp-Parol-2026!');
    await user.type(screen.getByLabelText('Новый пароль'), 'Yangi-Mustahkam-77');
    await user.type(screen.getByLabelText('Повторите новый пароль'), 'Yangi-Mustahkam-77');
    await user.click(screen.getByRole('button', { name: 'Сохранить пароль' }));
    await waitFor(() => expect(window.location.hash).toBe('#kazna/svod?br=3'));
  });

  it('opens the first allowed page from the root', async () => {
    mockApi(withMe(json(ME_ADMIN)));
    window.history.replaceState(null, '', '/');
    render(<App />);
    await waitFor(() => expect(window.location.hash).toBe('#obzor/svod'));
  });
});
