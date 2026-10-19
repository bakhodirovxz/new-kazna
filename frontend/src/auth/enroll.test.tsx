import { screen, waitFor, within } from '@testing-library/react';
import { StrictMode, useEffect, useRef, useState, type ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { expectNoAxeViolations } from '../test/axe';
import { ME_ADMIN } from '../test/fixtures';
import { apiError, json, mockApi } from '../test/mockApi';
import { renderWithProviders } from '../test/render';
import { useAuthFlow } from './AuthFlow';
import { backupCodesFilename, backupCodesText } from './BackupCodes';
import { Routes } from '../app/Routes';
import { MfaEnrollPage } from './MfaEnrollPage';

const TOKEN = 't'.repeat(32);
const SECRET = 'JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP';
const CODES = ['ABCD-EFGH-JKMN', 'BCDE-FGHJ-KMNP', 'CDEF-GHJK-MNPQ', 'DEFG-HJKM-NPQR', 'EFGH-JKMN-PQRS', 'FGHJ-KMNP-QRST', 'GHJK-MNPQ-RSTU', 'HJKM-NPQR-STUV', 'JKMN-PQRS-TUVW', 'KMNP-QRST-UVWX'];

function WithEnrollChallenge({ children }: { children: ReactNode }) {
  const flow = useAuthFlow();
  const started = useRef(false);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    flow.begin({ mfaToken: TOKEN, step: 'mfa_enroll', username: 'novikov', returnTo: 'kazna/svod' });
    setReady(true);
  }, [flow]);
  return ready ? <>{children}</> : null;
}

function enrollRoutes() {
  let attempts = 0;
  return mockApi({
    'POST /auth/2fa/enroll/start': json({
      otpauth_uri: `otpauth://totp/UGEKAZNA:novikov?secret=${SECRET}&issuer=UGEKAZNA`,
      qr_svg_data_uri: 'data:image/svg+xml;base64,PHN2Zy8+',
      secret: SECRET,
    }),
    'POST /auth/2fa/enroll/confirm': () => {
      attempts += 1;
      return attempts === 1
        ? apiError(401, 'invalid_mfa_code', 'Неверный код подтверждения')
        : json({ user: { ...ME_ADMIN, username: 'novikov', must_change_password: true }, backup_codes: CODES });
    },
  });
}

