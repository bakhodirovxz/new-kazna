import { useDocumentTitle } from '../app/useDocumentTitle';
import { t } from '../i18n';
import { Button } from '../ui/Button';
import { useDismissMfaOffer, useStartEnrollment } from './api';
import { AuthAlert, AuthLayout } from './AuthLayout';
import { authErrorText } from './errors';

/** Первый вход без 2FA: предложение подключить (необязательно, решение заказчика 27.10.2026). */
export function MfaOfferScreen() {
  const start = useStartEnrollment();
  const dismiss = useDismissMfaOffer();
  useDocumentTitle(t('mfaOffer.docTitle'));
  return (
    <AuthLayout>
      <h1>{t('mfaOffer.title')}</h1>
      <p className="auth__lead">{t('mfaOffer.lead')}</p>
      {dismiss.error ? <AuthAlert message={authErrorText(dismiss.error)} /> : null}
      <div className="auth__form">
        <Button block onClick={start}>
          {t('mfaOffer.accept')}
        </Button>
        <Button variant="secondary" block loading={dismiss.isPending} onClick={() => dismiss.mutate()}>
          {t('mfaOffer.later')}
        </Button>
      </div>
    </AuthLayout>
  );
}
