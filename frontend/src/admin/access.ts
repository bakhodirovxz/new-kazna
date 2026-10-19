import type { MessageKey } from '../i18n';
import type { IconName } from '../ui/icons';

export type AdminPageId = 'users' | 'roles' | 'alerts' | 'finmodel' | 'etl' | 'builds' | 'audit' | 'keys';

export interface AdminPageDef {
  id: AdminPageId;
  perm: string;
  titleKey: MessageKey;
  icon: IconName;
}

/** Spec 7.6 admin sahifalari va ularni ochuvchi ruxsatlar (tekshiruv baribir serverda). */
export const ADMIN_PAGES: readonly AdminPageDef[] = [
  { id: 'users', perm: 'admin:users', titleKey: 'admin.page.users', icon: 'people' },
  { id: 'roles', perm: 'admin:roles', titleKey: 'admin.page.roles', icon: 'shield' },
  { id: 'alerts', perm: 'admin:settings', titleKey: 'admin.page.alerts', icon: 'alert' },
  { id: 'finmodel', perm: 'admin:settings', titleKey: 'admin.page.finmodel', icon: 'net' },
  { id: 'etl', perm: 'admin:etl', titleKey: 'admin.page.etl', icon: 'refresh' },
  { id: 'builds', perm: 'admin:etl', titleKey: 'admin.page.builds', icon: 'layers' },
  { id: 'audit', perm: 'audit:read', titleKey: 'admin.page.audit', icon: 'history' },
  { id: 'keys', perm: 'admin:keys', titleKey: 'admin.page.keys', icon: 'key' },
];

export function allowedAdminPages(permissions: readonly string[]): AdminPageDef[] {
  return ADMIN_PAGES.filter((page) => permissions.includes(page.perm));
}