describe('MfaEnrollPage', () => {
  it('redirects to login without an enrollment challenge', async () => {
    renderWithProviders(<MfaEnrollPage />, { hash: '#2fa/setup' });
    await waitFor(() => expect(window.location.hash).toBe('#login'));
  });

  it('starts once (even in StrictMode) and shows the QR code and grouped key', async () => {
    const server = enrollRoutes();
    const { user } = renderWithProviders(
      <StrictMode>
        <WithEnrollChallenge>
          <MfaEnrollPage />
        </WithEnrollChallenge>
      </StrictMode>,
      { hash: '#2fa/setup' },
    );
    const qr = await screen.findByRole('img', { name: 'QR-код для подключения приложения-аутентификатора' });
    expect(qr).toHaveAttribute('src', 'data:image/svg+xml;base64,PHN2Zy8+');
    expect(screen.getByTestId('totp-secret')).toHaveTextContent('JBSW Y3DP EHPK 3PXP JBSW Y3DP EHPK 3PXP');
    expect(screen.getByText('Шаг 1 из 2')).toBeInTheDocument();
    expect(server.calls.filter((c) => c.path === '/auth/2fa/enroll/start')).toHaveLength(1);
    const write = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue(undefined); // user-event o'z clipboard'ini o'rnatadi
    await user.click(screen.getByRole('button', { name: 'Скопировать' }));
    expect(write).toHaveBeenCalledWith(SECRET);
  });

  it('confirms the code, shows backup codes and continues to the password step', async () => {
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    const server = enrollRoutes();
    const { user } = renderWithProviders(
      <WithEnrollChallenge>
        <MfaEnrollPage />
      </WithEnrollChallenge>,
      { hash: '#2fa/setup' },
    );
    await screen.findByTestId('totp-secret');
    await user.type(screen.getByLabelText('Код из приложения'), '000000');
    await user.click(screen.getByRole('button', { name: 'Подтвердить' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Неверный код подтверждения');
    await user.type(screen.getByLabelText('Код из приложения'), '123456');
    await user.keyboard('{Enter}');
    expect(await screen.findByRole('heading', { name: 'Резервные коды' })).toBeInTheDocument();
    const list = screen.getByTestId('backup-codes');
    expect(within(list).getAllByRole('listitem')).toHaveLength(10);
    expect(server.calls.find((c) => c.path === '/auth/2fa/enroll/confirm' && (c.body as { code: string }).code === '123456')).toBeTruthy();

    await user.click(screen.getByRole('button', { name: 'Скачать' }));
    expect(URL.createObjectURL).toHaveBeenCalledOnce();
    const anchor = click.mock.contexts[0] as HTMLAnchorElement;
    expect(anchor.download).toBe('ugekazna-backup-codes-novikov.txt');

    const next = screen.getByRole('button', { name: 'Продолжить' });
    expect(next).toBeDisabled();
    await user.click(screen.getByLabelText('Я сохранил резервные коды в надёжном месте'));
    expect(next).toBeEnabled();
    await user.click(next);
    await waitFor(() => expect(window.location.hash).toBe('#password'));
  });

  it('has no axe violations on the backup codes step', async () => {
    enrollRoutes();
    const { container, user } = renderWithProviders(
      <WithEnrollChallenge>
        <MfaEnrollPage />
      </WithEnrollChallenge>,
      { hash: '#2fa/setup' },
    );
    await screen.findByTestId('totp-secret');
    await expectNoAxeViolations(container);
    await user.type(screen.getByLabelText('Код из приложения'), '000000');
    await user.click(screen.getByRole('button', { name: 'Подтвердить' }));
    await screen.findByRole('alert');
    await user.type(screen.getByLabelText('Код из приложения'), '123456');
    await user.keyboard('{Enter}');
    await screen.findByTestId('backup-codes');
    await expectNoAxeViolations(container);
  });
});

describe('backup codes file', () => {
  it('lists every code with a header', () => {
    const text = backupCodesText(CODES, 'novikov', new Date('2026-09-24T05:00:00Z'));
    const lines = text.split(String.fromCharCode(13, 10));
    expect(lines[0]).toBe('UGEKAZNA — резервные коды двухфакторной аутентификации');
    expect(lines).toContain('Пользователь: novikov');
    expect(lines).toContain('Создано: 24.09.2026 10:00');
    expect(lines).toContain(' 1. ABCD-EFGH-JKMN');
    expect(lines).toContain('10. KMNP-QRST-UVWX');
    expect(backupCodesFilename('novikov')).toBe('ugekazna-backup-codes-novikov.txt');
  });
});

describe('routing and secret hygiene', () => {
  it('routes #2fa/setup to the enrollment page (not RequireAuth)', async () => {
    mockApi({});
    renderWithProviders(<Routes />, { hash: '#2fa/setup' });
    await waitFor(() => expect(window.location.hash).toBe('#login'));
  });

  it('drops the secret and the backup codes from the DOM after continuing', async () => {
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    enrollRoutes();
    const { user, client } = renderWithProviders(
      <WithEnrollChallenge>
        <MfaEnrollPage />
      </WithEnrollChallenge>,
      { hash: '#2fa/setup' },
    );
    await screen.findByTestId('totp-secret');
    await user.type(screen.getByLabelText('Код из приложения'), '000000');
    await user.click(screen.getByRole('button', { name: 'Подтвердить' }));
    await screen.findByRole('alert');
    expect(screen.getByLabelText('Код из приложения')).toHaveValue('');
    expect(screen.getByLabelText('Код из приложения')).toHaveFocus();
    await user.type(screen.getByLabelText('Код из приложения'), '123456');
    await user.keyboard('{Enter}');
    const heading = await screen.findByRole('heading', { name: 'Резервные коды' });
    expect(heading).toHaveFocus();
    expect(screen.queryByTestId('totp-secret')).not.toBeInTheDocument();
    expect(document.title).not.toContain(SECRET);
    expect(document.body.textContent).not.toContain(SECRET);
    await user.click(screen.getByRole('button', { name: 'Скачать' }));
    await vi.waitFor(() => expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:ugk-test'), { timeout: 3000 });
    await user.click(screen.getByLabelText('Я сохранил резервные коды в надёжном месте'));
    await user.click(screen.getByRole('button', { name: 'Продолжить' }));
    await waitFor(() => expect(window.location.hash).toBe('#password'));
    const stored = JSON.stringify({ ...sessionStorage }) + JSON.stringify({ ...localStorage });
    for (const needle of [SECRET, CODES[0], 'otpauth']) expect(stored).not.toContain(needle);
    expect(client.getMutationCache().getAll()).toHaveLength(0);
  });
});

describe('enrollment errors', () => {
  it('locks the form when the challenge expired and offers to sign in again', async () => {
    mockApi({
      'POST /auth/2fa/enroll/start': json({ otpauth_uri: 'otpauth://x', qr_svg_data_uri: 'data:image/svg+xml;base64,PHN2Zy8+', secret: SECRET }),
      'POST /auth/2fa/enroll/confirm': apiError(401, 'mfa_expired', 'Время подтверждения истекло'),
    });
    const { user } = renderWithProviders(
      <WithEnrollChallenge>
        <MfaEnrollPage />
      </WithEnrollChallenge>,
      { hash: '#2fa/setup' },
    );
    await screen.findByTestId('totp-secret');
    expect(screen.getByLabelText('Код из приложения')).toHaveFocus();
    await user.type(screen.getByLabelText('Код из приложения'), '000000');
    await user.click(screen.getByRole('button', { name: 'Подтвердить' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Время подтверждения истекло');
    expect(screen.getByLabelText('Код из приложения')).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Подтвердить' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Войти заново' })).toBeEnabled();
  });

  it('retries a failed enroll/start', async () => {
    let n = 0;
    const server = mockApi({
      'POST /auth/2fa/enroll/start': () => {
        n += 1;
        return n === 1
          ? apiError(500, 'internal', 'Ошибка сервера')
          : json({ otpauth_uri: 'otpauth://x', qr_svg_data_uri: 'data:image/svg+xml;base64,PHN2Zy8+', secret: SECRET });
      },
    });
    const { user } = renderWithProviders(
      <WithEnrollChallenge>
        <MfaEnrollPage />
      </WithEnrollChallenge>,
      { hash: '#2fa/setup' },
    );
    await user.click(await screen.findByRole('button', { name: 'Повторить' }));
    await screen.findByTestId('totp-secret');
    expect(server.calls.filter((c) => c.path === '/auth/2fa/enroll/start')).toHaveLength(2);
  });

  it('clears the consumed challenge when unmounted on the backup codes step without continuing', async () => {
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    const server = mockApi({
      'POST /auth/2fa/enroll/start': json({ otpauth_uri: 'otpauth://totp/x?secret=' + SECRET, qr_svg_data_uri: 'data:image/svg+xml;base64,PHN2Zy8+', secret: SECRET }),
      'POST /auth/2fa/enroll/confirm': json({ user: { ...ME_ADMIN, username: 'novikov' }, backup_codes: CODES }),
    });
    void server;
    function Harness() {
      const flow = useAuthFlow();
      const [show, setShow] = useState(true);
      return (
        <>
          <output data-testid="challenge">{flow.challenge ? 'set' : 'none'}</output>
          <button type="button" onClick={() => setShow(false)}>
            hide
          </button>
          {show ? <MfaEnrollPage /> : null}
        </>
      );
    }
    const { user } = renderWithProviders(
      <WithEnrollChallenge>
        <Harness />
      </WithEnrollChallenge>,
      { hash: '#2fa/setup' },
    );
    await screen.findByTestId('totp-secret');
    await user.type(screen.getByLabelText('Код из приложения'), '123456');
    await user.keyboard('{Enter}');
    await screen.findByTestId('backup-codes');
    expect(screen.getByTestId('challenge')).toHaveTextContent('set');
    await user.click(screen.getByRole('button', { name: 'hide' }));
    expect(screen.getByTestId('challenge')).toHaveTextContent('none');
  });
});
