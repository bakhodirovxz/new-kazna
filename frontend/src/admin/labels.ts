import type { UserOut } from '../api/types';
import { t } from '../i18n';
import { formatDateTime } from '../i18n/format';
import type { BadgeTone } from '../ui/Badge';

export function userStatus(user: UserOut, now = Date.now()): { tone: BadgeTone; label: string } {
  if (!user.is_active) return { tone: 'neg', label: t('users.status.blocked') };
  if (user.locked_until && Date.parse(user.locked_until) > now) {
    return { tone: 'warn', label: t('users.status.locked', { time: formatDateTime(user.locked_until) }) };
  }
  return { tone: 'ok', label: t('users.status.active') };
}
