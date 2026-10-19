import { useState } from 'react';
import type { PositionOut, RoleOut } from '../api/types';
import { t } from '../i18n';
import { useBranches } from '../meta/api';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { Card } from '../ui/Card';
import { ErrorBanner } from '../ui/ErrorBanner';
import { PageSkeleton } from '../ui/Skeleton';
import { Table, type Column } from '../ui/Table';
import { Tabs } from '../ui/Tabs';
import { usePermissions, usePositions, useRoles } from './api';
import { PositionDialog } from './PositionDialog';
import { RoleDialog } from './RoleDialog';

type Tab = 'positions' | 'roles';

export default function RolesPage() {
  const [tab, setTab] = useState<Tab>('positions');
  return (
    <Card>
      <Tabs
        label={t('roles.tabs')}
        tabs={[
          { id: 'positions', label: t('roles.tab.positions') },
          { id: 'roles', label: t('roles.tab.roles') },
        ]}
        value={tab}
        onChange={(id) => setTab(id === 'roles' ? 'roles' : 'positions')}
      >
        {tab === 'positions' ? <PositionsPanel /> : <RolesPanel />}
      </Tabs>
    </Card>
  );
}

function PositionsPanel() {
  const positions = usePositions();
  const roles = useRoles();
  const branches = useBranches();
  const [editing, setEditing] = useState<PositionOut | 'new' | null>(null);
  const roleById = new Map((roles.data ?? []).map((r) => [r.id, r]));
  const branchName = new Map((branches.data ?? []).map((b) => [b.id, b.short_name]));

  const columns: Column<PositionOut>[] = [
    { key: 'code', header: t('roles.col.code'), align: 'left', sortValue: (p) => p.code, cell: (p) => <span className="mono">{p.code}</span> },
    { key: 'name', header: t('roles.col.name'), align: 'left', wrap: true, sortValue: (p) => p.name, cell: (p) => p.name },
    { key: 'role', header: t('roles.col.role'), align: 'left', cell: (p) => roleById.get(p.role_id)?.name ?? p.role_code },
    {
      key: 'branches',
      header: t('roles.col.branches'),
      align: 'left',
      wrap: true,
      cell: (p) =>
        roleById.get(p.role_id)?.scope_all
          ? t('roles.allByRole')
          : p.branch_ids.length > 0
            ? p.branch_ids.map((id) => branchName.get(id) ?? String(id)).join(', ')
            : t('common.dash'),
    },
    {
      key: 'status',
      header: t('roles.col.status'),
      align: 'left',
      cell: (p) => <Badge tone={p.is_active ? 'ok' : 'neutral'}>{p.is_active ? t('roles.active') : t('roles.inactive')}</Badge>,
    },
  ];

  if (positions.isError) return <ErrorBanner error={positions.error} onRetry={() => void positions.refetch()} />;
  if (positions.isPending || roles.isPending) return <PageSkeleton />;

  return (
    <>
      <div className="toolbar">
        <span className="toolbar__grow" />
        <Button icon="plus" onClick={() => setEditing('new')}>
          {t('roles.addPosition')}
        </Button>
      </div>
      <Table
        caption={t('roles.tab.positions')}
        columns={columns}
        rows={positions.data}
        rowKey={(p) => p.id}
        onRowClick={(p) => setEditing(p)}
        initialSort={{ key: 'name', dir: 'asc' }}
      />
      {editing !== null ? (
        <PositionDialog
          position={editing === 'new' ? null : editing}
          roles={roles.data ?? []}
          branches={branches.data ?? []}
          onClose={() => setEditing(null)}
        />
      ) : null}
    </>
  );
}

function RolesPanel() {
  const roles = useRoles();
  const permissions = usePermissions();
  const [editing, setEditing] = useState<RoleOut | 'new' | null>(null);
  const total = permissions.data?.length ?? 0;

  const columns: Column<RoleOut>[] = [
    { key: 'code', header: t('roles.col.code'), align: 'left', sortValue: (r) => r.code, cell: (r) => <span className="mono">{r.code}</span> },
    { key: 'name', header: t('roles.col.name'), align: 'left', wrap: true, sortValue: (r) => r.name, cell: (r) => r.name },
    { key: 'scope', header: t('roles.col.scope'), align: 'left', cell: (r) => (r.scope_all ? t('roles.scopeAll') : t('roles.scopePosition')) },
    { key: 'perms', header: t('roles.col.perms'), cell: (r) => t('roles.permCount', { count: r.permissions.length, total }) },
    {
      key: 'type',
      header: t('roles.col.type'),
      align: 'left',
      cell: (r) => <Badge tone={r.is_system ? 'blue' : 'neutral'}>{r.is_system ? t('roles.system') : t('roles.custom')}</Badge>,
    },
  ];

  if (roles.isError) return <ErrorBanner error={roles.error} onRetry={() => void roles.refetch()} />;
  if (roles.isPending || permissions.isPending) return <PageSkeleton />;

  return (
    <>
      <div className="toolbar">
        <span className="toolbar__grow" />
        <Button icon="plus" onClick={() => setEditing('new')}>
          {t('roles.addRole')}
        </Button>
      </div>
      <Table caption={t('roles.tab.roles')} columns={columns} rows={roles.data} rowKey={(r) => r.id} onRowClick={(r) => setEditing(r)} />
      {editing !== null ? (
        <RoleDialog role={editing === 'new' ? null : editing} permissions={permissions.data ?? []} onClose={() => setEditing(null)} />
      ) : null}
    </>
  );
}
