import { useEffect, useRef, useState, type FormEvent } from 'react';
import { isApiError } from '../api/client';
import { useDocumentTitle } from '../app/useDocumentTitle';
import { t } from '../i18n';
import { navigate } from '../router/store';
import { Button } from '../ui/Button';
import { OtpInput } from '../ui/OtpInput';
import { useVerifyMfa } from './api';
import { AuthAlert, AuthLayout } from './AuthLayout';
import { useAuthFlow } from './AuthFlow';
import { destinationAfterSignIn } from './destination';
import { authErrorText } from './errors';

type Mode = 'totp' | 'backup';

function isComplete(code: string, mode: Mode): boolean {
  return mode === 'totp' ? /^\d{6}$/.test(code) : /^[A-Z0-9]{4}-?[A-Z0-9]{4}-?[A-Z0-9]{4}$/.test(code);
}

export function MfaVerifyPage() {
  const flow = useAuthFlow();
  const verify = useVerifyMfa();
  const [mode, setMode] = useState<Mode>('totp');
  const [code, setCode] = useState('');
  const [error, setError] = useState<string | null>(null);
  const inFlight = useRef(false);
  /** true — sahifa o'zi boshqa joyga o'tkazdi; challenge tozalangani uchun login'ga qaytarmaymiz. */
  const leaving = useRef(false);
  const challenge = flow.challenge;
  const valid = challenge !== null && challenge.step === 'mfa_verify';
  useDocumentTitle(t('mfa.docTitle'));

  useEffect(() => {
    if (!valid && !leaving.current) navigate({ kind: 'login', next: flow.returnTo }, { replace: true });
  }, [valid, flow.returnTo]);

  if (!challenge || !valid) return null;

  /** Bitta so'rov: avto-yuborish, Enter va tugma bir vaqtda kelsa ham (TOTP replay himoyasi). */
  const submit = (value: string) => {
    if (inFlight.current) return;
    if (!isComplete(value, mode)) {
      setError(t('mfa.codeIncomplete'));
      return;
    }
    inFlight.current = true;
    setError(null);
    verify.mutate(
      { mfa_token: challenge.mfaToken, code: value },
      {
        onSuccess: (me) => {
          const returnTo = challenge.returnTo;
          leaving.current = true;
          verify.reset(); // kod/token kuzatuvchida qolmasin
          navigate(destinationAfterSignIn(me, returnTo), { replace: true });
          flow.finish();
        },
        onError: (err) => {
          setCode('');
          setError(authErrorText(err));
        },
        onSettled: () => {
          inFlight.current = false;
        },
      },
    );
  };

  const restart = () => {
    const returnTo = challenge.returnTo;
    leaving.current = true;
    navigate({ kind: 'login', next: returnTo });
    flow.clear();
  };

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    submit(code);
  };

  const expired = isApiError(verify.error, 401, 'mfa_expired');

  return (
    <AuthLayout>
      <h1>{t('mfa.title')}</h1>
      <p className="auth__lead">{mode === 'totp' ? t('mfa.lead') : t('mfa.leadBackup')}</p>
      <form className="auth__form" noValidate onSubmit={onSubmit}>
        {error ? <AuthAlert message={error} /> : null}
        <OtpInput
          key={mode}
          label={mode === 'totp' ? t('mfa.codeLabel') : t('mfa.backupLabel')}
          mode={mode}
          value={code}
          onChange={setCode}
          onComplete={submit}
          focusOnMount
        />
        <Button type="submit" block loading={verify.isPending} disabled={expired}>
          {t('mfa.submit')}
        </Button>
      </form>
      <div className="auth__links">
        {!expired ? (
          <button
            type="button"
            className="linkbtn"
            onClick={() => {
              setMode((m) => (m === 'totp' ? 'backup' : 'totp'));
              setCode('');
              setError(null);
            }}
          >
            {mode === 'totp' ? t('mfa.useBackup') : t('mfa.useTotp')}
          </button>
        ) : null}
        <button type="button" className="linkbtn" onClick={restart}>
          {t('mfa.backToLogin')}
        </button>
      </div>
    </AuthLayout>
  );
}
