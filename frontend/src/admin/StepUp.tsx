import { useState, type ReactNode } from 'react';
import { isApiError } from '../api/client';
import { t } from '../i18n';
import { OtpInput } from '../ui/OtpInput';

/** data:*:approve berish 2FA bor adminda TOTP talab qiladi (422 step_up_required/step_up_failed):
 *  maydon shu paytdagina chiqadi, kod qayta yuboriladi (`otp`), har xatodan keyin tozalanadi. */
export function useStepUp() {
  const [asked, setAsked] = useState(false);
  const [otp, setOtp] = useState('');
  const [error, setError] = useState<string | null>(null);

  /** Mutatsiya `onError`ida chaqiriladi; step-up xatosi bo'lsa true. */
  const onError = (e: unknown): boolean => {
    const failed = isApiError(e, 422, 'step_up_failed');
    if (!failed && !isApiError(e, 422, 'step_up_required')) return false;
    setAsked(true);
    setOtp('');
    setError(failed ? e.message : null);
    return true;
  };
  const isStepUp = (e: unknown): boolean =>
    isApiError(e, 422, 'step_up_required') || isApiError(e, 422, 'step_up_failed');
  const body: { otp?: string } = asked && otp ? { otp } : {};
  const field: ReactNode = asked ? (
    <div className="span-2">
      <OtpInput label={t('settings.otp')} hint={t('roles.stepUpHint')} value={otp} onChange={setOtp} error={error} focusOnMount />
    </div>
  ) : null;
  return { onError, isStepUp, body, field };
}
