import { Suspense, useEffect, type ReactNode } from 'react';
import type { MeOut, MenuOut } from '../api/types';
import { useDocumentTitle } from '../app/useDocumentTitle';
import { t } from '../i18n';
import { buildHash, type Route } from '../router/hash';
import { navigate } from '../router/store';
import { SectionPlaceholder } from '../sections/SectionPlaceholder';
import { AppFrame } from '../shell/AppFrame';
import { PageHeader } from '../shell/PageHeader';
import type { SideModel } from '../shell/SideMenu';
import { StatusScreen } from '../shell/StatusScreen';
import { PageSkeleton } from '../ui/Skeleton';
import { ADMIN_PAGES, allowedAdminPages } from './access';
import { ADMIN_COMPONENTS } from './registry';
import './admin.css';

export type AdminRoute = Extract<Route, { kind: 'admin' }>;

export function AdminScreen({ me, menu, route, tools }: { me: MeOut; menu: MenuOut; route: AdminRoute; tools?: ReactNode }) {
  const allowed = allowedAdminPages(me.permissions);
  const known = ADMIN_PAGES.some((page) => page.id === route.page);
  const requested = allowed.find((page) => page.id === route.page);
  const forbidden = known && !requested;
  const current = requested ?? (forbidden ? undefined : allowed[0]);

  useEffect(() => {
    if (current && route.page !== current.id) navigate({ kind: 'admin', page: current.id }, { replace: true });
  }, [current, route.page]);

  useDocumentTitle(current ? `${t(current.titleKey)} | ${t('admin.title')}` : null);

  if (!current) return <StatusScreen kind="noaccess" menu={menu} tools={tools} />;

  const side: SideModel = {
    title: t('admin.title'),
    desc: t('admin.desc'),
    icon: 'shield',
    activeId: current.id,
    items: allowed.map((page) => ({
      id: page.id,
      label: t(page.titleKey),
      icon: page.icon,
      href: buildHash({ kind: 'admin', page: page.id }),
    })),
  };
  const Page = ADMIN_COMPONENTS[current.id];

  return (
    <AppFrame menu={menu} activeSection={null} side={side} tools={tools}>
      <PageHeader crumb={t('admin.title')} title={t(current.titleKey)} />
      <div className="view">
        {Page ? (
          <Suspense fallback={<PageSkeleton />}>
            <Page me={me} />
          </Suspense>
        ) : (
          <SectionPlaceholder title={t(current.titleKey)} />
        )}
      </div>
    </AppFrame>
  );
}
