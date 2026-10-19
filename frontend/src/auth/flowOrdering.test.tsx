import { screen, waitFor } from '@testing-library/react';
import { flushSync } from 'react-dom';
import { describe, expect, it } from 'vitest';
import { Routes } from '../app/Routes';
import { ME_ADMIN } from '../test/fixtures';
import { apiError, json, mockApi } from '../test/mockApi';
import { renderWithProviders } from '../test/render';
import { navigate } from '../router/store';
import { useAuthFlow } from './AuthFlow';

// Brauzer tartibi: AuthFlow (sinxron store), router va React holati act() siz alohida commit bo'ladi.
// act() hammasini bitta commit'ga birlashtirib, guard-effect xatolarini yashiradi, shuning uchun bu fayl alohida
// (yangi modul, async RTL testlaridan oldin) va begin()+flushSync(navigate()) ni act'siz chaqiradi.

const TOKEN = 't'.repeat(32);
const SECRET = 'JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP';
const CODES = ['ABCD-EFGH-JKMN', 'BCDE-FGHJ-KMNP'];

function enrollApi() {
  return mockApi({
    'POST /auth/2fa/enroll/start': json({ otpauth_uri: 'otpauth://x', qr_svg_data_uri: 'data:image/svg+xml;base64,PHN2Zy8+', secret: SECRET }),
    // Kechikish: javob click'ning act() doirasidan keyin keladi (brauzerdagidek), aks holda yangilanishlar birlashadi.
    'POST /auth/2fa/enroll/confirm': async () => {
      await new Promise((resolve) => setTimeout(resolve, 30));
      return json({ user: { ...ME_ADMIN, username: 'novikov', must_change_password: true }, backup_codes: CODES });
    },
    'POST /auth/2fa/verify': apiError(401, 'invalid_mfa_code', 'Неверный код'),
  });
}

let flow!: ReturnType<typeof useAuthFlow>;

async function beginThenNavigate(step: 'mfa_enroll' | 'mfa_verify', route: 'mfaEnroll' | 'mfa') {
  const Probe = () => {
    flow = useAuthFlow();
    return null;
  };
  const rendered = renderWithProviders(
    <>
      <Probe />
      <Routes />
    </>,
    { hash: '#login' },
  );
  const g = globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean };
  const prev = g.IS_REACT_ACT_ENVIRONMENT;
  g.IS_REACT_ACT_ENVIRONMENT = false;
  try {
    flow.begin({ mfaToken: TOKEN, step, username: 'novikov', returnTo: null });
    flushSync(() => navigate({ kind: route }));
    await new Promise((resolve) => setTimeout(resolve, 50));
  } finally {
    g.IS_REACT_ACT_ENVIRONMENT = prev;
  }
  return rendered;
}

describe('flow ordering in a real browser', () => {
  it('C3: backup codes stay on screen after confirm (no redirect to login); continue goes on', async () => {
    enrollApi();
    const { user } = await beginThenNavigate('mfa_enroll', 'mfaEnroll');
    await screen.findByTestId('totp-secret');
    await user.type(screen.getByLabelText('Код из приложения'), '123456');
    await user.click(screen.getByRole('button', { name: 'Подтвердить' }));
    expect(await screen.findByTestId('backup-codes')).toBeInTheDocument();
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(window.location.hash).toBe('#2fa/setup');
    expect(screen.getByTestId('backup-codes')).toBeInTheDocument();
    // Oqim kodlar ekranda turganda tugamasligi kerak: store sinxron, React holati esa keyin commit bo'ladi.
    expect(flow.challenge).not.toBeNull();
    await user.click(screen.getByLabelText('Я сохранил резервные коды в надёжном месте'));
    await user.click(screen.getByRole('button', { name: 'Продолжить' }));
    await waitFor(() => expect(window.location.hash).toBe('#password'));
    expect(flow.challenge).toBeNull();
  });

  it('C1: enrollment page keeps the route and starts enrollment', async () => {
    const server = enrollApi();
    await beginThenNavigate('mfa_enroll', 'mfaEnroll');
    expect(window.location.hash).toBe('#2fa/setup');
    await screen.findByTestId('totp-secret');
    expect(server.calls.filter((c) => c.path === '/auth/2fa/enroll/start')).toHaveLength(1);
  });

  it('C1: verify page keeps the route', async () => {
    enrollApi();
    await beginThenNavigate('mfa_verify', 'mfa');
    expect(window.location.hash).toBe('#2fa');
    expect(await screen.findByRole('heading', { name: 'Подтверждение входа' })).toBeInTheDocument();
  });

});
