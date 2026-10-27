import { t } from '../i18n';
import { useStartEnrollment } from './api';

/** «Подключить 2FA» — кнопка-ссылка в сообщении «нужна двухфакторная аутентификация» (шаг подтверждения). */
export function EnrollLink() {
  const { start, pending } = useStartEnrollment();
  return (
    <button type="button" className="linkbtn" disabled={pending} onClick={start}>
      {t('user.mfa')}
    </button>
  );
}
