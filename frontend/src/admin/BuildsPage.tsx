import { useState } from 'react';
import type { BuildOut } from '../api/types';
import { t } from '../i18n';
import { formatDateTime } from '../i18n/format';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { Card } from '../ui/Card';
import { ConfirmDialog } from '../ui/ConfirmDialog';
import { ErrorBanner } from '../ui/ErrorBanner';
import { PageSkeleton } from '../ui/Skeleton';
import { Table, type Column } from '../ui/Table';
import { useToast } from '../ui/Toast';
import { useBuilds, useRollbackBuild } from './api';
import { buildStatus } from './labels';

/** Faqat e'lon qilingan (joriy bo'lmagan) buildga qaytish mumkin (2-reja builds.rollback). */
function canActivate(build: BuildOut): boolean {
  return !build.active && (build.status === 'published' || build.status === 'superseded');
}

export default function BuildsPage() {
  const toast = useToast();
  const builds = useBuilds();
  const rollback = useRollbackBuild();
  const [target, setTarget] = useState<number | null>(null);

  const close = () => {
    setTarget(null);
    rollback.reset();
  };

  const confirm = () => {
    if (target === null) return;
    rollback.mutate(target, {
      onSuccess: (build) => {
        toast.show(t('builds.done', { id: build.build_id }), 'success');
        close();
      },
    });
  };

  const columns: Column<BuildOut>[] = [
    {
      key: 'build',
      header: t('builds.col.build'),
      align: 'left',
      sortValue: (b) => b.build_id,
      cell: (b) => (
        <span className="cell-main">
          <b>№{b.build_id}</b>
          {b.active ? <Badge tone="ok">{t('builds.active')}</Badge> : null}
        </span>
      ),
    },
    {
      key: 'status',
      header: t('builds.col.status'),
      align: 'left',
      cell: (b) => {
        const status = buildStatus(b.status);
        return <Badge tone={status.tone}>{status.label}</Badge>;
      },
    },
    { key: 'created', header: t('builds.col.created'), cell: (b) => formatDateTime(b.created_at) },
    { key: 'published', header: t('builds.col.published'), cell: (b) => (b.published_at ? formatDateTime(b.published_at) : t('common.dash')) },
    { key: 'load', header: t('builds.col.load'), cell: (b) => (b.load_id === null ? t('common.dash') : `№${b.load_id}`) },
    {
      key: 'action',
      header: t('builds.col.action'),
      cell: (b) =>
        canActivate(b) ? (
          <Button variant="secondary" onClick={() => setTarget(b.build_id)}>
            {t('builds.makeActive')}
          </Button>
        ) : null,
    },
  ];

  if (builds.isError) return <ErrorBanner error={builds.error} lastSuccessAt={builds.dataUpdatedAt} onRetry={() => void builds.refetch()} />;
  if (builds.isPending) return <PageSkeleton />;
  // "Oldingi" — serverdagi qoida (eng yaqin kichik superseded); id aniq yuboriladi, dialog va amal mos kelsin.
  const activeId = builds.data.find((b) => b.active)?.build_id;
  const previous = builds.data
    .filter((b) => b.status === 'superseded' && activeId !== undefined && b.build_id < activeId)
    .reduce<number | null>((best, b) => (best === null || b.build_id > best ? b.build_id : best), null);

  return (
    <Card>
      <div className="toolbar">
        <p className="note">{t('builds.note')}</p>
        <span className="toolbar__grow" />
        <Button variant="secondary" icon="history" disabled={previous === null} onClick={() => setTarget(previous)}>
          {t('builds.rollbackPrevious')}
        </Button>
      </div>
      <Table
        caption={t('admin.page.builds')}
        columns={columns}
        rows={builds.data}
        rowKey={(b) => b.build_id}
        initialSort={{ key: 'build', dir: 'desc' }}
        free
      />
      <ConfirmDialog
        open={target !== null}
        title={t('builds.confirmTitle')}
        message={t('builds.confirmText', { id: target ?? '' })}
        confirmLabel={t('builds.makeActive')}
        busy={rollback.isPending}
        error={rollback.error}
        onCancel={close}
        onConfirm={confirm}
      />
    </Card>
  );
}
