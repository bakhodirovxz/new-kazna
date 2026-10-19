import { useState, type ReactNode } from 'react';
import type { MeOut, MenuOut, SessionOut } from '../api/types';
import { useDocumentTitle } from '../app/useDocumentTitle';
import { t } from '../i18n';
import { formatDateTime } from '../i18n/format';
import { buildHash } from '../router/hash';
import { AppFrame } from '../shell/AppFrame';
import { PageHeader } from '../shell/PageHeader';
import type { SideModel } from '../shell/SideMenu';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { Card } from '../ui/Card';
import { ConfirmDialog } from '../ui/ConfirmDialog';
import { ErrorBanner } from '../ui/ErrorBanner';
import { PageSkeleton } from '../ui/Skeleton';
import { Table, type Column } from '../ui/Table';
import { useToast } from '../ui/Toast';
import { useRevokeSession, useSessions } from './api';

export function SessionsScreen({ me, menu, tools }: { me: MeOut; menu: MenuOut; tools?: ReactNode }) {
  const sessions = useSessions();
  const revoke = useRevokeSession();
  const toast = useToast();
  const [target, setTarget] = useState<SessionOut | null>(null);
  useDocumentTitle(t('sessions.title'));

  const side: SideModel = {
    title: t('account.title'),
    desc: me.full_name,
    icon: 'user',
    activeId: 'sessions',
    items: [
      { id: 'sessions', label: t('user.sessions'), icon: 'history', href: buildHash({ kind: 'sessions' }) },
      { id: 'password', label: t('user.password'), icon: 'key', href: buildHash({ kind: 'password' }) },
    ],
  };

  const columns: Column<SessionOut>[] = [
    {
      key: 'device',
      header: t('sessions.device'),
      align: 'left',
      cell: (s) => (
        <span className="cell-main">
          <b>{s.ua_summary || t('sessions.unknownDevice')}</b>
          {s.current ? <Badge tone="ok">{t('sessions.current')}</Badge> : null}
        </span>
      ),
    },
    { key: 'ip', header: t('sessions.ip'), align: 'left', cell: (s) => s.ip ?? t('common.dash') },
    { key: 'created', header: t('sessions.created'), cell: (s) => formatDateTime(s.created_at), sortValue: (s) => s.created_at },
    { key: 'seen', header: t('sessions.lastSeen'), cell: (s) => formatDateTime(s.last_seen_at), sortValue: (s) => s.last_seen_at },
    {
      key: 'action',
      header: t('sessions.actions'),
      cell: (s) =>
        s.current ? (
          <span className="muted">{t('sessions.thisDevice')}</span>
        ) : (
          <Button variant="secondary" onClick={() => setTarget(s)}>
            {t('sessions.end')}
          </Button>
        ),
    },
  ];

  const close = () => {
    setTarget(null);
    revoke.reset();
  };

  return (
    <AppFrame menu={menu} activeSection={null} side={side} tools={tools}>
      <PageHeader crumb={t('account.title')} title={t('sessions.title')} sub={t('sessions.lead')} />
      <div className="view">
        {sessions.isPending ? (
          <PageSkeleton />
        ) : sessions.isError ? (
          <ErrorBanner error={sessions.error} lastSuccessAt={sessions.dataUpdatedAt} onRetry={() => void sessions.refetch()} />
        ) : (
          <Card>
            <Table
              caption={t('sessions.title')}
              columns={columns}
              rows={sessions.data}
              rowKey={(s) => s.id}
              initialSort={{ key: 'seen', dir: 'desc' }}
              free
            />
          </Card>
        )}
      </div>
      <ConfirmDialog
        open={target !== null}
        title={t('sessions.confirmTitle')}
        message={t('sessions.confirmText', { device: target?.ua_summary || t('sessions.unknownDevice') })}
        confirmLabel={t('sessions.end')}
        danger
        busy={revoke.isPending}
        error={revoke.error}
        onCancel={close}
        onConfirm={() => {
          if (!target) return;
          revoke.mutate(target.id, {
            onSuccess: () => {
              toast.show(t('sessions.ended'), 'success');
              close();
            },
          });
        }}
      />
    </AppFrame>
  );
}
