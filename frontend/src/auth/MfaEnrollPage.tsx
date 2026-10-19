import { useEffect, useRef, useState, type FormEvent } from 'react';
import { isApiError } from '../api/client';
import type { EnrollConfirmOut } from '../api/types';
import { useDocumentTitle } from '../app/useDocumentTitle';
import { t } from '../i18n';
import { navigate } from '../router/store';
import { Button } from '../ui/Button';
import { OtpInput } from '../ui/OtpInput';
import { Skeleton } from '../ui/Skeleton';
import { useEnrollConfirm, useEnrollStart } from './api';
import { AuthAlert, AuthLayout } from './AuthLayout';
import { useAuthFlow } from './AuthFlow';
import { BackupCodes } from './BackupCodes';
import { destinationAfterSignIn } from './destination';
import { authErrorText } from './errors';

function groupSecret(secret: string): string {
  return secret.replace(/(.{4})/g, '$1 ').trim();
}

export function MfaEnrollPage() {
  const flow = useAuthFlow();
  const start = useEnrollStart();
  const confirm = useEnrollConfirm();
  const [code, setCode] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [expired, setExpired] = useState(false);
  const [result, setResult] = useState<EnrollConfirmOut | null>(null);
  const started = useRef(false);
  const inFlight = useRef(false);
  const formRef = useRef<HTMLFormElement>(null);
  const leaving = useRef(false);
  const shown = useRef(false); // kodlar ko'rsatilgan va 'Продолжить' bosilmagan
  const clear = flow.clear; // store.actions barqaror (flow obyekti esa holat bilan almashadi)
  const challenge = flow.challenge;
  const valid = challenge !== null && challenge.step === 'mfa_enroll';
  useDocumentTitle(t('enroll.docTitle'));

  useEffect(() => {
    if (!valid && !leaving.current && result === null) navigate({ kind: 'login', next: flow.returnTo }, { replace: true });
  }, [valid, result, flow.returnTo]);

  useEffect(() => {
    if (!challenge || !valid || started.current) return;
    started.current = true;
    start.mutate({ mfa_token: challenge.mfaToken });
  }, [challenge, valid, start]);

  useEffect(() => {
    shown.current = result !== null;
  }, [result]);
  useEffect(
    () => () => {
      if (shown.current) clear(); // 'Продолжить'siz ketilsa ishlatilgan mfa challenge xotirada qolmasin
    },
    [clear],
  );

  const enrollment = start.data;
  useEffect(() => {
    if (enrollment) formRef.current?.querySelector('input')?.focus(); // 1-qadam: kod maydoniga
  }, [enrollment]);

  if (result) {
    return (
      <AuthLayout wide>
        <BackupCodes
          codes={result.backup_codes}
          username={result.user.username}
          onContinue={() => {
            const target = destinationAfterSignIn(result.user, flow.returnTo);
            shown.current = false; // finish() returnTo'ni saqlaydi (parol bosqichi uchun)
            flow.finish();
            navigate(target, { replace: true });
          }}
        />
      </AuthLayout>
    );
  }
  if (!challenge || !valid) return null;

  const restart = () => {
    const returnTo = challenge.returnTo;
    leaving.current = true;
    navigate({ kind: 'login', next: returnTo });
    flow.clear();
  };

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (inFlight.current) return;
    if (!/^\d{6}$/.test(code)) {
      setError(t('mfa.codeIncomplete'));
      return;
    }
    setError(null);
    inFlight.current = true;
    confirm.mutate(
      { mfa_token: challenge.mfaToken, code },
      {
        onSuccess: (data) => {
          leaving.current = true; // guard-effect kodlar ko'rsatilguncha login'ga qaytarmasin
          setResult(data);
          start.reset(); // TOTP kaliti xotiradan ketsin
          confirm.reset(); // zaxira kodlar faqat komponent holatida; oqim 'Продолжить'da tugaydi (store sinxron)
        },
        onError: (err) => {
          setCode('');
          setError(authErrorText(err));
          const dead = isApiError(err, 401, 'mfa_expired');
          setExpired(dead);
          inFlight.current = false; // reset() onSettled'ni o'tkazib yuborishi mumkin
          confirm.reset(); // kod/token kuzatuvchida qolmasin
          if (!dead) formRef.current?.querySelector('input')?.focus();
        },
        onSettled: () => {
          inFlight.current = false;
        },
      },
    );
  };

  const copySecret = async (secret: string) => {
    try {
      await navigator.clipboard.writeText(secret);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };

  const dead = expired || isApiError(start.error, 401, 'mfa_expired');
  const retryStart = () => {
    if (start.isPending) return;
    start.reset();
    start.mutate({ mfa_token: challenge.mfaToken });
  };

  return (
    <AuthLayout wide>
      <p className="auth__step">{t('enroll.step', { n: 1, total: 2 })}</p>
      <h1>{t('enroll.title')}</h1>
      <p className="auth__lead">{t('enroll.lead')}</p>
      {start.isPending ? <Skeleton variant="card" /> : null}
      {start.error ? <AuthAlert message={authErrorText(start.error)} /> : null}
      {start.error && !dead ? (
        <Button variant="secondary" onClick={retryStart}>
          {t('common.retry')}
        </Button>
      ) : null}
      {enrollment ? (
        <div className="enroll">
          <img className="enroll__qr" src={enrollment.qr_svg_data_uri} alt={t('enroll.qrAlt')} width={176} height={176} />
          <div className="enroll__body">
            <ol className="enroll__steps">
              <li>{t('enroll.step1')}</li>
              <li>{t('enroll.step2')}</li>
              <li>{t('enroll.step3')}</li>
            </ol>
            <p className="field__label">{t('enroll.manualKey')}</p>
            <div className="secret">
              <code data-testid="totp-secret">{groupSecret(enrollment.secret)}</code>
              <Button variant="secondary" icon="copy" onClick={() => void copySecret(enrollment.secret)}>
                {copied ? t('common.copied') : t('common.copy')}
              </Button>
            </div>
          </div>
        </div>
      ) : null}
      <form ref={formRef} className="auth__form" noValidate onSubmit={onSubmit}>
        {error ? <AuthAlert message={error} /> : null}
        <OtpInput label={t('mfa.codeLabel')} value={code} onChange={setCode} disabled={!enrollment || dead} />
        <Button type="submit" block loading={confirm.isPending} disabled={!enrollment || dead}>
          {t('enroll.confirm')}
        </Button>
      </form>
      <div className="auth__links">
        <button type="button" className="linkbtn" onClick={restart}>
          {t('mfa.backToLogin')}
        </button>
      </div>
    </AuthLayout>
  );
}
