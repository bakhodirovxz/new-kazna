import { useState } from 'react';
import type { UserOut } from '../api/types';
import { t } from '../i18n';
import { formatDateTime } from '../i18n/format';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { Card } from '../ui/Card';
import { ErrorBanner } from '../ui/ErrorBanner';
import { TextInput } from '../ui/Field';
import { Pagination } from '../ui/Pagination';
import { PageSkeleton } from '../ui/Skeleton';
import { Table, type Column } from '../ui/Table';
import { useDebouncedValue } from '../ui/useDebouncedValue';
import { USERS_PAGE_SIZE, usePositions, useUsers } from './api';
import { userStatus } from './labels';
import type { AdminPageProps } from './registry';
import { TemporaryPasswordDialog, UserCreateDialog, UserEditDialog } from './UserDialogs';

type DialogState = { kind: 'create' } | { kind: 'edit'; user: UserOut } | null;

export default function UsersPage({ me }: AdminPageProps) {
  const [search, setSearch] = useState('');
  const q = useDebouncedValue(search.trim().toLowerCase(), 300);
  // Sahifa shu so'rov (q) uchun; q o'zgarsa 1-sahifa: eski q bilan ortiqcha so'rov ketmaydi.
  const [paged, setPaged] = useState({ q, page: 1 });
  const page = paged.q === q ? paged.page : 1;
  const setPage = (next: number) => setPaged({ q, page: next });
  const users = useUsers(q, page);
  const positions = usePositions();
  const [dialog, setDialog] = useState<DialogState>(null);
  const [secret, setSecret] = useState<{ username: string; password: string } | null>(null);

  const columns: Column<UserOut>[] = [
    {
      key: 'user',
      header: t('users.col.user'),
      align: 'left',
      sortValue: (u) => u.full_name,
      cell: (u) => (
        <span className="cell-main">
          <b>{u.full_name}</b>
          <small className="mono">{u.username}</small>
        </span>
      ),
    },
    { key: 'position', header: t('users.col.position'), align: 'left', wrap: true, sortValue: (u) => u.position.name, cell: (u) => u.position.name },
    { key: 'role', header: t('users.col.role'), align: 'left', cell: (u) => <span className="mono">{u.role_code}</span> },
    {
      key: 'mfa',
      header: t('users.col.mfa'),
      align: 'left',
      cell: (u) => <Badge tone={u.totp_enabled ? 'ok' : 'warn'}>{u.totp_enabled ? t('users.mfaOn') : t('users.mfaOff')}</Badge>,
    },
    {
      key: 'status',
      header: t('users.col.status'),
      align: 'left',
      cell: (u) => {
        const status = userStatus(u);
        return <Badge tone={status.tone}>{status.label}</Badge>;
      },
    },
    {
      key: 'login',
      header: t('users.col.lastLogin'),
      sortValue: (u) => u.last_login_at,
      cell: (u) => (u.last_login_at ? formatDateTime(u.last_login_at) : t('common.dash')),
    },
  ];

  return (
    <>
      <Card>
        <div className="toolbar">
          <TextInput
            type="search"
            label={t('users.search')}
            placeholder={t('users.searchPlaceholder')}
            value={search}
            maxLength={64}
            onChange={(e) => {
              setSearch(e.target.value);
            }}
          />
          <span className="toolbar__grow" />
          <Button icon="plus" onClick={() => setDialog({ kind: 'create' })}>
            {t('users.add')}
          </Button>
        </div>
        {users.isError ? (
          <ErrorBanner error={users.error} lastSuccessAt={users.dataUpdatedAt} onRetry={() => void users.refetch()} />
        ) : users.isPending ? (
          <PageSkeleton />
        ) : (
          <>
            <Table
              caption={t('admin.page.users')}
              columns={columns}
              rows={users.data.items}
              rowKey={(u) => u.id}
              onRowClick={(u) => setDialog({ kind: 'edit', user: u })}
              empty={q ? t('users.notFound') : undefined}
            />
            <Pagination page={page} pageSize={USERS_PAGE_SIZE} total={users.data.total} onPage={setPage} />
          </>
        )}
      </Card>
      {dialog?.kind === 'create' ? (
        <UserCreateDialog
          positions={positions.data ?? []}
          positionsFailed={positions.isError}
          onClose={() => setDialog(null)}
          onCreated={(user, password) => {
            setDialog(null);
            setSecret({ username: user.username, password });
          }}
        />
      ) : null}
      {dialog?.kind === 'edit' ? (
        <UserEditDialog
          me={me}
          user={users.data?.items.find((u) => u.id === dialog.user.id) ?? dialog.user}
          positions={positions.data ?? []}
          positionsFailed={positions.isError}
          onClose={() => setDialog(null)}
          onTemporaryPassword={(username, password) => {
            setDialog(null);
            setSecret({ username, password });
          }}
        />
      ) : null}
      {secret ? <TemporaryPasswordDialog username={secret.username} password={secret.password} onClose={() => setSecret(null)} /> : null}
    </>
  );
}
